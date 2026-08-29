"""Codec tables, quality presets and format metadata shared by UI and conversion layers.

This module is deliberately free of Qt and UI imports so that both the widgets
and the worker/model layers can depend on it without cycles.
"""

VIDEO_CODECS = {
    "libx264": "H.264 (x264)",
    "libx265": "H.265 / HEVC",
    "libvpx": "VP8",
    "libvpx-vp9": "VP9",
    "mpeg4": "MPEG-4",
    "wmv2": "WMV2",
    "libxvid": "Xvid",
}

AUDIO_CODECS = {
    "aac": "AAC",
    "libmp3lame": "MP3",
    "flac": "FLAC",
    "pcm_s16le": "WAV (PCM)",
    "libvorbis": "Vorbis",
    "opus": "Opus",
    "wmav2": "WMA",
}

DEFAULT_VIDEO_CODEC = {
    ".mp4": "libx264",
    ".mkv": "libx264",
    ".mov": "libx264",
    ".avi": "libx264",
    ".webm": "libvpx",
    ".flv": "libx264",
    ".3gp": "libx264",
    ".wmv": "wmv2",
}

DEFAULT_AUDIO_CODEC = {
    ".mp3": "libmp3lame",
    ".aac": "aac",
    ".flac": "flac",
    ".wav": "pcm_s16le",
    ".ogg": "libvorbis",
    ".m4a": "aac",
    ".wma": "wmav2",
}

# Quality presets. Kept as plain ffmpeg argument lists.
PRESETS = {
    "None": [],
    "Fast (web friendly)": ["-preset", "veryfast", "-crf", "28"],
    "High Quality (local)": ["-preset", "slow", "-crf", "18"],
    "Small Size (mobile)": ["-preset", "veryfast", "-crf", "32", "-vf", "scale=640:-2"],
    "Lossless (large)": ["-preset", "slow", "-crf", "0"],
}

# Human readable one-liners used by the preset picker.
PRESET_DESCRIPTIONS = {
    "None": "Use the converter defaults. Balanced quality and size.",
    "Fast (web friendly)": "Encodes quickly at a smaller size. Great for sharing and uploads.",
    "High Quality (local)": "Slower encode, near-transparent quality. Best for archiving.",
    "Small Size (mobile)": "Downscales to 640px wide for the smallest possible files.",
    "Lossless (large)": "Mathematically lossless. Produces very large files.",
}

# Resolution presets exposed as (label, width, height). height/width of 0 means "keep original".
RESOLUTION_PRESETS = [
    ("Original", 0, 0),
    ("2160p (3840x2160)", 3840, 2160),
    ("1440p (2560x1440)", 2560, 1440),
    ("1080p (1920x1080)", 1920, 1080),
    ("720p (1280x720)", 1280, 720),
    ("480p (854x480)", 854, 480),
    ("360p (640x360)", 640, 360),
]

AUDIO_SAMPLE_RATES = ["22050", "32000", "44100", "48000", "96000", "192000"]

AUDIO_BITRATE_CHOICES = [64, 96, 128, 160, 192, 256, 320]

# Category → member extensions. Drives the format browser and file-type icons.
CATEGORY_EXTENSIONS = {
    "Image": (
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        ".tiff", ".heif", ".heic", ".eps",
    ),
    "Video": (
        ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".3gp", ".wmv",
    ),
    "Audio": (
        ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma",
    ),
}

VIDEO_EXTENSIONS = frozenset(CATEGORY_EXTENSIONS["Video"])
AUDIO_EXTENSIONS = frozenset(CATEGORY_EXTENSIONS["Audio"])
IMAGE_EXTENSIONS = frozenset(CATEGORY_EXTENSIONS["Image"])


def category_for_extension(extension: str) -> str:
    """Return the broad media category for a file extension."""
    extension = str(extension).lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    if extension in VIDEO_EXTENSIONS:
        return "Video"
    if extension in AUDIO_EXTENSIONS:
        return "Audio"
    if extension in IMAGE_EXTENSIONS:
        return "Image"
    return "Unknown"
