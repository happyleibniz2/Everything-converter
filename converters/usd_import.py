"""USD / USDZ *reading* for trimesh, registered as a trimesh loader plugin.

trimesh 5.x advertises USD support but its wheel (and the usd-core combo we
ship against) has no ``usd``/``usdz`` entry in ``mesh_loaders`` — so loading a
``.usdz`` raises the same cryptic ``NotImplementedError: file_type 'usdz' not
supported`` that FBX used to. This module closes that gap with pxr-backed
loaders for ``.usd``, ``.usda``, ``.usdc`` and ``.usdz``.

How it works: open the file as a Usd.Stage (pxr resolves usdz archives
natively), walk every UsdGeom.Mesh prim, apply its model transform, pull out
points / face-vertex topology / normals / ``st`` primvars, resolve the bound
UsdPreviewSurface material (diffuse colour plus any UsdUVTexture image — read
straight out of the archive when needed) and concatenate everything into one
Trimesh, mirroring what the exporter in :mod:`converters.usd_export` writes.

Importing this module registers the loaders; it is a no-op without ``pxr``.
"""

import io
import zipfile
from pathlib import Path
from typing import Optional

from logger import logger

try:  # pragma: no cover - availability depends on the installed extras
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade
    PXR_AVAILABLE = True
except Exception:
    Gf = Usd = UsdGeom = UsdShade = Sdf = None
    PXR_AVAILABLE = False


def _sample_image(file_path: str, relative: str):
    """Load a texture referenced by a layer, including paths inside a .usdz."""
    from PIL import Image

    candidate = relative.replace("\\", "/").lstrip("./")
    if not candidate:
        return None
    try:
        if str(file_path).lower().endswith(".usdz") and zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path) as zf:
                names = {name.lower(): name for name in zf.namelist()}
                match = names.get(candidate.lower())
                if match is None:  # allow "texture.png" -> "sub/texture.png"
                    for lowered, original in names.items():
                        if lowered.endswith("/" + candidate.lower()):
                            match = original
                            break
                if match is None:
                    return None
                return Image.open(io.BytesIO(zf.read(match)))
        base = Path(file_path).parent
        for guess in (base / candidate, Path(candidate)):
            if guess.is_file():
                return Image.open(guess)
    except Exception as exc:
        logger.debug("USD texture %r could not be loaded: %s", relative, exc)
    return None


def _input_value(shader, name):
    """UsdShade.Input has no HasValue() — read Get() and treat None as unset."""
    try:
        input_socket = shader.GetInput(name)
        if input_socket is None:
            return None
        return input_socket.Get()
    except Exception:
        return None


def _material_for(mesh_prim, stage):
    """Return (rgb01, PIL image or None) from the prim's bound preview material."""
    rgb, image = None, None
    try:
        bound = UsdShade.MaterialBindingAPI(mesh_prim).ComputeBoundMaterial()
        material = bound[0] if bound else None
        if material is None:
            return rgb, image
        shader = None
        output = material.GetOutput("surface")
        if output is not None and output.HasConnectedSource():
            source = output.GetConnectedSource()
            node = source[0] if isinstance(source, (tuple, list)) else source
            prim = node.GetPrim() if node is not None else None
            if prim is not None and prim.IsValid():
                shader = UsdShade.Shader(prim)
        if shader is None:  # authored directly on the material prim?
            candidate = UsdShade.Shader(material.GetPrim())
            if candidate.GetIdAttr().HasValue():
                shader = candidate
        if shader is None:
            return rgb, image

        value = _input_value(shader, "diffuseColor")
        if value is not None and not hasattr(value, "path"):
            try:
                rgb = (float(value[0]), float(value[1]), float(value[2]))
            except Exception:
                rgb = None
        file_value = _input_value(shader, "file")
        if file_value is not None:
            reference = getattr(file_value, "path", None) or str(file_value)
            image = _sample_image(stage.GetRootLayer().identifier, reference)
    except Exception as exc:
        logger.debug("USD material lookup failed: %s", exc)
    return rgb, image


