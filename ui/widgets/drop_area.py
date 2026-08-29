"""The drag-and-drop target.

Custom-painted rather than stylesheet-driven so it can render a dashed border,
react to theme changes, and animate on drag-hover — none of which QSS does well.
"""

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
)
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, IconWidget, StrongBodyLabel,
    isDarkTheme, themeColor,
)

import lang

CATEGORY_ICONS = {
    "Image": FluentIcon.PHOTO,
    "Video": FluentIcon.VIDEO,
    "Audio": FluentIcon.MUSIC,
    "PDF": FluentIcon.DOCUMENT,
    "Archives": FluentIcon.ZIP_FOLDER,
    "Office": FluentIcon.DOCUMENT,
    "Favorites": FluentIcon.HEART,
}


class DropArea(QFrame):
    """Accepts dropped files and clicks to browse."""

    files_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self, parent=None, compact: bool = False):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._compact = compact
        self._hovering = False
        self._drag_active = False
        self._glow = 0.0

        self._glow_animation = QPropertyAnimation(self, b"glow", self)
        self._glow_animation.setDuration(180)
        self._glow_animation.setEasingCurve(QEasingCurve.OutCubic)

        self._build_ui()
        self._apply_mode()

    # ---------- construction ----------
    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignCenter)

        self.icon_widget = IconWidget(FluentIcon.CLOUD, self)

        self.title_label = StrongBodyLabel(lang.lang.get("Drop files here"), self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setObjectName("dropTitle")

        self.hint_label = CaptionLabel(lang.lang.get("or click to browse your computer"), self)
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setObjectName("browseLabel")

        self._row = QHBoxLayout()
        self._row.setAlignment(Qt.AlignCenter)

        self._layout.addWidget(self.icon_widget, 0, Qt.AlignCenter)
        self._layout.addWidget(self.title_label)
        self._layout.addWidget(self.hint_label)
        self._layout.addLayout(self._row)

    def _apply_mode(self):
        """Tall hero layout when the queue is empty; a slim bar once it has items."""
        if self._compact:
            self.setMinimumHeight(64)
            self.setMaximumHeight(72)
            self._layout.setContentsMargins(20, 10, 20, 10)
            self._layout.setSpacing(2)
            self.icon_widget.setFixedSize(22, 22)
            self.hint_label.setVisible(False)
        else:
            self.setMinimumHeight(190)
            self.setMaximumHeight(16777215)
            self._layout.setContentsMargins(24, 30, 24, 30)
            self._layout.setSpacing(10)
            self.icon_widget.setFixedSize(46, 46)
            self.hint_label.setVisible(True)
        self.updateGeometry()

    def set_compact(self, compact: bool):
        if compact == self._compact:
            return
        self._compact = compact
        self._apply_mode()
        self.retranslate()

    def set_icon(self, category):
        self.icon_widget.setIcon(CATEGORY_ICONS.get(category, FluentIcon.CLOUD))

    # ---------- glow animation ----------
    def get_glow(self) -> float:
        return self._glow

    def set_glow(self, value: float):
        self._glow = value
        self.update()

    glow = Property(float, get_glow, set_glow)

    def _animate_glow(self, target: float):
        self._glow_animation.stop()
        self._glow_animation.setStartValue(self._glow)
        self._glow_animation.setEndValue(target)
        self._glow_animation.start()

    # ---------- painting ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing)

        dark = isDarkTheme()
        accent = themeColor()
        radius = 10.0
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # Background: tint toward the accent colour as the glow rises.
        base = QColor(255, 255, 255, 10) if dark else QColor(255, 255, 255, 160)
        if self._glow > 0:
            tint = QColor(accent)
            tint.setAlpha(int(28 * self._glow) + (6 if dark else 12))
            painter.setBrush(tint)
        else:
            painter.setBrush(base)

        border = QColor(accent) if self._glow > 0 else (
            QColor(255, 255, 255, 40) if dark else QColor(0, 0, 0, 40)
        )
        if self._glow > 0:
            border.setAlpha(120 + int(135 * self._glow))

        pen = QPen(border, 1.6 + 0.8 * self._glow, Qt.DashLine)
        pen.setDashPattern([5, 4])
        painter.setPen(pen)
        painter.drawPath(path)

    # ---------- interaction ----------
    def enterEvent(self, event):
        self._hovering = True
        if not self._drag_active:
            self._animate_glow(0.35)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovering = False
        if not self._drag_active:
            self._animate_glow(0.0)
        super().leaveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._drag_active = True
            self._animate_glow(1.0)
            self.title_label.setText(lang.lang.get("Release to add these files"))
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drag_active = False
        self._animate_glow(0.35 if self._hovering else 0.0)
        self.retranslate()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drag_active = False
        self._animate_glow(0.0)
        self.retranslate()

        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        # Release rather than press, so a drag that starts here is not a click.
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.browse_requested.emit()
        super().mouseReleaseEvent(event)

    def retranslate(self):
        if self._compact:
            self.title_label.setText(lang.lang.get("Drop more files here, or click to browse"))
        else:
            self.title_label.setText(lang.lang.get("Drop files here"))
        self.hint_label.setText(lang.lang.get("or click to browse your computer"))
