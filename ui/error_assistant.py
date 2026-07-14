# ui/error_assistant.py

import re
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QSplitter, QMessageBox, QApplication, QFrame
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import QSize


def analyze_error(error_text: str) -> str:
    """
    Analyze the error message and return a user-friendly suggestion.
    """
    text = error_text.lower()
    suggestions = []

    # 1. Check for cancellation (exit code 15 or 4294967274? 15 is typical)
    if "exit code 15" in text or "cancelled" in text:
        suggestions.append("The conversion was cancelled by the user or system (exit code 15).")
        suggestions.append("If you did not intentionally cancel, the process may have been terminated.")
        suggestions.append("Try restarting the conversion, or ensure your system has enough resources.")

    # 2. Container/codec mismatch detection (crucial for WebM/MP4/MKV issues)
    if "only vp8 or vp9 or av1 video and vorbis or opus audio are supported for webm" in text:
        suggestions.append("WebM container only supports VP8, VP9, or AV1 video codecs, and Vorbis or Opus audio.")
        suggestions.append("You are trying to encode with a different video codec (e.g., libxvid, libx264).")
        suggestions.append("Solution: Change the video codec to VP9 or VP8, or choose a different output container (e.g., MP4, MKV).")
    if "only vp8 or vp9 video and vorbis or opus audio are supported for webm" in text:
        suggestions.append("WebM only supports VP8/VP9 video and Vorbis/Opus audio. Please select a compatible codec.")
        suggestions.append("Switch to VP9 or use MP4/MKV container instead.")
    if "invalid pixel aspect ratio" in text:
        suggestions.append("Pixel aspect ratio (SAR) exceeds the limit (255/255) for the chosen encoder.")
        suggestions.append("Try using a different video codec (e.g., libx264) or remove custom SAR settings.")
    if "could not write header (incorrect codec parameters)" in text:
        suggestions.append("The output format does not support the selected codec combination.")
        suggestions.append("Ensure the codec is compatible with the container (e.g., H.264 in MP4, VP9 in WebM).")

    # 3. Detect invalid argument (exit code -22 or its unsigned equivalent 4294967274)
    if "exit code 4294967274" in text or "invalid argument" in text:
        suggestions.append("The conversion failed due to an invalid argument (exit code -22).")
        suggestions.append("This often means an unsupported codec/container combination or an incorrect parameter.")
        suggestions.append("Check the conversion settings (codec, container, bitrate, pixel format, etc.) and try again.")

    # 4. If the error text consists mostly of progress output and no typical error keywords,
    #    it's likely an interruption.
    progress_indicators = ["progress=continue", "frame=", "fps=", "bitrate=", "speed=", "out_time=", "total_size="]
    has_progress = any(ind in text for ind in progress_indicators)
    has_error_keywords = any(kw in text for kw in ["error", "invalid", "unknown", "permission", "cannot", "not found",
                                                   "memory", "alloc", "timeout", "pixel format", "only vp8"])
    if has_progress and not has_error_keywords and not any(kw in text for kw in ["exit code", "cancelled"]):
        suggestions.append("The conversion appears to have been interrupted or terminated prematurely (no specific error detected).")
        suggestions.append("This could be due to manual cancellation, system resource issues, or a timeout.")
        suggestions.append("Try converting again, or check system logs for more details.")

    # 5. Other specific errors (avoid false positives)
    if "invalid data" in text or "corrupt" in text:
        suggestions.append("The input file seems corrupted or is not a valid media file.")
        suggestions.append("Try opening the file in a media player to verify it's playable, or use a different source file.")
    if "unknown encoder" in text:
        suggestions.append("The encoder required for this format is not available in your FFmpeg build.")
        suggestions.append("Try choosing a different output format, or reinstall FFmpeg with more codecs.")
    if "unknown decoder" in text:
        suggestions.append("The decoder for the input file's codec is missing.")
        suggestions.append("Ensure FFmpeg has the necessary codec support, or convert the file to a more common format first.")
    if "permission denied" in text:
        suggestions.append("The application lacks write permission to the output folder.")
        suggestions.append("Check folder permissions, run the app as administrator, or choose a different output location.")
    if "no such file" in text or "cannot open" in text:
        suggestions.append("The input file could not be found or opened.")
        suggestions.append("Verify the file path and that the file exists.")
    if "codec" in text and "not found" in text:
        suggestions.append("The required codec is not installed or not supported.")
        suggestions.append("Install additional codec packs or choose a different format.")
    if "memory" in text or "alloc" in text:
        suggestions.append("The system may be out of memory or resources.")
        suggestions.append("Close other programs, reduce the number of concurrent conversions, or restart the application.")
    if "timeout" in text:
        suggestions.append("The conversion took too long and was interrupted.")
        suggestions.append("Try a smaller file or increase the timeout limit in settings.")
    if "pixel format" in text:
        suggestions.append("There is an issue with the pixel format of the video.")
        suggestions.append("Try using a different output format, or set a specific pixel format via extra arguments.")
    if "bitrate" in text and any(kw in text for kw in ["invalid", "error", "not supported", "wrong"]):
        suggestions.append("There might be a problem with the requested bitrate.")
        suggestions.append("Adjust the bitrate settings or use a preset that works for your source.")

    if not suggestions:
        suggestions.append("No specific suggestions available. Please check the error details and logs.")
        suggestions.append("You may also search online for the error message.")

    # Remove duplicates
    unique = []
    for s in suggestions:
        if s not in unique:
            unique.append(s)
    return "\n".join(unique)


