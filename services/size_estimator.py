"""Heuristic output-size estimation.

These are deliberately rough: a real answer requires actually encoding. The
returned ``confidence`` communicates that uncertainty to the user instead of
hiding it behind a precise-looking number.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from converters.presets import category_for_extension
from models.conversion_options import ConversionOptions
from utils.formatter import format_size

# preset -> (low ratio, high ratio, confidence stars)
PRESET_RATIO_RANGES = {
    "Lossless (large)": (2.0, 5.0, "★★☆☆☆"),
    "High Quality (local)": (0.9, 1.2, "★★★☆☆"),
    "Fast (web friendly)": (0.7, 0.9, "★★★☆☆"),
    "Small Size (mobile)": (0.2, 0.4, "★★★☆☆"),
    "None": (0.7, 1.0, "★★☆☆☆"),
}

# Rough container/codec efficiency relative to a typical H.264 source.
CODEC_EFFICIENCY = {
    "libx265": 0.65,
    "libvpx-vp9": 0.7,
    "libvpx": 1.0,
    "libx264": 1.0,
    "mpeg4": 1.4,
    "wmv2": 1.4,
    "libxvid": 1.35,
}

# Lossless/uncompressed image formats grow; lossy ones shrink.
IMAGE_RATIOS = {
    ".png": 1.6,
    ".bmp": 6.0,
    ".tiff": 4.0,
    ".eps": 5.0,
    ".gif": 0.9,
    ".jpg": 0.35,
    ".jpeg": 0.35,
    ".webp": 0.28,
    ".heif": 0.25,
    ".heic": 0.25,
}


@dataclass
class SizeEstimate:
    source: int = 0
    estimated: float = 0.0
    confidence: str = "—"

    @property
    def saved(self) -> float:
        return self.source - self.estimated

    @property
    def percent(self) -> float:
        if not self.source:
            return 0.0
        return self.saved / self.source * 100.0

    @property
    def grows(self) -> bool:
        return self.estimated > self.source

    def describe(self) -> str:
        """Compact label for the queue's Estimate column.

        Deliberately excludes the confidence stars: the column is narrow and
        they would truncate the number itself. Use :meth:`tooltip` for those.
        """
        if not self.source or not self.estimated:
            return "—"
        arrow = "▲" if self.grows else "▼"
        return f"≈{format_size(self.estimated)}  {arrow}{abs(self.percent):.0f}%"

    def tooltip(self) -> str:
        """Fuller explanation, including how reliable the estimate is."""
        if not self.source or not self.estimated:
            return ""
        verb = "larger" if self.grows else "smaller"
        return (
            f"Source: {format_size(self.source)}\n"
            f"Estimated output: {format_size(self.estimated)}\n"
            f"About {abs(self.percent):.0f}% {verb}\n"
            f"Confidence: {self.confidence}"
        )


def estimate_output_size(file_path: str, converter: Any,
                         options: Optional[ConversionOptions] = None,
                         default_preset: str = "None",
                         media_info: Optional[Dict] = None) -> SizeEstimate:
    """Estimate the output size for one conversion."""
    try:
        source = Path(file_path).stat().st_size
    except OSError:
        source = 0
    if not source or converter is None:
        return SizeEstimate(source=source)

    options = options or ConversionOptions()
    target_ext = (converter.output_extension or "").lower()
    category = category_for_extension(target_ext)

    # Remuxing rewrites the container only, so size barely moves.
    if options.copy_mode:
        return SizeEstimate(source=source, estimated=source * 1.01, confidence="★★★★★")

    if category == "Image":
        ratio = IMAGE_RATIOS.get(target_ext, 1.0)
        return SizeEstimate(source=source, estimated=source * ratio, confidence="★★★☆☆")

    info = media_info if media_info is not None else {}
    duration = float(info.get("duration") or 0)

    # An explicit bitrate makes size arithmetic rather than guesswork.
    video_bitrate = options.video_bitrate
    audio_bitrate = options.audio_bitrate or (info.get("audio_bitrate") or 0) / 1000 or None

    if duration and (video_bitrate or audio_bitrate):
        total_kbps = float(video_bitrate or 0) + float(audio_bitrate or 0)
        if total_kbps > 0:
            estimated = total_kbps * 1000 * duration / 8
            return SizeEstimate(source=source, estimated=estimated, confidence="★★★★☆")

    if category == "Audio":
        bitrate = float(audio_bitrate or 128)
        if duration:
            estimated = bitrate * 1000 * duration / 8
            # Lossless audio codecs ignore the bitrate request entirely.
            if target_ext in (".flac", ".wav"):
                estimated = source * (1.0 if target_ext == ".wav" else 0.6)
                return SizeEstimate(source=source, estimated=estimated, confidence="★★★☆☆")
            return SizeEstimate(source=source, estimated=estimated, confidence="★★★★☆")
        return SizeEstimate(source=source, estimated=source * 0.6, confidence="★★☆☆☆")

    # Video with CRF or a named preset: fall back to ratio bands.
    preset = options.preset or default_preset or "None"
    low, high, confidence = PRESET_RATIO_RANGES.get(preset, PRESET_RATIO_RANGES["None"])
    ratio = (low + high) / 2

    ratio *= CODEC_EFFICIENCY.get(options.video_codec or "libx264", 1.0)

    if options.crf is not None:
        # CRF 23 is the x264 default; each ~6 steps roughly halves/doubles size.
        ratio *= 2 ** ((23 - options.crf) / 6.0)
        confidence = "★★★☆☆"

    # Downscaling cuts pixel count, which dominates bitrate demand.
    if options.scale and info.get("width") and info.get("height"):
        try:
            width, height = (int(value) for value in options.scale.split(":", 1))
            if width > 0 and height > 0:
                source_pixels = int(info["width"]) * int(info["height"])
                if source_pixels:
                    ratio *= min(1.0, (width * height) / source_pixels) ** 0.75
        except (ValueError, TypeError):
            pass

    # Trimming scales output linearly with the retained fraction.
    if duration and (options.start_time or options.end_time):
        kept = _trimmed_duration(duration, options.start_time, options.end_time)
        if kept > 0:
            ratio *= kept / duration

    return SizeEstimate(source=source, estimated=max(0.0, source * ratio), confidence=confidence)


def _parse_timecode(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parts = [float(part) for part in text.split(":")]
    except ValueError:
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def _trimmed_duration(duration: float, start: Optional[str], end: Optional[str]) -> float:
    begin = _parse_timecode(start) or 0.0
    finish = _parse_timecode(end)
    finish = duration if finish is None else min(finish, duration)
    return max(0.0, finish - begin)
