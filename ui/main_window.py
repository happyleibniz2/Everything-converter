from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from logger import logger
from registry import CONVERTERS, find_converters, search_converters


class DropArea(QFrame):
    """Large central drop target for files."""

    files_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon_label = QLabel("📄")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setObjectName("dropIcon")

        title_label = QLabel("Drop files here")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setObjectName("dropTitle")

        or_label = QLabel("or")
        or_label.setAlignment(Qt.AlignCenter)

        browse_label = QLabel("Click to browse")
        browse_label.setAlignment(Qt.AlignCenter)
        browse_label.setObjectName("browseLabel")

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(or_label)
        layout.addWidget(browse_label)

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


class SettingsDialog(QDialog):
    """Placeholder settings window for Stage 1."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")

        layout = QFormLayout(self)
        layout.addRow("Theme", QLabel("System default"))
        layout.addRow("Language", QLabel("English"))
        layout.addRow("Output Folder", QLabel("Same as input file"))

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addRow(close_button)


class AboutDialog(QDialog):
    """Application information window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Everything Converter")

        layout = QFormLayout(self)
        layout.addRow(QLabel("Everything Converter"))
        layout.addRow("Version", QLabel("0.1.0"))
        layout.addRow("Author", QLabel("Everything Converter Team"))
        layout.addRow("Qt", QLabel("PySide6"))
        layout.addRow("Python", QLabel("3.12+"))
        layout.addRow("FFmpeg", QLabel("Bundled"))

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addRow(close_button)


class MainWindow(QMainWindow):
    """Main application shell for Everything Converter."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Everything Converter")
        self.resize(1100, 700)
        self.selected_files = []
        self.available_converters = list(CONVERTERS)

        self._create_actions()
        self._create_menu_bar()
        self._create_tool_bar()
        self._create_status_bar()
        self._create_central_ui()

    def _create_actions(self):
        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.close)

        self.open_action = QAction("Open", self)
        self.open_action.triggered.connect(self.browse_files)

        self.convert_action = QAction("Convert", self)
        self.convert_action.triggered.connect(self.convert_selected_files)

        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.show_settings)

        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self.show_about)

    def _create_menu_bar(self):
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.exit_action)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction(self.settings_action)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.about_action)

    def _create_tool_bar(self):
        toolbar = QToolBar("Main Toolbar", self)
        self.addToolBar(toolbar)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.convert_action)
        toolbar.addAction(self.settings_action)

    def _create_status_bar(self):
        status_bar = QStatusBar(self)
        self.setStatusBar(status_bar)
        status_bar.showMessage("Ready")
        status_bar.addPermanentWidget(QLabel("v0.1.0"))

    def _create_central_ui(self):
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(180)
        self.sidebar.addItems([
            "⭐ Favorites",
            "🖼 Images",
            "🎥 Video",
            "🎵 Audio",
            "📄 PDF",
            "📦 Archives",
            "📊 Office",
            "📝 Text",
            "🎨 Color",
            "📏 Units",
            "⚙ Others",
        ])

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search conversions...")
        self.search_bar.textChanged.connect(self.refresh_converter_list)

        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self.handle_files)
        self.drop_area.browse_requested.connect(self.browse_files)

        self.detected_extension_label = QLabel("Drop a file to detect available conversions")
        self.detected_extension_label.setObjectName("detectedExtensionLabel")

        self.converter_list = QListWidget()
        self.converter_list.setObjectName("converterList")
        self.converter_list.setMinimumHeight(110)

        content_layout.addWidget(self.search_bar)
        content_layout.addWidget(self.detected_extension_label)
        content_layout.addWidget(self.drop_area, stretch=1)
        content_layout.addWidget(QLabel("Converter List"))
        content_layout.addWidget(self.converter_list)

        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(content, stretch=1)

        self.setCentralWidget(root)

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Open files",
            "",
            "Supported files (*.png);;All files (*)",
        )
        if files:
            self.handle_files(files)

    def handle_files(self, files):
        self.selected_files = files
        detected_extensions = sorted({Path(file_name).suffix.lower() for file_name in files})
        compatible_converters = []

        for extension in detected_extensions:
            compatible_converters.extend(find_converters(extension))

        self.available_converters = list(dict.fromkeys(compatible_converters))

        if detected_extensions:
            extension_text = ", ".join(extension or "[no extension]" for extension in detected_extensions)
            self.detected_extension_label.setText(f"Detected: {extension_text}")
        else:
            self.detected_extension_label.setText("No file extension detected")

        self.refresh_converter_list()

        if self.available_converters:
            self.converter_list.setCurrentRow(0)
            self.statusBar().showMessage(f"{len(files)} file(s) ready — choose a conversion")
        else:
            self.statusBar().showMessage("No converter found")

    def refresh_converter_list(self):
        query = self.search_bar.text()
        converters = search_converters(query, self.available_converters)
        self.converter_list.clear()

        for converter in converters:
            input_extensions = ", ".join(extension.upper().lstrip(".") for extension in converter.input_extensions)
            output_extension = converter.output_extension.upper().lstrip(".")
            self.converter_list.addItem(f"{input_extensions} → {output_extension}")
            self.converter_list.item(self.converter_list.count() - 1).setData(Qt.UserRole, converter)

        if converters:
            self.converter_list.setCurrentRow(0)
        elif query:
            self.converter_list.addItem("No conversions match your search")
        else:
            self.converter_list.addItem("No conversions available for the selected file type")

    def selected_converter(self):
        current_item = self.converter_list.currentItem()
        if current_item is None:
            return None

        return current_item.data(Qt.UserRole)

    def convert_selected_files(self):
        if not self.selected_files:
            self.statusBar().showMessage("Ready")
            QMessageBox.information(self, "No files selected", "Drop files or click Open before converting.")
            return

        converter = self.selected_converter()
        if converter is None:
            self.statusBar().showMessage("No converter selected")
            QMessageBox.warning(self, "No converter selected", "Select a conversion from the list first.")
            return

        converted = 0
        errors = []
        self.statusBar().showMessage("Converting...")

        for file_name in self.selected_files:
            if Path(file_name).suffix.lower() not in converter.input_extensions:
                errors.append(f"{Path(file_name).name}: incompatible with {converter.name}")
                continue

            output_file = self._build_output_path(file_name, converter.output_extension)
            try:
                converter.convert(file_name, output_file)
                converted += 1
                logger.info("Converted %s to %s", file_name, output_file)
            except Exception as exc:
                logger.exception("Conversion failed for %s", file_name)
                errors.append(f"{Path(file_name).name}: {exc}")

        if errors:
            self.statusBar().showMessage("Error")
            QMessageBox.warning(self, "Conversion finished with errors", "\n".join(errors))
        elif converted:
            self.statusBar().showMessage("Done")
            QMessageBox.information(self, "Conversion complete", f"Converted {converted} file(s).")
        else:
            self.statusBar().showMessage("Ready")

    def _build_output_path(self, input_file, output_extension):
        source = Path(input_file)
        output = source.with_suffix(output_extension)
        counter = 1

        while output.exists():
            output = source.with_name(f"{source.stem}_{counter}{output_extension}")
            counter += 1

        return str(output)

    def show_settings(self):
        SettingsDialog(self).exec()

    def show_about(self):
        AboutDialog(self).exec()
