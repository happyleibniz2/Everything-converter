"""3D model conversion: STL, OBJ, glTF/GLB, CAD and USD/USDZ.

Built on trimesh, which reads the whole mesh family (STL/OBJ/PLY/GLTF/GLB/
OFF/3MF, plus COLLADA/FBX when assimp is present) and writes most of it. USD
and USDZ *output* are added by :mod:`converters.usd_export`, which registers a
pxr-backed exporter with trimesh — without ``usd-core`` installed those two
targets simply report as unavailable.

Textures ride along where the format allows them:

* GLB / glTF embed PBR materials (base-colour texture included).
* OBJ writes a sidecar ``.mtl`` plus the image file next to the output.
* Applying an image to a plain mesh (e.g. an STL that has no material) bakes
  the UVs onto the geometry so the texture survives the round trip.

The optional ``texture_path`` keyword comes from the render preview dialog's
"Add texture" button, so per-file customisation reaches the worker through
``ConversionOptions.extra_args`` (see :meth:`configure_for_options`).
"""

import json
import shutil
from pathlib import Path
from typing import Optional, Tuple

from converters.base import Converter
from converters.usd_export import PXR_AVAILABLE, register as register_usd_exporters

# Formats we can read. Everything except FBX works out of the box with trimesh.
MODEL_INPUT_EXTENSIONS: Tuple[str, ...] = (
    ".stl", ".obj", ".gltf", ".glb",
    ".usd", ".usda", ".usdc", ".usdz",
    ".ply", ".off", ".3mf", ".dae", ".fbx", ".xyz",
)

# Formats we can write (availability checked at runtime via trimesh).
MODEL_OUTPUT_FORMATS = (".stl", ".obj", ".gltf", ".glb", ".usd", ".usdz", ".ply", ".off")


def _module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def trimesh_available() -> bool:
    """Whether the model pipeline can run at all on this machine."""
    if not _module("trimesh"):
        return False
    register_usd_exporters()
    return True


