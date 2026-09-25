"""GPU-accelerated video encoders (NVENC / Quick Sync / AMF) and their detection.

The hardware encoders are exposed as ordinary codec ids, so everything downstream
(``ConversionOptions``, ``FFmpegConverter``) treats them like any other encoder.
Availability is probed from ``ffmpeg -encoders`` once per process and cached;
the probe degrades gracefully when ffmpeg is missing.
"""

import subprocess
import sys
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from utils.paths import FFMPEG

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# id -> (display label, container extensions it can write, vendor)
GPU_VIDEO_CODECS: Dict[str, Tuple[str, Tuple[str, ...], str]] = {
    "h264_nvenc": ("H.264 (NVIDIA NVENC)", (".mp4", ".mkv", ".mov", ".avi", ".flv", ".webm"), "NVIDIA"),
    "hevc_nvenc": ("H.265/HEVC (NVIDIA NVENC)", (".mp4", ".mkv", ".mov", ".avi"), "NVIDIA"),
    "av1_nvenc":  ("AV1 (NVIDIA NVENC)", (".mp4", ".mkv", ".mov"), "NVIDIA"),
    "h264_qsv":   ("H.264 (Intel Quick Sync)", (".mp4", ".mkv", ".mov", ".avi"), "Intel"),
    "hevc_qsv":   ("H.265/HEVC (Intel Quick Sync)", (".mp4", ".mkv", ".mov"), "Intel"),
    "av1_qsv":    ("AV1 (Intel Quick Sync)", (".mp4", ".mkv"), "Intel"),
    "h264_amf":   ("H.264 (AMD AMF)", (".mp4", ".mkv", ".mov", ".avi"), "AMD"),
    "hevc_amf":   ("H.265/HEVC (AMD AMF)", (".mp4", ".mkv", ".mov"), "AMD"),
    "av1_amf":    ("AV1 (AMD AMF)", (".mp4", ".mkv"), "AMD"),
}

GPU_CODEC_LABELS = {key: value[0] for key, value in GPU_VIDEO_CODECS.items()}


def gpu_codec_supports_output(codec: str, extension: str) -> bool:
    """Whether a GPU encoder can legally write into ``extension``."""
    entry = GPU_VIDEO_CODECS.get(codec)
    if entry is None:
        return False
    extension = (extension or "").lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension in entry[1]


@lru_cache(maxsize=1)
def available_gpu_codecs() -> Tuple[str, ...]:
    """Codec ids the bundled ffmpeg was built with (hardware presence aside)."""
    try:
        result = subprocess.run(
            [str(FFMPEG), "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        listing = (result.stdout or "") + (result.stderr or "")
    except Exception:
        return ()
    found = []
    for codec in GPU_VIDEO_CODECS:
        # Encoder lines look like:  V....D h264_nvenc             NVIDIA NVENC ...
        for line in listing.splitlines():
            if codec in line and line.strip().startswith("V"):
                found.append(codec)
                break
    return tuple(found)


def detect_gpu_vendor() -> Optional[str]:
    """Best-effort guess of which GPU vendor is present (for UI hints only)."""
    codecs = available_gpu_codecs()
    vendors = {GPU_VIDEO_CODECS[codec][2] for codec in codecs}
    for preferred in ("NVIDIA", "Intel", "AMD"):
        if preferred in vendors:
            return preferred
    return next(iter(vendors), None)


def gpu_codecs_for_output(extension: str) -> List[Tuple[str, str]]:
    """(id, label) pairs usable for ``extension``, ordered by detected support."""
    supported = set(available_gpu_codecs())
    picks = []
    for codec, (_label, _extensions, _vendor) in GPU_VIDEO_CODECS.items():
        if codec in supported and gpu_codec_supports_output(codec, extension):
            picks.append((codec, GPU_CODEC_LABELS[codec]))
    return picks


# Quality mapping: GPU encoders use CQP/QP rather than x264-style CRF. The
# offset keeps the slider meaningful while staying inside sane QP ranges.
def crf_to_qp(crf: int) -> int:
    return max(0, min(51, int(crf) + 4))
