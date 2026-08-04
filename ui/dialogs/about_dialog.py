import platform

from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QPushButton

import lang
from system_info import APP_VERSION, BUILD_TYPE, ffmpeg_version


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(lang.lang.get("About Everything Converter"))
        self.resize(420, 320)

        layout = QFormLayout(self)
        title = QLabel(f"<b>{lang.lang.get('EverythingConverter')}</b>")
        title.setTextFormat(Qt.RichText)
        layout.addRow(title)
        layout.addRow(lang.lang.get("Version"), QLabel(APP_VERSION))
        layout.addRow(lang.lang.get("Build"), QLabel(BUILD_TYPE))
        layout.addRow(lang.lang.get("Python"), QLabel(platform.python_version()))
        layout.addRow(lang.lang.get("Qt"), QLabel(qVersion()))
        layout.addRow(lang.lang.get("FFmpeg"), QLabel(ffmpeg_version()))
        homepage = QLabel('<a href="https://example.com">https://example.com</a>')
        homepage.setOpenExternalLinks(True)
        layout.addRow(lang.lang.get("Homepage"), homepage)
        layout.addRow(lang.lang.get("License"), QLabel("MIT"))

        close_button = QPushButton(lang.lang.get("Close"))
        close_button.clicked.connect(self.accept)
        layout.addRow(close_button)