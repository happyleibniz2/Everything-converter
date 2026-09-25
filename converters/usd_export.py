"""USD / USDZ writing for trimesh, registered as a trimesh export plugin.

trimesh ships a USD *loader* but no USD exporter, so ``mesh.export("x.usd")``
fails out of the box. This module registers writers for ``.usd``, ``.usda``,
``.usdc`` and ``.usdz`` through Pixar's ``pxr`` Python bindings (the
``usd-core`` wheel), making USD a first-class *output* format for the model
converter — not just an input one.

Calling-convention note: ``trimesh.export_mesh`` calls registered exporters as
``exporter(mesh, **kwargs)`` — it does NOT pass the opened file object. The
writers therefore return serialised bytes (loose layers as ascii ``.usda`` or
binary ``.usdc`` blobs; ``.usdz`` as a real zip archive assembled with
``UsdZip.Writer`` plus embedded textures). When ModelConverter exports to a
path it writes those bytes itself, which also lets loose USD formats carry a
``texture.png`` sidecar next to the layer.

Importing this module is all that is needed; it is a no-op when ``pxr`` is
absent so the rest of the app keeps working without the dependency.
"""

import io
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from logger import logger

try:  # pragma: no cover - availability depends on the installed extras
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade
    PXR_AVAILABLE = True
except Exception:  # ImportError or platform-specific load failure
    Gf = Usd = UsdGeom = UsdShade = Sdf = None
    PXR_AVAILABLE = False


def _base_colour(material) -> tuple:
    """Best-effort RGB extraction from a trimesh Simple/PBR material."""
    if material is None:
        return (0.8, 0.8, 0.8)
    for attribute in ("baseColorFactor", "diffuse"):
        value = getattr(material, attribute, None)
        if value is None:
            continue
        try:
            if hasattr(value, "shape"):                    # numpy array
                components = [float(component) for component in list(value)[:3]]
            elif hasattr(value, "toRGBA"):                 # PIL colour
                components = [component / 255.0 for component in value.toRGBA()[:3]]
            else:                                          # plain sequence
                components = [float(component) for component in list(value)[:3]]
                if max(components) > 1.0:                  # given as 0-255
                    components = [component / 255.0 for component in components]
            if len(components) == 3:
                return tuple(min(max(component, 0.0), 1.0) for component in components)
        except Exception:
            continue
    return (0.8, 0.8, 0.8)


def _material_image(mesh):
    """The base-colour texture of a mesh, if it has one (a PIL image)."""
    visual = getattr(mesh, "visual", None)
    material = getattr(visual, "material", None)
    image = (getattr(material, "baseColorTexture", None)
             or getattr(material, "image", None))
    if image is not None and hasattr(image, "save"):
        return image
    return None


def _encode_png(image) -> Optional[bytes]:
    buffer = io.BytesIO()
    try:
        image.convert("RGBA").save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as exc:  # never fail the whole export over a texture
        logger.debug("USD texture encoding skipped: %s", exc)
        return None


