"""Shown when the queue is empty.

An empty table with column headers tells the user nothing about what to do next.
This states the value proposition and offers the two ways in.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, FluentIcon, IconWidget, PushButton, SubtitleLabel, TitleLabel,
)

import lang


class EmptyState(QWidget):
    """Friendly placeholder with primary calls to action."""

    browse_requested = Signal()
    folder_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6)

        self.icon = IconWidget(FluentIcon.MEDIA, self)
        self.icon.setFixedSize(44, 44)
        layout.addWidget(self.icon, 0, Qt.AlignCenter)
        layout.addSpacing(6)

        self.title = SubtitleLabel(lang.lang.get("Your queue is empty"), self)
        self.title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title)

        self.subtitle = BodyLabel(
            lang.lang.get("Add images, video or audio and convert them all at once."), self
        )
        self.subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.subtitle)
        layout.addSpacing(12)

        buttons = QHBoxLayout()
        buttons.setAlignment(Qt.AlignCenter)
        buttons.setSpacing(8)

        self.browse_button = PushButton(
            FluentIcon.DOCUMENT.icon(), lang.lang.get("Choose files"), self
        )
        self.browse_button.clicked.connect(self.browse_requested)

        self.folder_button = PushButton(
            FluentIcon.FOLDER.icon(), lang.lang.get("Add a folder"), self
        )
        self.folder_button.clicked.connect(self.folder_requested)

        buttons.addWidget(self.browse_button)
        buttons.addWidget(self.folder_button)
        layout.addLayout(buttons)

    def retranslate(self):
        self.title.setText(lang.lang.get("Your queue is empty"))
        self.subtitle.setText(
            lang.lang.get("Add images, video or audio and convert them all at once.")
        )
        self.browse_button.setText(lang.lang.get("Choose files"))
        self.folder_button.setText(lang.lang.get("Add a folder"))
