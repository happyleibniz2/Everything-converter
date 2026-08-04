# ui/error_assistant.py

import re
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter, QMessageBox, QApplication
)
from PySide6.QtGui import QFont
from lang import lang


def analyze_error(error_text: str) -> str:
    """
    Analyze the error message and return a user-friendly suggestion.
    """
    text = error_text.lower()
    suggestions = []

    # Cancellation / termination
    if re.search(r"exit\s*code\s*15|cancelled|terminated", text):
        suggestions.extend([
            lang.get("The conversion was cancelled by the user or system (exit code 15)."),
            lang.get("If you did not intentionally cancel, the process may have been terminated."),
            lang.get("Try restarting the conversion, or ensure your system has enough resources."),
        ])

    # Container / codec mismatch (flexible matching for variations)
    if "webm" in text and re.search(r"vp8|vp9|av1|vorbis|opus", text):
        suggestions.extend([
            lang.get("WebM container only supports VP8, VP9, or AV1 video codecs, and Vorbis or Opus audio."),
            lang.get("You may be encoding with an incompatible codec — choose VP8/VP9/AV1 or switch container (MP4/MKV)."),
            lang.get("Solution: Change the video codec to VP9 or VP8, or choose a different output container (e.g., MP4, MKV)."),
        ])

    # Pixel aspect ratio / header writing issues
    if re.search(r"pixel aspect ratio|invalid pixel aspect", text):
        suggestions.extend([
            lang.get("Pixel aspect ratio (SAR) may be out of range for the selected encoder."),
            lang.get("Try using a different video codec (e.g., libx264) or remove custom SAR settings."),
        ])
    if re.search(r"could not write header|incorrect codec parameters", text):
        suggestions.extend([
            lang.get("The output format may not support the selected codec combination."),
            lang.get("Ensure the codec is compatible with the container (e.g., H.264 in MP4, VP9 in WebM)."),
        ])

    # Invalid argument / general ffmpeg failures
    if re.search(r"invalid argument|invalid data|corrupt|exit code", text):
        suggestions.extend([
            lang.get("The conversion failed due to an invalid argument or corrupted input."),
            lang.get("Check the conversion settings (codec, container, bitrate, pixel format, etc.) and try again."),
        ])

    # Decoder / encoder missing
    if re.search(r"unknown encoder|encoder not found", text):
        suggestions.extend([
            lang.get("The encoder required for this format is not available in your FFmpeg build."),
            lang.get("Try choosing a different output format, or reinstall FFmpeg with more codecs."),
        ])
    if re.search(r"unknown decoder|decoder not found", text):
        suggestions.extend([
            lang.get("The decoder for the input file's codec is missing."),
            lang.get("Ensure FFmpeg has the necessary codec support, or convert the file to a more common format first."),
        ])

    # Permission / file access
    if re.search(r"permission denied|access denied", text):
        suggestions.extend([
            lang.get("The application lacks write permission to the output folder."),
            lang.get("Check folder permissions, run the app as administrator, or choose a different output location."),
        ])
    if re.search(r"no such file|cannot open|not found", text):
        suggestions.extend([
            lang.get("The input file could not be found or opened."),
            lang.get("Verify the file path and that the file exists."),
        ])

    # Resource issues
    if re.search(r"memory|alloc|out of memory", text):
        suggestions.extend([
            lang.get("The system may be out of memory or resources."),
            lang.get("Close other programs, reduce the number of concurrent conversions, or restart the application."),
        ])

    # Timeout / interrupted progress
    progress_indicators = ["progress=continue", "frame=", "fps=", "bitrate=", "speed=", "out_time=", "total_size="]
    has_progress = any(ind in text for ind in progress_indicators)
    has_error_keywords = any(kw in text for kw in ["error", "invalid", "unknown", "permission", "cannot", "not found", "memory", "alloc", "timeout", "pixel format"]) 
    if has_progress and not has_error_keywords and not re.search(r"exit\s*code|cancelled|terminated", text):
        suggestions.extend([
            lang.get("The conversion appears to have been interrupted or terminated prematurely (no specific error detected)."),
            lang.get("This could be due to manual cancellation, system resource issues, or a timeout."),
            lang.get("Try converting again, or check system logs for more details."),
        ])

    # Bitrate / pixel format hints
    if re.search(r"pixel format|pix fmt", text):
        suggestions.extend([
            lang.get("There is an issue with the pixel format of the video."),
            lang.get("Try using a different output format, or set a specific pixel format via extra arguments."),
        ])
    if re.search(r"bitrate.*(invalid|error|not supported|wrong)", text):
        suggestions.extend([
            lang.get("There might be a problem with the requested bitrate."),
            lang.get("Adjust the bitrate settings or use a preset that works for your source."),
        ])

    if not suggestions:
        suggestions.extend([
            lang.get("No specific suggestions available. Please check the error details and logs."),
            lang.get("You may also search online for the error message."),
        ])

    # Remove duplicates while preserving order
    unique = []
    for s in suggestions:
        if s not in unique:
            unique.append(s)
    return "\n".join(unique)


