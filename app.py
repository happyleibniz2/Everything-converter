import sys
import multiprocessing
from pathlib import Path
from logger import logger
import system_info
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from utils.paths import ROOT, RESOURCES
from PySide6.QtCore import QSettings
from lang import lang

def run():
    app = QApplication(sys.argv)

    # Set default settings if not present
    settings = QSettings("EverythingConverter", "Settings")
    if not settings.contains("threads"):
        cpu_count = multiprocessing.cpu_count()
        recommended = max(1, cpu_count // 2) if cpu_count <= 4 else cpu_count // 2
        settings.setValue("threads", recommended)

    # Load language from settings
    if not settings.contains("language"):
        settings.setValue("language", "en_US")
    lang_code = settings.value("language", "en_US", type=str)
    lang.load_language(lang_code)

    # Load stylesheet (light) – explicit UTF-8 encoding
    stylesheet = ROOT / "ui" / "styles.qss"
    if stylesheet.exists():
        app.setStyleSheet(stylesheet.read_text(encoding='utf-8'))

    icon_path = RESOURCES / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    logger.info("Application started")
    logger.info(system_info.generate_report())
    sys.exit(app.exec())

if __name__ == "__main__":
    run()