def _populate_stage(stage, mesh, texture_reference: Optional[str]) -> None:
    """Write geometry, normals, UVs and a display material into *stage*."""
    root_path = Sdf.Path("/World")
    root = UsdGeom.Xform.Define(stage, root_path)
    stage.SetDefaultPrim(root.GetPrim())

    mesh_path = root_path.AppendChild("Model")
    usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)

    vertices = mesh.vertices
    faces = mesh.faces

    usd_mesh.CreatePointsAttr([tuple(vertex) for vertex in vertices])
    usd_mesh.CreateFaceVertexCountsAttr([len(face) for face in faces])
    usd_mesh.CreateFaceVertexIndicesAttr(
        [int(index) for face in faces for index in face])
    normals_attr = usd_mesh.GetNormalsAttr()
    if normals_attr is None:
        usd_mesh.CreateNormalsAttr()
        normals_attr = usd_mesh.GetNormalsAttr()
    normals_attr.Set([Gf.Vec3f(*normal) for normal in mesh.vertex_normals])
    try:  # older bindings expose the schema method, newer only the attribute
        usd_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    except AttributeError:
        usd_mesh.GetNormalsInterpolationAttr().Set(UsdGeom.Tokens.vertex)
    usd_mesh.CreateExtentAttr([
        tuple(vertices.min(axis=0)), tuple(vertices.max(axis=0))])

    uvs = getattr(getattr(mesh, "visual", None), "uv", None)
    if uvs is not None and len(uvs) == len(vertices):
        indices = [int(index) for face in faces for index in face]
        pairs = [(float(uvs[index][0]), float(uvs[index][1]))
                 for index in indices]
        UsdGeom.PrimvarsAPI(usd_mesh.GetPrim()).CreatePrimvar(
            "st", Sdf.ValueTypeNames.TexCoord2fArray,
            UsdGeom.Tokens.faceVarying).Set(pairs)

    material_source = getattr(getattr(mesh, "visual", None), "material", None)
    material_path = root_path.AppendChild("DisplayMaterial")
    material_api = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(
        stage, material_path.AppendChild("PreviewSurface"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        _base_colour(material_source))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.9)

    if texture_reference:
        tex_shader = UsdShade.Shader.Define(
            stage, material_path.AppendChild("BaseColorTexture"))
        tex_shader.CreateIdAttr("UsdUVTexture")
        tex_shader.CreateInput("file", Sdf.ValueTypeNames.Asset) \
                  .Set(Sdf.AssetPath(texture_reference))
        tex_shader.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        tex_shader.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        tex_shader.CreateOutput("rgb", Sdf.ValueTypeNames.Color3f)
        shader.GetInput("diffuseColor").ConnectToSource(
            tex_shader.GetOutput("rgb"))

    shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    material_api.CreateSurfaceOutput().ConnectToSource(
        shader.GetOutput("surface"))
    UsdShade.MaterialBindingAPI.Apply(usd_mesh.GetPrim()).Bind(
        UsdShade.Material(material_api.GetPrim()))


def _build_layer(mesh, extension: str, texture_reference: Optional[str]) -> bytes:
    """Serialise *mesh* into a fresh ``.usda``/``.usdc`` layer and return bytes.

    Virtual (stream-only) layers are unreliable across usd-core builds — the
    file-format arguments must be strings and some releases refuse to create
    them at all — so we write through a short-lived temporary file instead.
    """
    with tempfile.TemporaryDirectory(prefix="ec-usd-") as folder:
        path = os.path.join(folder, "layer" + extension)
        stage = Usd.Stage.CreateNew(path)
        if stage is None:
            raise RuntimeError(f"Could not create a {extension} stage")
        _populate_stage(stage, mesh, texture_reference)
        stage.GetRootLayer().Save()
        del stage
        with open(path, "rb") as handle:
            data = handle.read()
    if not data:
        raise RuntimeError("USD serialisation produced no data")
    return data


def _write_stored(zf: zipfile.ZipFile, name: str, payload: bytes) -> None:
    """Add *payload* to the archive uncompressed, with sane file permissions.

    The USDZ spec requires STORED entries; ``external_attr`` carries the POSIX
    mode (0644 << 16) that pxr's reader expects when validating archives.
    """
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o644 << 16
    zf.writestr(info, payload)


