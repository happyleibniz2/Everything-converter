"""Builds a run-ready converter from a registry converter plus user options.

Registry converters are templates: they carry the format pair and the flags that
are *intrinsic* to that conversion (e.g. ``-vn`` for audio extraction). User
options must be layered on top without discarding those intrinsic flags — the
previous code replaced ``extra_args`` wholesale, which quietly dropped ``-vn``
and left a video stream in "extract audio" output.
"""

from typing import Any

from converters.ffmpeg_base import FFmpegConverter
from models.conversion_options import ConversionOptions


def configure_converter(converter: Any, options: ConversionOptions) -> Any:
    """Return a converter instance configured for ``options``.

    Non-ffmpeg converters (Pillow) take no options and are returned unchanged.
    """
    if not isinstance(converter, FFmpegConverter):
        return converter

    kwargs = options.converter_kwargs()

    # Preserve the template's intrinsic flags, and don't duplicate them.
    intrinsic = list(converter.extra_args or [])
    user_args = list(kwargs.pop("extra_args", []))
    merged = intrinsic + [arg for arg in user_args if arg not in intrinsic or not _is_flag(arg)]

    # An audio-only conversion has no video codec to set, whatever the dialog says.
    if "-vn" in intrinsic:
        kwargs["video_codec"] = None
        kwargs["scale"] = None

    configured = FFmpegConverter(
        converter.name,
        converter.input_extensions,
        converter.output_extension,
        extra_args=merged,
        **kwargs,
    )
    configured.category = converter.category
    return configured


def _is_flag(arg: str) -> bool:
    """True for ``-x`` style switches (as opposed to their values)."""
    return isinstance(arg, str) and arg.startswith("-") and not arg[1:2].isdigit()
