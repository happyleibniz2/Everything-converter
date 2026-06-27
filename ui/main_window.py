from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QListWidget,
    QPushButton,
)

from registry import CONVERTERS


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Everything Converter")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        self.list = QListWidget()

        for converter in CONVERTERS:
            self.list.addItem(converter.name)

        layout.addWidget(self.list)

        layout.addWidget(QPushButton("Convert"))