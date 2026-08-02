from pathlib import Path
from typing import Any, Dict

from utils.media_info import get_media_info


PRESET_RATIO_RANGES = {
    "Lossless (large)": (2.0, 5.0, "★★☆☆☆"),
    "High Quality (local)": (0.9, 1.2, "★★★☆☆"),
    "Fast (web friendly)": (0.7, 0.9, "★★★☆☆"),
    "Small Size (mobile)": (0.2, 0.4, "★★★☆☆"),
    "None": (0.7, 1.0, "★★☆☆☆"),
}


def estimate_output_size(file_path: str, converter: Any, opts: Dict[str, Any], default_preset: str = "None") -> Dict[str, float | str]:
    size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
    if not size:
        return {"estimated": 0, "saved": 0, "percent": 0, "confidence": "—"}

    info = get_media_info(file_path) or {}
    duration = float(info.get("duration") or 0)
    video_bitrate = opts.get("video_bitrate")
    audio_bitrate = opts.get("audio_bitrate") or info.get("audio_bitrate")

    if duration and (video_bitrate or audio_bitrate):
        total_kbps = int(video_bitrate or 0) + int(audio_bitrate or 0)
        estimated = total_kbps * 1000 * duration / 8
        confidence = "★★★★☆"
    else:
        preset = opts.get("preset", default_preset)
        lo, hi, confidence = PRESET_RATIO_RANGES.get(preset, PRESET_RATIO_RANGES["None"])
        target_ext = converter.output_extension.lower() if converter else ""
        if target_ext in {".hevc", ".h265"} or opts.get("video_codec") == "libx265":
            lo, hi = min(lo, 0.6), min(hi, 0.8)
        estimated = size * ((lo + hi) / 2)

    saved = max(0, size - estimated)
    return {
        "estimated": estimated,
        "saved": saved,
        "percent": (saved / size * 100) if size else 0,
        "confidence": confidence,
    }