def extract_file_name(error_line: str) -> str:
    """
    Extract a file name from the error line.
    Tries to find a pattern like "filename.mp4: ..." or "Error processing filename".
    """
    # Pattern 1: "filename: ..." where filename has a common extension
    match = re.match(r'^([^:]+\.\w+)\s*:', error_line.strip())
    if match:
        return match.group(1)

    # Pattern 2: "Error processing filename"
    match = re.search(r'Error processing\s+([^\s]+)', error_line, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: "Cannot open filename"
    match = re.search(r'Cannot open\s+([^\s]+)', error_line, re.IGNORECASE)
    if match:
        return match.group(1)

    return "Unknown file"


class ErrorAssistant(QDialog):
    """
    A dialog that displays conversion errors and provides helpful suggestions.
    """
    retry_requested = pyqtSignal(list)

    def __init__(self, errors, parent=None):
        super().__init__(parent)
        self.errors = errors
        self.setWindowTitle("Error Assistant")
        self.resize(950, 650)          # Slightly bigger
        self.setModal(True)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Header
        title = QLabel("Conversion Errors")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        main_layout.addWidget(title)

        info = QLabel(f"{len(self.errors)} error(s) occurred. Click an error to see details and suggestions.")
        info.setWordWrap(True)
        main_layout.addWidget(info)

        # Main splitter (left: list, right: suggestions + details)
        splitter = QSplitter(Qt.Horizontal)

        # Left: error list
        self.error_list = QListWidget()
        self.error_list.itemClicked.connect(self.on_error_selected)
        for err in self.errors:
            file_name = extract_file_name(err)
            if file_name == "Unknown file":
                display_text = err[:40] + "..." if len(err) > 40 else err
            else:
                display_text = file_name
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, err)
            item.setToolTip(err)
            self.error_list.addItem(item)
        splitter.addWidget(self.error_list)

        # Right panel: suggestions on top, error details below
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # --- Suggestions area (prominent) ---
        sugg_label = QLabel("💡 Suggestions")
        sugg_label.setFont(QFont("Arial", 12, QFont.Bold))
        right_layout.addWidget(sugg_label)

        self.suggestions_text = QTextEdit()
        self.suggestions_text.setReadOnly(True)
        self.suggestions_text.setPlaceholderText("Select an error to see suggestions")
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

        # --- Error details area (scrollable) ---
        detail_label = QLabel("Error Details")
        detail_label.setFont(QFont("Arial", 10, QFont.Bold))
        right_layout.addWidget(detail_label)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setPlaceholderText("Select an error to view the full stack")
        self.details_text.setStyleSheet("QTextEdit { font-family: monospace; font-size: 9pt; }")
        right_layout.addWidget(self.details_text)

        splitter.addWidget(right_panel)
        splitter.setSizes([220, 730])  # left: 220, right: 730

        main_layout.addWidget(splitter)

        # Buttons at bottom
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy Error")
        copy_btn.clicked.connect(self.copy_error)
        copy_all_btn = QPushButton("Copy All Errors")
        copy_all_btn.clicked.connect(self.copy_all)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(copy_all_btn)
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

        # Select first error by default
        if self.error_list.count() > 0:
            self.error_list.setCurrentRow(0)
            self.on_error_selected(self.error_list.item(0))

    def on_error_selected(self, item):
        error_text = item.data(Qt.UserRole)
        suggestion = analyze_error(error_text)
        # Update suggestions area (plain text, but we can keep it simple)
        self.suggestions_text.setPlainText(suggestion)
        # Update details area (with monospace)
        self.details_text.setPlainText(error_text)

    def copy_error(self):
        item = self.error_list.currentItem()
        if item:
            error_text = item.data(Qt.UserRole)
            clipboard = QApplication.clipboard()
            clipboard.setText(error_text)
            QMessageBox.information(self, "Copied", "Error details copied to clipboard.")

    def copy_all(self):
        clipboard = QApplication.clipboard()
        clipboard.setText("\n\n".join(self.errors))
        QMessageBox.information(self, "Copied", "All errors copied to clipboard.")