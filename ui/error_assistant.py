"""Explains conversion failures in terms a user can act on.

ffmpeg's stderr is written for developers. This maps the common failure patterns
onto concrete next steps, and keeps the raw output available for the cases the
heuristics miss.
"""

import re
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, ListWidget, MessageBoxBase,
    PushButton, StrongBodyLabel, SubtitleLabel, TextEdit,
)

import lang
from services.ranks import EFFORT_MAX, RankManager
from ui.widgets.badge import RankBadge

# Effort levels for the Error Assistant. Normal ranks analyze with "default"
# effort; Bronze and above (and dev mode) analyze with "max" effort, which
# enables the extended diagnostics, deeper log scanning and remediation plans.
EFFORT_DEFAULT = "default"


def current_effort() -> str:
    """The effort level the current user's rank entitles them to."""
    return RankManager.instance().error_assistant_effort

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

# Extra patterns only evaluated at MAX effort (Bronze and above, or dev mode).
# They catch subtler failure modes that the default heuristics intentionally
# skip to keep free-tier answers short and safe.
MAX_EFFORT_DIAGNOSTICS: List[Tuple[str, List[str]]] = [
    (r"nvenc|quicksync|qsv|amf|vaapi|cuda", [
        "The GPU encoder rejected this request.",
        "Update your graphics driver, lower the resolution or bitrate, or switch back to CPU encoding.",
    ]),
    (r"bit rate.*too high|exceeds.*maximum|too large for container", [
        "The chosen bitrate exceeds what the container or target format allows.",
        "Lower the bitrate or CRF, or pick a container with a higher ceiling such as MKV.",
    ]),
    (r"sample rate|channels|audio codec|resample", [
        "The audio stream conflicts with the output settings.",
        "Force a common layout with -ar 48000 -ac 2 under Advanced, or drop audio and remux.",
    ]),
    (r"timebase|timestamp|pts|dts", [
        "Timestamps in the source are inconsistent, which breaks some muxers.",
        "Enable 'Remux only' first to test, or add -fflags +genpts under Advanced.",
    ]),
    (r"thread|deadlock|assertion|segmentation", [
        "This looks like an internal FFmpeg fault rather than a settings problem.",
        "Reduce 'Files at once' in Settings and retry; if it persists, convert the file alone.",
    ]),
    (r"timeout|timed out|stalled", [
        "The conversion stalled before finishing.",
        "Check the drive the source lives on (network drives often stall), then retry from a local copy.",
    ]),
    (r"unsupported|not implemented", [
        "The requested feature combination is not supported by this FFmpeg build.",
        "Simplify the pipeline: one codec change at a time, without extra filters.",
    ]),
    (r"encrypted|drm|protected", [
        "The source file is encrypted or DRM-protected.",
        "Only unencrypted media can be converted; export a plain file from the original app first.",
    ]),
]

# Deeper follow-up steps appended to matched advice at MAX effort, keyed by
# advice line so each diagnosis gains concrete, ordered actions.
MAX_EFFORT_FOLLOWUPS = {
    "Pick a different output format, such as MP4 with H.264.":
        "Try MP4/H.264 first — it works everywhere. Then re-add your preferred codec via Advanced.",
    "Choose a different output folder in Settings, or run as administrator.":
        "Good targets: your user Downloads folder, or a second internal drive formatted NTFS/exFAT.",
    "Use H.264 for MP4, VP9 for WebM, or enable Remux only if the streams already match.":
        "Quickest path: set the codec to H.264, leave everything else on Auto, and retry just this file.",
}


def analyze_error(error_text: str, effort: Optional[str] = None) -> List[str]:
    """Return ordered, de-duplicated advice for one error message.

    ``effort`` selects how hard the assistant thinks:
      * ``"default"`` — Normal rank: the core heuristics only.
      * ``"max"``     — Bronze and above (and dev mode): core heuristics plus
        the extended diagnostics, deeper log scanning and follow-up steps.
    When omitted, the current user's rank decides.
    """
    if effort is None:
        effort = current_effort()
    max_effort = effort == EFFORT_MAX

    text = str(error_text or "").lower()
    advice: List[str] = []

    def collect(entries):
        for pattern, suggestions in entries:
            if re.search(pattern, text):
                for suggestion in suggestions:
                    translated = lang.lang.get(suggestion)
                    if translated not in advice:
                        advice.append(translated)
                        if max_effort:
                            followup = MAX_EFFORT_FOLLOWUPS.get(suggestion)
                            if followup:
                                followup = lang.lang.get(followup)
                                if followup not in advice:
                                    advice.append("   ↳ " + followup)

    collect(DIAGNOSTICS)
    if max_effort:
        # Max effort scans the whole log, not just the tail, and adds every
        # extended pattern that matches.
        collect(MAX_EFFORT_DIAGNOSTICS)

    if not advice:
        advice = [lang.lang.get(item) for item in FALLBACK_ADVICE]
        if max_effort:
            advice.append(lang.lang.get(
                "Max-effort scan found no known failure signature. "
                "Attach the raw output when contacting support for a faster answer."
            ))
    return advice


class ErrorAssistant(MessageBoxBase):
    """Lists failures with a diagnosis and the raw output for each.

    Analysis depth depends on the user's rank: Normal runs at default effort,
    Bronze/Silver/Gold (and dev mode) run at max effort — extended patterns,
    follow-up steps and a deeper log scan.
    """

    def __init__(self, failures, parent=None):
        """``failures`` is a sequence of ``(filename, error_message)``."""
        super().__init__(parent)
        self.failures = [
            (name, message) for name, message in (failures or []) if message
        ]
        self.effort = current_effort()
        self._manager = RankManager.instance()
        self._build()
        self.yesButton.setText(lang.lang.get("Close"))
        self.cancelButton.hide()
        self.widget.setMinimumWidth(780)

        if self.failures:
            self.list_widget.setCurrentRow(0)
            self._show_failure(0)

    def rank_for_badge(self):
        """The rank shown next to the header (dev mode shows the user's rank)."""
        return self._manager.rank

    def _effort_caption(self) -> str:
        if self.effort == EFFORT_MAX:
            return lang.lang.get("Error Assistant · max effort")
        return lang.lang.get(
            "Error Assistant · default effort — upgrade to Bronze for max-effort diagnosis."
        )

    def _build(self):
        self.viewLayout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(
            SubtitleLabel(f"{len(self.failures)} {lang.lang.get('conversion(s) failed')}", self)
        )
        header.addStretch(1)
        header.addWidget(RankBadge(self.rank_for_badge(), self))
        self.viewLayout.addLayout(header)
        self.effort_caption = CaptionLabel(self._effort_caption(), self)
        self.viewLayout.addWidget(self.effort_caption)
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
        advice = analyze_error(message, effort=self.effort)
        self.advice_label.setText("\n".join(f"\u2022  {item}" for item in advice))
        self.raw_output.setPlainText(message)

    def _copy_current(self):
        row = self.list_widget.currentRow()
        if not (0 <= row < len(self.failures)):
            return
        name, message = self.failures[row]
        advice = "\n".join(analyze_error(message, effort=self.effort))
        QApplication.clipboard().setText(f"{name}\n\n{advice}\n\n{message}")
        self.copy_button.setText(lang.lang.get("Copied"))
