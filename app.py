import sys
from pathlib import Path
from logger import logger
import system_info

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def run():
    app = QApplication(sys.argv)

    stylesheet = Path("ui/styles.qss")
    if stylesheet.exists():
        app.setStyleSheet(stylesheet.read_text())

    window = MainWindow()
    window.show()

    logger.info("Application started")
    logger.info(system_info.generate_report())
    sys.exit(app.exec())