def _face_varying_pairs(primvar, face_vertex_indices, vertex_count):
    """Flatten a faceVarying primvar into per-vertex UVs (first hit wins)."""
    pairs = primvar.Get()
    indices = primvar.GetIndices()
    uvs = [[0.0, 0.0] for _ in range(vertex_count)]
    seen = set()
    if indices and len(indices) == len(pairs):
        for position, index in enumerate(indices):
            vertex = face_vertex_indices[position]
            if vertex not in seen:
                seen.add(vertex)
                uvs[vertex] = [float(pairs[position][0]), float(pairs[position][1])]
    elif len(pairs) == len(face_vertex_indices):
        for position, pair in enumerate(pairs):
            vertex = face_vertex_indices[position]
            if vertex not in seen:
                seen.add(vertex)
                uvs[vertex] = [float(pair[0]), float(pair[1])]
    return uvs


def _read_mesh_prim(mesh_prim, usd_mesh, stage, matrix):
    """Extract (vertices, faces, normals, uvs, rgb, image) from one UsdGeom.Mesh.

    *mesh_prim* is the raw Usd.Prim (binding/material lookups want that);
    *usd_mesh* is the same prim wrapped as UsdGeom.Mesh for schema accessors.
    """
    points_attr = usd_mesh.GetPointsAttr()
    if not points_attr or not points_attr.HasValue():
        return None
    points = [matrix.Transform(point) for point in points_attr.Get()]
    counts = usd_mesh.GetFaceVertexCountsAttr().Get()
    indices = usd_mesh.GetFaceVertexIndicesAttr().Get()
    vertices = [[float(p[0]), float(p[1]), float(p[2])] for p in points]
    faces, cursor = [], 0
    for count in counts:
        faces.append([int(index) for index in indices[cursor:cursor + count]])
        cursor += count
    if not vertices or not faces:
        return None

    normals = None
    normals_attr = usd_mesh.GetNormalsAttr()
    if normals_attr and normals_attr.HasValue():
        values = normals_attr.Get()
        try:  # schema-level attribute; fall back to length heuristics below
            interpolation = usd_mesh.GetNormalsInterpolationAttr().Get()
        except Exception:
            interpolation = None
        if interpolation == UsdGeom.Tokens.constant and values:
            constant = [float(values[0][0]), float(values[0][1]), float(values[0][2])]
            normals = [list(constant) for _ in range(len(faces))]
        elif len(values) == len(indices):  # faceVarying -> collapse per vertex
            flat = []
            for position, index in enumerate(indices):
                value = values[position]
                while len(flat) <= index:
                    flat.append([0.0, 0.0, 0.0])
                flat[index] = [float(value[0]), float(value[1]), float(value[2])]
            normals = flat
        elif len(values) == len(vertices):
            normals = [[float(v[0]), float(v[1]), float(v[2])] for v in values]

    uvs = None
    primvars = UsdGeom.PrimvarsAPI(mesh_prim).GetPrimvars()
    pairs = primvars.items() if hasattr(primvars, "items") \
        else [(p.GetName(), p) for p in primvars]
    for name, primvar in pairs:
        if name.split(":")[0].lower() != "st":
            continue
        if not primvar.HasAuthoredValue():
            continue
        try:
            if primvar.GetInterpolation() == UsdGeom.Tokens.faceVarying:
                uvs = _face_varying_pairs(primvar, [int(i) for i in indices],
                                          len(vertices))
            else:
                values = primvar.Get()
                if len(values) == len(vertices):
                    uvs = [[float(pair[0]), float(pair[1])] for pair in values]
        except Exception:
            continue
        if uvs is not None:
            break

    rgb, image = _material_for(mesh_prim, stage)
    return vertices, faces, normals, uvs, rgb, image


