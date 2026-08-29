"""Live batch status panel.

Appears beneath the queue while a batch runs, so the user keeps seeing their
files instead of being thrown onto a separate progress screen. Replaces the old
full-page ``QStackedWidget`` swap.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, ProgressBar, ProgressRing,
    PushButton, SimpleCardWidget, StrongBodyLabel, TransparentToolButton,
)

import lang
from utils.formatter import format_clock, format_eta, format_speed


class ProgressDock(SimpleCardWidget):
    """Aggregate progress, throughput, ETA and batch controls."""

    pause_toggled = Signal(bool)     # True when the user asked to pause
    cancel_requested = Signal()
    dismiss_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._finished = False
        self._build_ui()
        self.reset()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(14)

        self.ring = ProgressRing(self)
        self.ring.setFixedSize(52, 52)
        self.ring.setStrokeWidth(5)
        self.ring.setTextVisible(True)
        top.addWidget(self.ring, 0, Qt.AlignVCenter)

        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        self.title_label = StrongBodyLabel(lang.lang.get("Converting…"), self)
        self.subtitle_label = CaptionLabel("", self)
        self.subtitle_label.setWordWrap(False)
        text_column.addWidget(self.title_label)
        text_column.addWidget(self.subtitle_label)
        top.addLayout(text_column, 1)

        self.pause_button = PushButton(FluentIcon.PAUSE.icon(), lang.lang.get("Pause"), self)
        self.pause_button.clicked.connect(self._on_pause_clicked)

        self.cancel_button = PushButton(FluentIcon.CANCEL.icon(), lang.lang.get("Cancel"), self)
        self.cancel_button.clicked.connect(self.cancel_requested)

        self.dismiss_button = TransparentToolButton(FluentIcon.CLOSE, self)
        self.dismiss_button.setToolTip(lang.lang.get("Hide"))
        self.dismiss_button.clicked.connect(self.dismiss_requested)

        top.addWidget(self.pause_button, 0, Qt.AlignVCenter)
        top.addWidget(self.cancel_button, 0, Qt.AlignVCenter)
        top.addWidget(self.dismiss_button, 0, Qt.AlignVCenter)
        outer.addLayout(top)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        outer.addWidget(self.progress_bar)

        stats = QGridLayout()
        stats.setHorizontalSpacing(24)
        stats.setVerticalSpacing(1)
        self._stat_widgets = {}
        for column, (key, caption) in enumerate([
            ("elapsed", "Elapsed"),
            ("remaining", "Remaining"),
            ("speed", "Throughput"),
            ("completed", "Completed"),
        ]):
            caption_label = CaptionLabel(lang.lang.get(caption), self)
            caption_label.setObjectName(f"caption_{key}")
            value_label = BodyLabel("—", self)
            stats.addWidget(caption_label, 0, column)
            stats.addWidget(value_label, 1, column)
            self._stat_widgets[key] = (caption_label, value_label)
        stats.setColumnStretch(4, 1)
        outer.addLayout(stats)

    # ---------- state ----------
    def reset(self):
        self._paused = False
        self._finished = False
        self.ring.setValue(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setPaused(False)
        self.progress_bar.setError(False)
        self.title_label.setText(lang.lang.get("Converting…"))
        self.subtitle_label.setText("")
        for key in self._stat_widgets:
            self._set_stat(key, "—")
        self.pause_button.setText(lang.lang.get("Pause"))
        self.pause_button.setIcon(FluentIcon.PAUSE.icon())
        self.pause_button.setVisible(True)
        self.pause_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.dismiss_button.setVisible(False)

    def _set_stat(self, key, text):
        widgets = self._stat_widgets.get(key)
        if widgets:
            widgets[1].setText(text)

    def _on_pause_clicked(self):
        self._paused = not self._paused
        self.progress_bar.setPaused(self._paused)
        if self._paused:
            self.pause_button.setText(lang.lang.get("Resume"))
            self.pause_button.setIcon(FluentIcon.PLAY.icon())
            self.title_label.setText(lang.lang.get("Paused"))
        else:
            self.pause_button.setText(lang.lang.get("Pause"))
            self.pause_button.setIcon(FluentIcon.PAUSE.icon())
            self.title_label.setText(lang.lang.get("Converting…"))
        self.pause_toggled.emit(self._paused)

    # ---------- updates from the coordinator ----------
    def set_progress(self, percent: int):
        self.ring.setValue(percent)
        self.progress_bar.setValue(percent)

    def set_counts(self, completed: int, failed: int, total: int):
        text = f"{completed} / {total}"
        if failed:
            text += f"  ({failed} {lang.lang.get('failed')})"
        self._set_stat("completed", text)

    def set_stats(self, bytes_per_second: float, elapsed: float, eta: float):
        self._set_stat("elapsed", format_clock(elapsed))
        self._set_stat("remaining", format_eta(eta) if eta > 0 else "—")
        self._set_stat("speed", format_speed(bytes_per_second))

    def set_active_files(self, names):
        """Show which files are in flight right now (batches run in parallel)."""
        if not names:
            self.subtitle_label.setText("")
            return
        shown = ", ".join(names[:2])
        if len(names) > 2:
            shown += f" +{len(names) - 2}"
        self.subtitle_label.setText(shown)

    def finish(self, succeeded: int, failed: int, cancelled: int):
        self._finished = True
        self.ring.setValue(100)
        self.progress_bar.setValue(100)
        self.progress_bar.setPaused(False)
        self.progress_bar.setError(bool(failed))

        if cancelled and not succeeded:
            self.title_label.setText(lang.lang.get("Conversion cancelled"))
        elif failed:
            self.title_label.setText(lang.lang.get("Finished with errors"))
        else:
            self.title_label.setText(lang.lang.get("Conversion complete"))

        parts = [f"{succeeded} {lang.lang.get('succeeded')}"]
        if failed:
            parts.append(f"{failed} {lang.lang.get('failed')}")
        if cancelled:
            parts.append(f"{cancelled} {lang.lang.get('cancelled')}")
        self.subtitle_label.setText(" · ".join(parts))

        self.pause_button.setVisible(False)
        self.cancel_button.setVisible(False)
        self.dismiss_button.setVisible(True)

    def retranslate(self):
        for key, caption in [
            ("elapsed", "Elapsed"),
            ("remaining", "Remaining"),
            ("speed", "Throughput"),
            ("completed", "Completed"),
        ]:
            widgets = self._stat_widgets.get(key)
            if widgets:
                widgets[0].setText(lang.lang.get(caption))
        self.dismiss_button.setToolTip(lang.lang.get("Hide"))
        if not self._finished:
            self.pause_button.setText(
                lang.lang.get("Resume") if self._paused else lang.lang.get("Pause")
            )
            self.cancel_button.setText(lang.lang.get("Cancel"))
            self.title_label.setText(
                lang.lang.get("Paused") if self._paused else lang.lang.get("Converting…")
            )
