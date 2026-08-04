# utils/paths.py

import sys
from pathlib import Path

# ---------------------------------------------------------------------
# 1. Determine the base directory where resources are located
# ---------------------------------------------------------------------
def get_base_dir() -> Path:
    """
    Returns the root directory of the application:
    - When running from source (python app.py): the project root.
    - When frozen by PyInstaller: sys._MEIPASS (temporary folder).
    - When frozen by Nuitka (or other): the folder containing the executable.
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller uses _MEIPASS
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS)
        # Nuitka and other bundlers: the executable is in the bundle root
        return Path(sys.executable).parent
    # Development: this file is in utils/, so project root is two levels up
    return Path(__file__).resolve().parent.parent

# Base directory for all resources
BASE = get_base_dir()

# ---------------------------------------------------------------------
# 2. Define all paths relative to BASE
# ---------------------------------------------------------------------
RESOURCES = BASE / "resources"
ICONS = RESOURCES / "icons"
LANGUAGE_EN_US = RESOURCES / "language" / "en_US.json"
# If you have other language files, you can pattern:
# LANGUAGE_FILES = RESOURCES / "language"

FFMPEG = BASE / "ffmpeg" / "ffmpeg.exe"
FFPROBE = BASE / "ffmpeg" / "ffprobe.exe"

# Output, temp, logs – these are user data, not bundled.
# They can stay relative to the user's home or current directory.
USER_DATA = Path.home() / "AppData" / "Local" / "EverythingConverter"
OUTPUT = USER_DATA / "output"
TEMP = USER_DATA / "temp"
LOGS = USER_DATA / "logs"

# Ensure user data directories exist
OUTPUT.mkdir(parents=True, exist_ok=True)
TEMP.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# 3. (Optional) For debugging – print paths when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    print(f"BASE: {BASE}")
    print(f"RESOURCES: {RESOURCES}")
    print(f"ICONS: {ICONS}")
    print(f"LANGUAGE_EN_US: {LANGUAGE_EN_US}")
    print(f"FFMPEG: {FFMPEG}")
    print(f"FFPROBE: {FFPROBE}")
    print(f"OUTPUT: {OUTPUT}")
    print(f"TEMP: {TEMP}")
    print(f"LOGS: {LOGS}")