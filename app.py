import sys
from pathlib import Path
from logger import logger
import system_info

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from utils.paths import ROOT, RESOURCES

def run():
    app = QApplication(sys.argv)

    stylesheet = ROOT / "ui" / "styles.qss"
    if stylesheet.exists():
        app.setStyleSheet(stylesheet.read_text())

    icon_path = RESOURCES / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    logger.info("Application started")
    logger.info(system_info.generate_report())
    sys.exit(app.exec())