"""Small painted badges used across the app (rank pills, lock hints).

Drawn rather than composed of labels so they can be dropped into table cells,
navigation rows and card headers without fighting layout margins.
"""

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget

from qfluentwidgets import getFont, isDarkTheme

from services.ranks import Rank


class RankBadge(QWidget):
    """A rounded pill showing a rank's short label in the rank's own colour."""

    clicked = Signal()

    def __init__(self, rank: Rank, parent=None, scale: float = 1.0):
        super().__init__(parent)
        self._rank = rank
        self._scale = scale
        self.setCursor(Qt.PointingHandCursor)
        self.set_size_for_rank()

    def set_rank(self, rank: Rank) -> None:
        self._rank = rank
        self.set_size_for_rank()
        self.update()

    @property
    def rank(self) -> Rank:
        return self._rank

    def _font(self):
        font = getFont(9 if self._scale < 1 else 10)
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def sizeHint(self):
        metrics = QFontMetrics(self._font())
        width = metrics.horizontalAdvance(self._rank.badge) + int(20 * self._scale)
        height = int(22 * self._scale)
        return QSize(max(width, 44), max(height, 18))

    def set_size_for_rank(self) -> None:
        self.setFixedSize(self.sizeHint())

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

        red, green, blue = self._rank.color
        accent = QColor(red, green, blue)
        if isDarkTheme():
            accent = accent.lighter(150)

        background = QColor(accent)
        background.setAlpha(48 if isDarkTheme() else 36)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, radius, radius)

        # A thin ring keeps light silver/gold readable on white backgrounds.
        ring = QColor(accent)
        ring.setAlpha(150)
        pen = painter.pen()
        pen.setColor(ring)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        font = getFont(9 if self._scale < 1 else 10)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(accent)
        painter.drawText(rect, Qt.AlignCenter, self._rank.badge)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
