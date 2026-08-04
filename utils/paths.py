# utils/paths.py

import sys
from pathlib import Path

def get_base_dir():
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS)
        # Nuitka: exe is in the root
        return Path(sys.executable).parent
    # Development: this file is in utils/, so root is two levels up
    return Path(__file__).parent.parent

# ROOT is the base directory (for compatibility with existing code)
ROOT = get_base_dir()

# Other paths
RESOURCES = ROOT / "resources"
ICONS = RESOURCES / "icons"
UI = ROOT / "ui"
FFMPEG = ROOT / "ffmpeg" / "ffmpeg.exe"
FFPROBE = ROOT / "ffmpeg" / "ffprobe.exe"

# User data (unbundled)
APP_DATA = Path.home() / "AppData" / "Local" / "EverythingConverter"
OUTPUT = APP_DATA / "output"
TEMP = APP_DATA / "temp"
LOGS = APP_DATA / "logs"
OUTPUT.mkdir(parents=True, exist_ok=True)
TEMP.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

# Optional: keep LANGUAGE_EN_US if you use it elsewhere
LANGUAGE_EN_US = RESOURCES / "language" / "en_US.json"