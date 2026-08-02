from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout

import lang
from utils.paths import ICONS


class DropArea(QFrame):
    files_dropped = pyqtSignal(list)
    browse_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setObjectName("dropIcon")
        self.set_icon(None)

        self.title_label = QLabel(lang.lang.get("Drop files here"))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setObjectName("dropTitle")

        or_label = QLabel(lang.lang.get("or"))
        or_label.setAlignment(Qt.AlignCenter)

        self.browse_label = QLabel(lang.lang.get("Click to browse"))
        self.browse_label.setAlignment(Qt.AlignCenter)
        self.browse_label.setObjectName("browseLabel")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(or_label)
        layout.addWidget(self.browse_label)

    def set_icon(self, category):
        icon_map = {
            "Image": "image.svg",
            "Video": "video.svg",
            "Audio": "audio.svg",
            "PDF": "pdf.svg",
            "Archives": "archive.svg",
            "Office": "office.svg",
            "Favorites": "favorite.svg",
        }
        if category and category in icon_map:
            icon_name = icon_map[category]
        else:
            icon_name = "image.svg"

        icon_path = ICONS / icon_name
        if icon_path.exists():
            renderer = QSvgRenderer(str(icon_path))
            if renderer.isValid():
                pixmap = QPixmap(64, 64)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                self.icon_label.setPixmap(pixmap)
                return

        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        if not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(64, 64))
        else:
            self.icon_label.clear()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def retranslate(self):
        self.title_label.setText(lang.lang.get("Drop files here"))
        self.browse_label.setText(lang.lang.get("Click to browse"))
        # "or" label is not stored as attribute, find it
        for child in self.children():
            if isinstance(child, QLabel) and child.objectName() != "dropTitle" and child.objectName() != "browseLabel" and child.objectName() != "dropIcon":
                child.setText(lang.lang.get("or"))


# ---------- Settings Dialog ----------