def extract_file_name(error_line: str) -> str:
    """Extract a file name from the error line."""
    match = re.match(r'^([^:]+\.\w+)\s*:', error_line.strip())
    if match:
        return match.group(1)
    match = re.search(r'Error processing\s+([^\s]+)', error_line, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'Cannot open\s+([^\s]+)', error_line, re.IGNORECASE)
    if match:
        return match.group(1)
    return lang.get("Unknown file")


class ErrorAssistant(QDialog):
    retry_requested = Signal(list)

    def __init__(self, errors, parent=None):
        super().__init__(parent)
        self.errors = errors
        self.setWindowTitle(lang.get("Error Assistant"))
        self.resize(950, 650)
        self.setModal(True)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        title = QLabel(lang.get("Conversion Errors"))
        title.setFont(QFont("Arial", 14, QFont.Bold))
        main_layout.addWidget(title)

        info = QLabel(f"{len(self.errors)} {lang.get('error(s) occurred. Click an error to see details and suggestions.')}")
        info.setWordWrap(True)
        main_layout.addWidget(info)

        splitter = QSplitter(Qt.Horizontal)

        self.error_list = QListWidget()
        self.error_list.itemClicked.connect(self.on_error_selected)
        for err in self.errors:
            file_name = extract_file_name(err)
            if file_name == lang.get("Unknown file"):
                display_text = err[:40] + "..." if len(err) > 40 else err
            else:
                display_text = file_name
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, err)
            item.setToolTip(err)
            self.error_list.addItem(item)
        splitter.addWidget(self.error_list)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        sugg_label = QLabel(f"💡 {lang.get('Suggestions')}")
        sugg_label.setFont(QFont("Arial", 12, QFont.Bold))
        right_layout.addWidget(sugg_label)

        self.suggestions_text = QTextEdit()
        self.suggestions_text.setReadOnly(True)
        self.suggestions_text.setPlaceholderText(lang.get("Select an error to see suggestions"))
        self.suggestions_text.setStyleSheet("""
            QTextEdit {
                background: #f0f7ff;
                border: 1px solid #aac0e8;
                border-radius: 6px;
                padding: 8px;
                font-size: 11pt;
            }
        """)
        self.suggestions_text.setMinimumHeight(120)
        self.suggestions_text.setMaximumHeight(200)
        right_layout.addWidget(self.suggestions_text)

        detail_label = QLabel(lang.get("Error Details"))
        detail_label.setFont(QFont("Arial", 10, QFont.Bold))
        right_layout.addWidget(detail_label)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setPlaceholderText(lang.get("Select an error to view the full stack"))
        self.details_text.setStyleSheet("QTextEdit { font-family: monospace; font-size: 9pt; }")
        right_layout.addWidget(self.details_text)

        splitter.addWidget(right_panel)
        splitter.setSizes([220, 730])

        main_layout.addWidget(splitter)

        btn_layout = QHBoxLayout()
        copy_btn = QPushButton(lang.get("Copy Error"))
        copy_btn.clicked.connect(self.copy_error)
        copy_all_btn = QPushButton(lang.get("Copy All Errors"))
        copy_all_btn.clicked.connect(self.copy_all)
        close_btn = QPushButton(lang.get("Close"))
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(copy_all_btn)
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

        if self.error_list.count() > 0:
            self.error_list.setCurrentRow(0)
            self.on_error_selected(self.error_list.item(0))

    def on_error_selected(self, item):
        error_text = item.data(Qt.UserRole)
        suggestion = analyze_error(error_text)
        self.suggestions_text.setPlainText(suggestion)
        self.details_text.setPlainText(error_text)

    def copy_error(self):
        item = self.error_list.currentItem()
        if item:
            error_text = item.data(Qt.UserRole)
            clipboard = QApplication.clipboard()
            clipboard.setText(error_text)
            QMessageBox.information(self, lang.get("Copied"), lang.get("Error details copied to clipboard."))

    def copy_all(self):
        clipboard = QApplication.clipboard()
        clipboard.setText("\n\n".join(self.errors))
        QMessageBox.information(self, lang.get("Copied"), lang.get("All errors copied to clipboard."))