def load_usd(file_obj=None, file_type=None, resolver=None, metadata=None,
             **kwargs):
    """Load ``.usd/.usda/.usdc/.usdz`` as a single trimesh.Trimesh.

    Registered in ``trimesh.exchange.load.mesh_loaders``, which calls loaders
    as ``loader(file_obj=..., file_type=..., resolver=..., metadata=...)``
    and expects a dict of ``_load_kwargs`` arguments back — not a built
    mesh. We build the Trimesh here (pxr needs the real path) and hand it
    back through the ``meshes`` key, letting trimesh assemble the scene.
    """
    if not PXR_AVAILABLE:
        raise RuntimeError("Reading USD files requires the 'usd-core' package "
                           "(pip install usd-core)")
    import numpy as np
    import trimesh
    from trimesh.visual import TextureVisuals
    from trimesh.visual.material import PBRMaterial

    path = str(file_obj_to_str(file_obj))
    stage = Usd.Stage.Open(path)
    if stage is None:
        raise RuntimeError(f"Could not open USD file: {path}")

    all_vertices, all_faces, all_normals, all_uvs = [], [], [], []
    materials = []
    current_rgb, current_image = None, None
    cache = {}

    for prim in stage.Traverse():
        if not UsdGeom.Mesh(prim) or not prim.IsA(UsdGeom.Mesh):
            continue
        matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            Usd.TimeCode.Default())
        usd_mesh = UsdGeom.Mesh(prim)
        data = _read_mesh_prim(prim, usd_mesh, stage, matrix)
        if data is None:
            continue
        vertices, faces, normals, uvs, rgb, image = data
        offset = len(all_vertices)
        all_vertices.extend(vertices)
        all_faces.extend([[index + offset for index in face] for face in faces])
        all_normals.extend(normals if normals else [[0.0, 0.0, 1.0]] * len(vertices))
        all_uvs.extend(uvs if uvs else [[0.5, 0.5]] * len(vertices))
        key = (rgb, id(image))
        if key not in cache:
            cache[key] = len(materials)
            materials.append((rgb, image))
        current_rgb, current_image = rgb, image

    if not all_vertices:
        raise RuntimeError(f"No mesh geometry found in {Path(path).name}")

    mesh = trimesh.Trimesh(vertices=np.asarray(all_vertices, dtype=np.float64),
                           faces=np.asarray(all_faces, dtype=np.int64),
                           process=False)
    try:
        mesh.vertex_normals = np.asarray(all_normals, dtype=np.float64)
    except Exception:
        pass  # trimesh will recompute; not worth failing the load

    rgb = current_rgb if current_rgb is not None else (0.8, 0.8, 0.8)
    factor = [rgb[0], rgb[1], rgb[2], 1.0]
    if current_image is not None:
        material = PBRMaterial(baseColorTexture=current_image, baseColorFactor=factor)
        mesh.visual = TextureVisuals(uv=np.asarray(all_uvs, dtype=np.float64),
                                     material=material)
    else:
        mesh.visual = TextureVisuals(
            material=PBRMaterial(baseColorFactor=factor))
    # trimesh's _load_kwargs dispatches on key names: "vertices"+"faces"
    # rebuilds a Trimesh (visual survives via Trimesh(**kwargs)); "geometry"
    # builds a Scene. Serialise accordingly — raw dicts, not objects.
    payload = {
        "vertices": np.asarray(all_vertices, dtype=np.float64),
        "faces": np.asarray(all_faces, dtype=np.int64),
        "process": False,
    }
    visual = getattr(mesh, "visual", None)
    if visual is not None:
        payload["visual"] = visual
    uvs = getattr(visual, "uv", None)
    if uvs is not None:
        try:
            payload["face_normals"] = mesh.face_normals
        except Exception:
            pass
    return payload


def file_obj_to_str(file_obj) -> str:
    """Accept a path, file object or bytes-ish thing; return a usable path."""
    if isinstance(file_obj, (str, Path)):
        return str(file_obj)
    name = getattr(file_obj, "name", None)
    if name:
        return str(name)
    raise RuntimeError("USD loading needs a real file path (this build of "
                       "trimesh hands loaders a path, so you should not see "
                       "this)")


def register() -> bool:
    """Install the USD loaders into trimesh's extension map. Idempotent."""
    if not PXR_AVAILABLE:
        return False
    try:
        from trimesh.exchange import load as _load
    except Exception as exc:  # pragma: no cover - trimesh missing entirely
        logger.debug("trimesh unavailable, USD loader not registered: %s", exc)
        return False
    changed = False
    for extension in ("usd", "usda", "usdc", "usdz"):
        if extension not in _load.mesh_loaders:
            _load.mesh_loaders[extension] = load_usd
            changed = True
    if changed:
        logger.info("USD/USDZ loader registered with trimesh")
    return True


__all__ = ["PXR_AVAILABLE", "load_usd", "register"]

# Import-time registration, same convention as converters.usd_export.
register()