def _build_usdz(mesh, texture_bytes: Optional[bytes]) -> bytes:
    """Assemble a spec-compliant .usdz zip carrying layer + textures."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
        _write_stored(zf, "world.usdc", _build_layer(
            mesh, ".usdc", "./texture.png" if texture_bytes else None))
        if texture_bytes:
            _write_stored(zf, "texture.png", texture_bytes)
    data = archive.getvalue()
    if not data:
        raise RuntimeError("USDZ serialisation produced no data")
    return data


def export_usd(mesh, file_obj=None, **kwargs):
    """Export a :class:`trimesh.Trimesh` to USD (ascii/binary) or USDZ.

    Registered as a trimesh mesh exporter, so it is called as
    ``exporter(mesh, **kwargs)`` — *without* the opened file object. The
    target therefore has to come from kwargs (``file_path=`` / ``path=``);
    when it is missing we fall back to a binary ``.usdc`` layer, which is the
    safest default for a bare ``mesh.export(file_type="usd")`` call.

    Returns serialised bytes. ``.usdz`` builds a zip archive, ``.usdc/.usd``
    a binary layer, anything else ascii ``.usda``. Textures are embedded in
    USDZ archives; for loose files the caller (ModelConverter) writes the
    ``texture.png`` sidecar via :func:`texture_sidecar_for`.
    """
    if not PXR_AVAILABLE:
        raise RuntimeError("USD export requires the 'usd-core' package "
                           "(pip install usd-core)")

    target = str(kwargs.get("file_path") or kwargs.get("path")
                 or getattr(file_obj, "name", "") or "").lower()
    image = _material_image(mesh)
    texture_bytes = _encode_png(image) if image is not None else None

    if target.endswith(".usdz"):
        return _build_usdz(mesh, texture_bytes)
    if target.endswith((".usdc", ".usd")):
        reference = "./texture.png" if texture_bytes else None
        return _build_layer(mesh, ".usdc", reference)
    reference = "./texture.png" if texture_bytes else None
    return _build_layer(mesh, ".usda", reference)


def texture_sidecar_for(mesh) -> Optional[bytes]:
    """PNG bytes for the mesh's base-colour texture, or None."""
    image = _material_image(mesh)
    return _encode_png(image) if image is not None else None


def write_usd(mesh, output_file: str) -> None:
    """Serialize *mesh* to *output_file*, including texture sidecars."""
    path = Path(output_file)
    data = export_usd(mesh, file_path=str(path))
    if path.suffix.lower() == ".usdz" and not zipfile.is_zipfile(io.BytesIO(data)):
        raise RuntimeError("USDZ archive failed validation")
    path.write_bytes(data)
    if path.suffix.lower() in (".usd", ".usda", ".usdc"):
        sidecar = texture_sidecar_for(mesh)
        if sidecar is not None:
            try:
                (path.parent / "texture.png").write_bytes(sidecar)
            except OSError as exc:
                logger.debug("Could not write USD texture sidecar: %s", exc)


def _export_usdz_dict(mesh, **kwargs):
    """Multi-file exporter form for ``usdz``.

    trimesh treats a dict return value as a bundle of files and writes every
    entry through the resolver — but a USDZ is a single zip archive, so we
    return exactly one member named after the destination (or a generic
    ``model.usdz`` when the exporter was called without a path).
    """
    target = str(kwargs.get("file_path") or kwargs.get("path") or "").lower()
    name = os.path.basename(target) if target.endswith(".usdz") else "model.usdz"
    return {name: export_usd(mesh, file_path=target or "x.usdz")}


def register() -> bool:
    """Install the USD exporters into trimesh. Safe to call repeatedly."""
    if not PXR_AVAILABLE:
        return False
    try:
        from trimesh.exchange import export as _export
    except Exception as exc:  # trimesh missing entirely
        logger.debug("trimesh unavailable, USD plugin not registered: %s", exc)
        return False
    if "usd" in _export._mesh_exporters:
        return True
    for extension in ("usd", "usda", "usdc"):
        _export._mesh_exporters[extension] = export_usd
    _export._mesh_exporters["usdz"] = _export_usdz_dict
    logger.info("USD/USDZ exporter registered with trimesh")
    return True


__all__ = ["PXR_AVAILABLE", "export_usd", "register", "texture_sidecar_for",
           "write_usd"]

# Import-time registration: `import converters.usd_export` (or importing the
# model converter, which does exactly that) is enough.
register()
