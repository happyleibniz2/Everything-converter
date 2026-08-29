import multiprocessing
import sys

from PySide6.QtCore import QLocale, QSettings, Qt, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from qfluentwidgets import FluentTranslator

import system_info
from lang import lang
from logger import logger
from ui.main_window import MainWindow, apply_appearance
from utils.paths import RESOURCES

# Locale codes understood by the bundled language files.
SUPPORTED_LANGUAGES = ("en_US", "zh_CN", "ja_JP")


def _seed_defaults(settings: QSettings) -> None:
    """Populate first-run defaults, deriving sensible values from the machine."""
    if not settings.contains("threads"):
        # 0 means "let ffmpeg decide", which is usually better than guessing.
        settings.setValue("threads", 0)

    if not settings.contains("parallel_jobs"):
        # 0 means auto; the planner derives a value from the CPU count.
        settings.setValue("parallel_jobs", 0)

    if not settings.contains("language"):
        settings.setValue("language", _detect_language())

    if not settings.contains("theme_mode"):
        settings.setValue("theme_mode", "auto")


def _detect_language() -> str:
    """Match the system locale to a bundled translation, defaulting to English."""
    system = QLocale.system().name()
    if system in SUPPORTED_LANGUAGES:
        return system
    prefix = system.split("_")[0]
    for candidate in SUPPORTED_LANGUAGES:
        if candidate.startswith(prefix):
            return candidate
    return "en_US"


def run():
    # Crisp rendering on fractional-scaling displays.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Everything Converter")
    app.setApplicationVersion("0.2.0")

    settings = QSettings("EverythingConverter", "Settings")
    _seed_defaults(settings)

    language_code = settings.value("language", "en_US", type=str) or "en_US"
    lang.load_language(language_code)

    # Translate the widget library's own strings (dialog buttons, colour picker).
    fluent_translator = FluentTranslator(QLocale(language_code))
    app.installTranslator(fluent_translator)

    apply_appearance(settings)

    icon_path = RESOURCES / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    logger.info("Application started (language=%s)", language_code)
    logger.debug(system_info.generate_report())

    sys.exit(app.exec())


if __name__ == "__main__":
    # Required so the frozen build does not re-launch itself per worker.
    multiprocessing.freeze_support()
    run()
