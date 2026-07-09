import locale
import os
import platform
import subprocess
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PyQt5.QtCore import QLibraryInfo, Qt
from PyQt5.QtGui import QGuiApplication
from utils.paths import FFMPEG, OUTPUT, TEMP, LOGS

APP_NAME = "Everything Converter"
APP_VERSION = "0.1.0"
BUILD_TYPE = "Debug"


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "Not Installed"


def ffmpeg_version() -> str:
    if not FFMPEG.exists():
        return "Not Found"
    try:
        result = subprocess.run(
            [str(FFMPEG), "-version"],
            capture_output=True,
            text=True,
            timeout=3
        )
        return result.stdout.splitlines()[0]
    except Exception:
        return "Unknown"


def generate_report() -> str:
    screen = QGuiApplication.primaryScreen()
    if screen:
        geometry = screen.geometry()
        dpi = screen.logicalDotsPerInch()
        scale = round(dpi / 96 * 100)
        resolution = f"{geometry.width()} x {geometry.height()}"
    else:
        resolution = "Unknown"
        dpi = 0
        scale = 100

    lines = []
    lines.append("=" * 60)
    lines.append(APP_NAME)
    lines.append("=" * 60)
    lines.append(f"Version           : {APP_VERSION}")
    lines.append(f"Build             : {BUILD_TYPE}")
    lines.append(f"Started           : {datetime.now()}")
    lines.append("")
    lines.append("SYSTEM")
    lines.append("-" * 60)
    lines.append(f"OS                : {platform.system()}")
    lines.append(f"Release           : {platform.release()}")
    lines.append(f"Version           : {platform.version()}")
    lines.append(f"Architecture      : {platform.machine()}")
    lines.append(f"Processor         : {platform.processor()}")
    lines.append(f"Python            : {platform.python_version()}")
    lines.append(f"Executable        : {sys.executable}")
    lines.append(f"Working Directory : {Path.cwd()}")
    lines.append(f"User              : {os.getenv('USERNAME')}")
    lines.append(f"Computer          : {os.getenv('COMPUTERNAME')}")
    lines.append("")
    lines.append("DISPLAY")
    lines.append("-" * 60)
    lines.append(f"Resolution        : {resolution}")
    lines.append(f"DPI               : {dpi:.1f}")
    lines.append(f"DPI Scale         : {scale}%")
    lines.append("")
    lines.append("QT")
    lines.append("-" * 60)
    lines.append(f"Qt Version        : {QLibraryInfo.version().toString()}")
    lines.append(f"PyQt5 Version     : {package_version('PyQt5')}")
    lines.append(f"Theme             : {_get_theme()}")
    lines.append(f"Language          : {locale.getdefaultlocale()[0]}")
    lines.append("")
    lines.append("LIBRARIES")
    lines.append("-" * 60)
    packages = [
        "Pillow", "PyMuPDF", "pypdf", "openpyxl",
        "python-docx", "python-pptx", "PyYAML", "py7zr"
    ]
    for pkg in packages:
        lines.append(f"{pkg:<18}: {package_version(pkg)}")
    lines.append("")
    lines.append("FFMPEG")
    lines.append("-" * 60)
    lines.append(f"Version           : {ffmpeg_version()}")
    lines.append(f"Location          : {FFMPEG}")
    lines.append("")
    lines.append("DIRECTORIES")
    lines.append("-" * 60)
    lines.append(f"Output            : {OUTPUT.resolve()}")
    lines.append(f"Temp              : {TEMP.resolve()}")
    lines.append(f"Logs              : {LOGS.resolve()}")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def _get_theme():
    try:
        return QGuiApplication.styleHints().colorScheme().name
    except AttributeError:
        return "Unknown (Qt5)"
