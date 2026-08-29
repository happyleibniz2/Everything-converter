"""Explains conversion failures in terms a user can act on.

ffmpeg's stderr is written for developers. This maps the common failure patterns
onto concrete next steps, and keeps the raw output available for the cases the
heuristics miss.
"""

import re
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, ListWidget, MessageBoxBase,
    PushButton, StrongBodyLabel, SubtitleLabel, TextEdit,
)

import lang

# (regex, [advice keys]). Ordered most-specific first; all matches contribute.
DIAGNOSTICS: List[Tuple[str, List[str]]] = [
    (r"unknown encoder|encoder not found", [
        "The encoder this format needs is not available in the bundled FFmpeg.",
        "Pick a different output format, such as MP4 with H.264.",
    ]),
    (r"unknown decoder|decoder not found", [
        "The input file uses a codec this FFmpeg build cannot read.",
        "Convert it to a common format first, or try a different source file.",
    ]),
    (r"permission denied|access is denied", [
        "The app is not allowed to write to the destination folder.",
        "Choose a different output folder in Settings, or run as administrator.",
    ]),
    (r"no such file|cannot find the file|does not exist", [
        "The source file was moved, renamed or deleted after it was queued.",
        "Remove it from the queue and add it again.",
    ]),
    (r"no space left|disk full", [
        "The destination drive is out of free space.",
        "Free some space or pick another drive, then retry.",
    ]),
    (r"could not write header|incorrect codec parameters|invalid argument", [
        "The chosen codec is not compatible with the output container.",
        "Use H.264 for MP4, VP9 for WebM, or enable Remux only if the streams already match.",
    ]),
    (r"webm.*(vp8|vp9|av1|vorbis|opus)|(\bvp8\b|\bvp9\b).*webm", [
        "WebM only accepts VP8, VP9 or AV1 video with Vorbis or Opus audio.",
        "Switch the codec to VP9, or choose MP4 or MKV instead.",
    ]),
    (r"pixel format|pix_fmt", [
        "The pixel format is not supported by this encoder.",
        "Add -pix_fmt yuv420p under Advanced, which is the most widely compatible choice.",
    ]),
    (r"invalid data|corrupt|moov atom not found", [
        "The source file appears to be incomplete or corrupted.",
        "Try playing it first to confirm it is intact.",
    ]),
    (r"out of memory|cannot allocate", [
        "The system ran out of memory during encoding.",
        "Lower 'Files at once' in Settings, or close other applications.",
    ]),
    (r"height not divisible by 2|width not divisible by 2", [
        "H.264 requires even pixel dimensions.",
        "Choose a standard resolution preset, or use a scale value ending in -2.",
    ]),
    (r"cancelled|exit code 15|terminated", [
        "This conversion was stopped before it finished.",
        "Retry it if that was not intentional.",
    ]),
]

FALLBACK_ADVICE = [
    "No specific diagnosis is available for this error.",
    "Check the raw output below, and the log files listed in Settings.",
]


def analyze_error(error_text: str) -> List[str]:
    """Return ordered, de-duplicated advice for one error message."""
    text = str(error_text or "").lower()
    advice: List[str] = []

    for pattern, suggestions in DIAGNOSTICS:
        if re.search(pattern, text):
            for suggestion in suggestions:
                translated = lang.lang.get(suggestion)
                if translated not in advice:
                    advice.append(translated)

    if not advice:
        advice = [lang.lang.get(item) for item in FALLBACK_ADVICE]
    return advice


class ErrorAssistant(MessageBoxBase):
    """Lists failures with a diagnosis and the raw output for each."""

    def __init__(self, failures, parent=None):
        """``failures`` is a sequence of ``(filename, error_message)``."""
        super().__init__(parent)
        self.failures = [
            (name, message) for name, message in (failures or []) if message
        ]
        self._build()
        self.yesButton.setText(lang.lang.get("Close"))
        self.cancelButton.hide()
        self.widget.setMinimumWidth(780)

        if self.failures:
            self.list_widget.setCurrentRow(0)
            self._show_failure(0)

    def _build(self):
        self.viewLayout.setSpacing(10)

        self.viewLayout.addWidget(
            SubtitleLabel(f"{len(self.failures)} {lang.lang.get('conversion(s) failed')}", self)
        )
        self.viewLayout.addWidget(
            CaptionLabel(lang.lang.get("Select a file to see what went wrong."), self)
        )

        body = QHBoxLayout()
        body.setSpacing(12)

        self.list_widget = ListWidget(self)
        self.list_widget.setFixedWidth(210)
        for name, _message in self.failures:
            self.list_widget.addItem(QListWidgetItem(name))
        self.list_widget.currentRowChanged.connect(self._show_failure)
        body.addWidget(self.list_widget)

        detail = QWidget(self)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)

        detail_layout.addWidget(StrongBodyLabel(lang.lang.get("What to try"), detail))
        self.advice_label = BodyLabel("", detail)
        self.advice_label.setWordWrap(True)
        self.advice_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.advice_label)

        detail_layout.addWidget(CaptionLabel(lang.lang.get("Raw output"), detail))
        self.raw_output = TextEdit(detail)
        self.raw_output.setReadOnly(True)
        self.raw_output.setMinimumHeight(150)
        detail_layout.addWidget(self.raw_output)

        copy_row = QHBoxLayout()
        copy_row.addStretch(1)
        self.copy_button = PushButton(FluentIcon.COPY.icon(), lang.lang.get("Copy details"), detail)
        self.copy_button.clicked.connect(self._copy_current)
        copy_row.addWidget(self.copy_button)
        detail_layout.addLayout(copy_row)

        body.addWidget(detail, 1)
        self.viewLayout.addLayout(body)

    def _show_failure(self, row):
        if not (0 <= row < len(self.failures)):
            return
        _name, message = self.failures[row]
        advice = analyze_error(message)
        self.advice_label.setText("\n".join(f"\u2022  {item}" for item in advice))
        self.raw_output.setPlainText(message)

    def _copy_current(self):
        row = self.list_widget.currentRow()
        if not (0 <= row < len(self.failures)):
            return
        name, message = self.failures[row]
        advice = "\n".join(analyze_error(message))
        QApplication.clipboard().setText(f"{name}\n\n{advice}\n\n{message}")
        self.copy_button.setText(lang.lang.get("Copied"))