class ModelConverter(Converter):
    """Convert one 3D model between mesh/CAD/USD formats."""

    category = "Model"

    def __init__(self, name: str, input_extensions: Tuple[str, ...],
                 output_extension: str, texture_path: Optional[str] = None):
        self.name = name
        self.input_extensions = tuple(input_extensions)
        self.output_extension = output_extension
        # Set from ConversionOptions.extra_args entry "--texture <path>".
        self.texture_path: Optional[str] = texture_path

    # -------------------------------------------------------- availability --
    def is_available(self) -> bool:
        if not trimesh_available():
            return False
        if self.output_extension in (".usd", ".usdz"):
            return PXR_AVAILABLE
        return True

    # ------------------------------------------------------------- options --
    @classmethod
    def configure_for_options(cls, converter, options):
        """Copy ``converter`` with any ``--texture <path>`` from extra_args applied.

        Keeps the model pipeline compatible with the generic
        ``ConversionOptions`` plumbing without teaching the factory about us.
        """
        texture = None
        args = list(getattr(options, "extra_args", None) or [])
        for index, arg in enumerate(args):
            if str(arg).lower() in ("--texture", "-texture") and index + 1 < len(args):
                texture = str(args[index + 1])
        if texture == getattr(converter, "texture_path", None):
            return converter
        configured = cls(converter.name, converter.input_extensions,
                         converter.output_extension, texture_path=texture)
        configured.category = converter.category
        return configured

    # ------------------------------------------------------------ convert --
    def convert(self, input_file, output_file):
        import trimesh

        mesh = trimesh.load(str(input_file), force="mesh", process=False)
        if mesh is None or len(mesh.faces) == 0:
            raise RuntimeError("No mesh geometry found in the input model")

        if self.texture_path:
            self._apply_texture(trimesh, mesh, self.texture_path)

        target = str(output_file)
        extension = Path(target).suffix.lower()

        if extension == ".obj":
            self._write_obj(trimesh, mesh, target)
            return
        if extension == ".gltf":
            # Sidecar .bin + textures; trimesh needs a directory-based path.
            mesh.export(target)
            return
        try:
            mesh.export(target)
        except ValueError as exc:
            # trimesh raises ValueError("... exporter not available") when the
            # optional backend (pxr for USD, networkx for 3MF...) is missing.
            raise RuntimeError(f"Cannot export {extension}: {exc}") from exc

    # ----------------------------------------------------------- textures --
    @staticmethod
    def _apply_texture(trimesh, mesh, texture_path: str) -> None:
        """Attach an image as the model's base-colour texture."""
        from PIL import Image  # noqa: F401 - validated dependency for the material

        image_path = Path(texture_path)
        if not image_path.is_file():
            raise RuntimeError(f"Texture file not found: {image_path}")

        material = trimesh.visual.material.PBRMaterial(
            baseColorTexture=Image.open(image_path),
            baseColorFactor=[1.0, 1.0, 1.0, 1.0],
            metallicFactor=0.0, roughnessFactor=1.0,
        )
        # Meshes loaded from STL/OBJ have no UVs; project the texture with
        # planar mapping so every face samples the image after conversion.
        texture = trimesh.visual.TextureVisuals(uv=mesh.visual.uv, material=material)
        if mesh.visual.uv is None:
            import numpy as np

            bounds = mesh.bounds
            span = np.maximum(bounds[1] - bounds[0], 1e-9)
            projected = (mesh.vertices[:, :2] - bounds[0][:2]) / span[:2]
            texture = trimesh.visual.TextureVisuals(uv=projected, material=material)
        mesh.visual = texture

    # -------------------------------------------------------------- obj --
    @staticmethod
    def _write_obj(trimesh, mesh, target: str) -> None:
        """OBJ with its material library; keeps textures as visible sidecars."""
        mesh.export(target)
        visual = getattr(mesh, "visual", None)
        material = getattr(visual, "material", None)
        image = getattr(material, "baseColorTexture", None) or getattr(material, "image", None)
        if image is None:
            return
        stem = Path(target).stem
        image_path = Path(target).with_suffix("").parent / f"{stem}_texture.png"
        try:
            image.save(image_path)
        except Exception:
            return  # The geometry exported fine; the texture is a bonus.
        mtl_path = Path(target).with_suffix(".mtl")
        if mtl_path.exists():
            text = mtl_path.read_text(encoding="utf-8", errors="ignore")
            mtl_path.write_text(text.replace("map_Kd ", f"map_Kd {image_path.name} "),
                                encoding="utf-8")

    # --------------------------------------------------------- estimation --
    def estimate_ratio(self, source_size: int) -> float:
        """Rough size multiplier used by the batch estimator."""
        return {
            ".stl": 1.6,       # ASCII STL triples binary facet data
            ".obj": 1.4,
            ".ply": 1.2,
            ".gltf": 1.5,      # JSON wrapper + base64/bin buffer
            ".glb": 0.95,
            ".usd": 1.3,
            ".usdz": 1.1,
            ".off": 1.1,
        }.get(self.output_extension, 1.2)


def build_model_converters():
    """Instantiate the template converters for every supported pair."""
    converters = []
    readable = MODEL_INPUT_EXTENSIONS
    for output in MODEL_OUTPUT_FORMATS:
        label = output[1:].upper()
        converters.append(ModelConverter(f"Models → {label}", readable, output))
    return converters


MODEL_CONVERTERS = build_model_converters()
AVAILABLE_MODEL_CONVERTERS = [c for c in MODEL_CONVERTERS if c.is_available()]

__all__ = [
    "ModelConverter", "MODEL_INPUT_EXTENSIONS", "MODEL_OUTPUT_FORMATS",
    "MODEL_CONVERTERS", "AVAILABLE_MODEL_CONVERTERS", "trimesh_available",
]
