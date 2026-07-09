from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FFMPEG = ROOT / "ffmpeg" / "ffmpeg.exe"
FFPROBE = ROOT / "ffmpeg" / "ffprobe.exe"
OUTPUT = ROOT / "output"
TEMP = ROOT / "temp"
LOGS = ROOT / "logs"
RESOURCES = ROOT / "resources"
ICONS = RESOURCES / "icons"
