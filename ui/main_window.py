from pathlib import Path
import platform
import time
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6 import __version__ as QT_VERSION_STR
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QBrush
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from logger import logger
from registry import CONVERTERS, find_converters, search_converters
from converters.extensions import EXTENSION_DESCRIPTIONS
from system_info import APP_VERSION, BUILD_TYPE, ffmpeg_version
from utils.paths import ICONS, RESOURCES


class ConversionWorker(QThread):
    """Worker thread for file conversions."""

    progress_updated = Signal(int)
    per_file_progress = Signal(int)
    status_message = Signal(str)
    speed_updated = Signal(str)
    current_file_updated = Signal(str)
    time_updated = Signal(str, str)
    conversion_finished = Signal(int, list)

    def __init__(self, converter, file_pairs):
        super().__init__()
        self.converter = converter
        self.file_pairs = file_pairs
        self.converted = 0
        self.errors = []
        self.is_paused = False
        self.is_cancelled = False
        self.start_time = None
        self.bytes_processed = 0

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        total_files = len(self.file_pairs)
        self.start_time = time.time()

        total_files = len(self.file_pairs)
        for index, (file_name, output_file) in enumerate(self.file_pairs, start=1):
            if self.is_cancelled:
                break

            while self.is_paused:
                time.sleep(0.1)

            self.current_file_updated.emit(Path(file_name).name)
            self.status_message.emit(f"Converting {index}/{total_files}...")

            try:
                file_size = Path(file_name).stat().st_size
                logger.info("================================================")
                logger.info("Conversion")
                logger.info("Input: %s", file_name)
                logger.info("Output: %s", output_file)
                logger.info("Converter: %s", self.converter.name)
                start_file = time.time()

                if hasattr(self.converter, "convert_with_progress"):
                    def _progress_cb(percent, elapsed_sec, remaining_sec):
                        while self.is_paused:
                            time.sleep(0.1)

                        elapsed_text = time.strftime("%H:%M:%S", time.gmtime(elapsed_sec))
                        remaining_text = time.strftime("%H:%M:%S", time.gmtime(remaining_sec)) if remaining_sec else "00:00:00"

                        try:
                            bytes_for_file = int(file_size * (percent / 100.0))
                        except Exception:
                            bytes_for_file = 0

                        total_processed = self.bytes_processed + bytes_for_file
                        total_elapsed = time.time() - self.start_time if self.start_time else elapsed_sec
                        speed_mbps = (total_processed / (1024 * 1024)) / max(total_elapsed, 0.001)

                        self.per_file_progress.emit(int(percent))
                        self.time_updated.emit(elapsed_text, remaining_text)
                        self.speed_updated.emit(f"{speed_mbps:.2f} MB/s")

                    self.converter.convert_with_progress(file_name, output_file, progress_callback=_progress_cb, should_cancel=lambda: self.is_cancelled)
                else:
                    self.converter.convert(file_name, output_file)

                duration = time.time() - start_file
                self.bytes_processed += file_size
                self.converted += 1

                logger.info("Duration: %.2f seconds", duration)
                logger.info("Success")
            except Exception as exc:
                logger.exception("Conversion failed for %s", file_name)
                self.errors.append(f"{Path(file_name).name}: {exc}")
                if self.is_cancelled:
                    self.status_message.emit("Conversion canceled")
                    break

            elapsed = time.time() - self.start_time
            remaining = 0.0
            if index > 0 and index < total_files:
                remaining = elapsed / index * (total_files - index)

            elapsed_text = time.strftime("%H:%M:%S", time.gmtime(elapsed))
            remaining_text = time.strftime("%H:%M:%S", time.gmtime(remaining))

            speed_mbps = (self.bytes_processed / (1024 * 1024)) / max(elapsed, 0.001)
            self.speed_updated.emit(f"{speed_mbps:.2f} MB/s")
            self.time_updated.emit(elapsed_text, remaining_text)
            self.progress_updated.emit(index)
            self.per_file_progress.emit(100)

        self.conversion_finished.emit(self.converted, self.errors)


class DropArea(QFrame):
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

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setObjectName("dropIcon")
        self.set_icon(None)

        title_label = QLabel("Drop files here")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setObjectName("dropTitle")

        or_label = QLabel("or")
        or_label.setAlignment(Qt.AlignCenter)

        browse_label = QLabel("Click to browse")
        browse_label.setAlignment(Qt.AlignCenter)
        browse_label.setObjectName("browseLabel")

        layout.addWidget(self.icon_label)
        layout.addWidget(title_label)
        layout.addWidget(or_label)
        layout.addWidget(browse_label)

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


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(400, 320)

        layout = QFormLayout(self)

        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.follow_system_checkbox = QCheckBox("Follow System")
        self.output_folder_combo = QComboBox()
        self.output_folder_combo.addItems(["Same folder", "Ask every time", "Custom folder"])
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "中文", "日本語"])
        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItems(["Rename", "Overwrite", "Skip"])
        self.logging_combo = QComboBox()
        self.logging_combo.addItems(["Verbose", "Normal", "Silent"])

        layout.addRow(self.dark_mode_checkbox, self.follow_system_checkbox)
        layout.addRow("Output Folder", self.output_folder_combo)
        layout.addRow("Language", self.language_combo)
        layout.addRow("Overwrite behavior", self.overwrite_combo)
        layout.addRow("Logging", self.logging_combo)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addRow(close_button)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Everything Converter")
        self.resize(420, 320)

        layout = QFormLayout(self)
        title = QLabel("<b>Everything Converter</b>")
        title.setTextFormat(Qt.RichText)
        layout.addRow(title)
        layout.addRow("Version", QLabel(APP_VERSION))
        layout.addRow("Build", QLabel(BUILD_TYPE))
        layout.addRow("Python", QLabel(platform.python_version()))
        layout.addRow("Qt", QLabel(QT_VERSION_STR))
        layout.addRow("FFmpeg", QLabel(ffmpeg_version()))
        homepage = QLabel('<a href="https://example.com">https://example.com</a>')
        homepage.setOpenExternalLinks(True)
        layout.addRow("Homepage", homepage)
        layout.addRow("License", QLabel("MIT"))

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addRow(close_button)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Everything Converter")
        self.resize(1100, 700)
        self.selected_files = []
        self.available_converters = list(CONVERTERS)
        self.converter_thread = None
        self.current_speed = "0.00 MB/s"

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

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        status_bar.addPermanentWidget(self.progress_bar)
        status_bar.addPermanentWidget(QLabel("v0.1.0"))

    def _create_central_ui(self):
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.current_category = None
        self.category_items = {}

        self.sidebar = QTreeWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setRootIsDecorated(False)
        self.sidebar.setFixedWidth(280)

        # ★★★★★ Black text with white outline ★★★★★
        self.sidebar.setStyleSheet("""
            QTreeWidget#sidebar::item {
                color: black;
                text-shadow: 1px 1px 0 white, -1px -1px 0 white, 1px -1px 0 white, -1px 1px 0 white;
            }
        """)

        self.sidebar.itemClicked.connect(self.on_sidebar_item_clicked)
        self._build_sidebar()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search conversions...")
        self.search_bar.textChanged.connect(self.on_search_text_changed)

        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self.handle_files)
        self.drop_area.browse_requested.connect(self.browse_files)

        self.detected_extension_label = QLabel("Drop a file to detect available conversions")
        self.detected_extension_label.setObjectName("detectedExtensionLabel")

        self.converter_list = QListWidget()
        self.converter_list.setObjectName("converterList")
        self.converter_list.setMinimumHeight(110)
        self.converter_list.currentItemChanged.connect(self.update_converter_details)
        self.converter_list.itemDoubleClicked.connect(self.convert_selected_files)

        self.converter_description_label = QLabel("Select a conversion to see the target format description")
        self.converter_description_label.setObjectName("converterDescriptionLabel")
        self.converter_description_label.setWordWrap(True)
        self.converter_description_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.converter_description_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.description_scroll_area = QScrollArea()
        self.description_scroll_area.setWidgetResizable(True)
        self.description_scroll_area.setWidget(self.converter_description_label)
        self.description_scroll_area.setMaximumHeight(150)
        self.description_scroll_area.setFrameShape(QFrame.StyledPanel)

        self.destination_label = QLabel("Destination path will appear after selecting a conversion")
        self.destination_label.setObjectName("destinationLabel")
        self.destination_label.setWordWrap(True)

        content_layout.addWidget(self.search_bar)
        content_layout.addWidget(self.detected_extension_label)
        content_layout.addWidget(self.drop_area, stretch=1)
        content_layout.addWidget(QLabel("Converter List"))
        content_layout.addWidget(self.converter_list)
        content_layout.addWidget(self.description_scroll_area)
        content_layout.addWidget(self.destination_label)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(content)

        conversion_view = QWidget()
        conversion_layout = QVBoxLayout(conversion_view)
        conversion_layout.setAlignment(Qt.AlignCenter)
        conversion_layout.setSpacing(16)

        conversion_title = QLabel("Converting files...")
        conversion_title.setObjectName("conversionTitle")
        conversion_title.setAlignment(Qt.AlignCenter)

        self.current_converter_label = QLabel("Current Converter: -")
        self.current_converter_label.setAlignment(Qt.AlignCenter)

        self.current_file_label = QLabel("File: -")
        self.current_file_label.setAlignment(Qt.AlignCenter)

        self.conversion_progress_bar = QProgressBar()
        self.conversion_progress_bar.setMinimum(0)
        self.conversion_progress_bar.setMaximum(100)
        self.conversion_progress_bar.setValue(0)
        self.conversion_progress_bar.setTextVisible(True)
        self.conversion_progress_bar.setMinimumHeight(28)

        self.conversion_info_label = QLabel("0 / 0 files | 0.00 MB/s")
        self.conversion_info_label.setObjectName("conversionInfoLabel")
        self.conversion_info_label.setAlignment(Qt.AlignCenter)

        timing_layout = QHBoxLayout()
        timing_layout.addWidget(QLabel("Elapsed:"))
        self.elapsed_label = QLabel("00:00:00")
        timing_layout.addWidget(self.elapsed_label)
        timing_layout.addStretch()
        timing_layout.addWidget(QLabel("Remaining:"))
        self.remaining_label = QLabel("00:00:00")
        timing_layout.addWidget(self.remaining_label)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_conversion)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_conversion)

        self.done_button = QPushButton("Done")
        self.done_button.clicked.connect(self.finish_conversion)
        self.done_button.setVisible(False)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.done_button)
        button_layout.addStretch()

        conversion_layout.addStretch()
        conversion_layout.addWidget(conversion_title)
        conversion_layout.addWidget(self.current_converter_label)
        conversion_layout.addWidget(self.current_file_label)
        conversion_layout.addWidget(self.conversion_progress_bar)
        conversion_layout.addWidget(self.conversion_info_label)
        conversion_layout.addLayout(timing_layout)
        conversion_layout.addLayout(button_layout)
        conversion_layout.addStretch()

        self.content_stack.addWidget(conversion_view)

        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(self.content_stack, stretch=1)

        self.setCentralWidget(root)

    def _build_sidebar(self):
        self.sidebar.clear()
        self.category_items.clear()

        self.sidebar.setIconSize(QSize(40, 40))

        # Mapping of category (or None for Favorites) to background JPG filename
        bg_map = {
            None: "favorite.jpg",
            "Image": "image.jpg",
            "Video": "video.jpg",
            "Audio": "audio.jpg",
            "PDF": "pdf.jpg",
            "Archives": "archive.jpg",
            "Office": "office.jpg",
        }

        def set_item_background(item, category):
            jpg_name = bg_map.get(category)
            if jpg_name is None:
                return
            bg_path = RESOURCES / "backgrounds" / jpg_name
            if bg_path.exists():
                pixmap = QPixmap(str(bg_path))
                # Scale to item's size hint (260x48) with cover behavior (crop to fill)
                scaled = pixmap.scaled(260, 48, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                brush = QBrush(scaled)
                item.setBackground(0, brush)

        # Favorites item
        favorites_item = QTreeWidgetItem(["Favorites (0)"])
        favorites_item.setData(0, Qt.UserRole, None)
        favorites_item.setSizeHint(0, QSize(260, 48))
        set_item_background(favorites_item, None)

        fav_icon_path = ICONS / "favorite.svg"
        if fav_icon_path.exists():
            renderer = QSvgRenderer(str(fav_icon_path))
            if renderer.isValid():
                pixmap = QPixmap(40, 40)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                favorites_item.setIcon(0, QIcon(pixmap))
            else:
                icon = QIcon(str(fav_icon_path))
                if not icon.isNull():
                    favorites_item.setIcon(0, icon)
        self.sidebar.addTopLevelItem(favorites_item)

        file_formats = QTreeWidgetItem(["File Formats"])
        file_formats.setExpanded(True)
        self.sidebar.addTopLevelItem(file_formats)

        categories = [
            ("Images", "image.svg", "Image"),
            ("Video", "video.svg", "Video"),
            ("Audio", "audio.svg", "Audio"),
            ("PDF", "pdf.svg", "PDF"),
            ("Archives", "archive.svg", "Archives"),
            ("Office", "office.svg", "Office"),
        ]

        for label, icon_name, category_name in categories:
            item = QTreeWidgetItem([label])
            item.setSizeHint(0, QSize(260, 48))
            set_item_background(item, category_name)

            icon_path = ICONS / icon_name
            if icon_path.exists():
                renderer = QSvgRenderer(str(icon_path))
                if renderer.isValid():
                    pixmap = QPixmap(40, 40)
                    pixmap.fill(Qt.transparent)
                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()
                    item.setIcon(0, QIcon(pixmap))
                else:
                    icon = QIcon(str(icon_path))
                    if not icon.isNull():
                        item.setIcon(0, icon)
            item.setData(0, Qt.UserRole, category_name)
            file_formats.addChild(item)
            self.category_items[category_name] = item

        self.update_sidebar_counts()

    def on_search_text_changed(self):
        self.update_sidebar_counts(self.search_bar.text())
        self.refresh_converter_list()

    def on_sidebar_item_clicked(self, item, column):
        category = item.data(0, Qt.UserRole)
        self.current_category = category
        if category is None:
            self.drop_area.set_icon("Favorites")
        else:
            self.drop_area.set_icon(category)
        self.refresh_converter_list()

    def update_sidebar_counts(self, query: str = ""):
        converters = search_converters(query, CONVERTERS) if query else list(CONVERTERS)
        counts = {}
        for converter in converters:
            counts[converter.category] = counts.get(converter.category, 0) + 1

        for category, tree_item in self.category_items.items():
            count = counts.get(category, 0)
            tree_item.setText(0, f"{category} ({count})")

        total_converters = len(converters)
        if self.sidebar.topLevelItemCount() > 0:
            fav_item = self.sidebar.topLevelItem(0)
            if fav_item:
                fav_item.setText(0, f"Favorites ({total_converters})")

    def filter_converters_by_category(self, converters):
        if not self.current_category:
            return converters
        return [converter for converter in converters if converter.category.lower() == self.current_category.lower()]

    def resolve_output_paths(self, converter):
        file_pairs = []
        for input_file in self.selected_files:
            candidate = Path(input_file).with_suffix(converter.output_extension)
            if candidate.exists():
                candidate = self.ask_output_conflict(candidate)
                if candidate is None:
                    continue
            file_pairs.append((input_file, str(candidate)))
        return file_pairs

    def ask_output_conflict(self, existing_path: Path):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Output already exists")
        dialog.setText(
            f"The file already exists:\n{existing_path}\n\nChoose what to do:"
        )
        dialog.setIcon(QMessageBox.Warning)

        overwrite_button = dialog.addButton("Yes", QMessageBox.YesRole)
        no_button = dialog.addButton("No", QMessageBox.NoRole)
        rename_button = dialog.addButton("Rename", QMessageBox.ActionRole)
        skip_button = dialog.addButton("Skip", QMessageBox.RejectRole)
        dialog.setDefaultButton(overwrite_button)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked == overwrite_button:
            return existing_path
        if clicked == no_button:
            return self.get_unique_output(existing_path)
        if clicked == rename_button:
            text, ok = QInputDialog.getText(
                self,
                "Rename output file",
                "New filename:",
                text=existing_path.name,
            )
            if ok and text:
                new_path = existing_path.with_name(text)
                if new_path.exists():
                    return self.get_unique_output(new_path)
                return new_path
            return None
        return None

    def get_unique_output(self, output_path: Path):
        source = output_path
        counter = 1
        while source.exists():
            source = source.with_name(f"{output_path.stem}_{counter}{output_path.suffix}")
            counter += 1
        return source

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Open files",
            "",
            "All files (*)",
        )
        if files:
            self.handle_files(files)

    def handle_files(self, files):
        self.selected_files = files
        self.current_category = None
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
        converters = self.filter_converters_by_category(converters)
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

        self.update_converter_details()

    def selected_converter(self):
        current_item = self.converter_list.currentItem()
        if current_item is None:
            return None
        return current_item.data(Qt.UserRole)

    def _update_conversion_controls(self, enabled: bool):
        self.convert_action.setEnabled(enabled)
        self.converter_list.setEnabled(enabled)

    def _on_conversion_progress(self, index: int):
        self.progress_bar.setValue(index)
        if self.converter_thread:
            total = len(self.converter_thread.file_pairs)
            percentage = int((index / total) * 100) if total > 0 else 0
            self.conversion_progress_bar.setValue(percentage)
            self.conversion_info_label.setText(f"{index} / {total} files | {self.current_speed}")

    def _on_conversion_status(self, message: str):
        self.statusBar().showMessage(message)

    def _on_conversion_speed(self, speed: str):
        self.current_speed = speed
        if self.converter_thread:
            total = len(self.converter_thread.file_pairs)
            index = self.progress_bar.value()
            self.conversion_info_label.setText(f"{index} / {total} files | {speed}")

    def _on_current_file(self, filename: str):
        self.current_file_label.setText(f"File: {filename}")

    def _on_time_update(self, elapsed: str, remaining: str):
        self.elapsed_label.setText(elapsed)
        self.remaining_label.setText(remaining)

    def _on_conversion_finished(self, converted: int, errors: list):
        self._update_conversion_controls(True)
        self.progress_bar.setValue(0)
        self.pause_button.setVisible(False)
        self.cancel_button.setVisible(False)
        self.done_button.setVisible(True)
        self.conversion_progress_bar.setValue(100)

        if errors:
            self.statusBar().showMessage("Error")
        elif converted:
            self.statusBar().showMessage("Done")
        else:
            self.statusBar().showMessage("Ready")

    def pause_conversion(self):
        if self.converter_thread:
            self.converter_thread.pause()
            self.pause_button.setText("Resume")
            self.pause_button.clicked.disconnect()
            self.pause_button.clicked.connect(self.resume_conversion)

    def resume_conversion(self):
        if self.converter_thread:
            self.converter_thread.resume()
            self.pause_button.setText("Pause")
            self.pause_button.clicked.disconnect()
            self.pause_button.clicked.connect(self.pause_conversion)

    def cancel_conversion(self):
        if self.converter_thread:
            self.converter_thread.cancel()

    def finish_conversion(self):
        converted = self.converter_thread.converted if self.converter_thread else 0
        errors = self.converter_thread.errors if self.converter_thread else []

        if errors:
            QMessageBox.warning(self, "Conversion finished with errors", "\n".join(errors))
        elif converted:
            QMessageBox.information(self, "Conversion complete", f"Converted {converted} file(s).")

        self.content_stack.setCurrentIndex(0)
        self.pause_button.setVisible(True)
        self.cancel_button.setVisible(True)
        self.done_button.setVisible(False)
        self.pause_button.setText("Pause")
        self.pause_button.clicked.disconnect()
        self.pause_button.clicked.connect(self.pause_conversion)

    def _describe_extension(self, extension):
        description = EXTENSION_DESCRIPTIONS.get(extension.lower(), "Unknown file type")
        return f"{extension.upper()} — {description}"

    def update_converter_details(self):
        converter = self.selected_converter()
        if converter is None:
            self.converter_description_label.setText("Select a conversion to see the target format description")
            self.destination_label.setText("Destination path will appear after selecting a conversion")
            return

        output_extension = converter.output_extension
        self.converter_description_label.setText(
            f"Target format: {self._describe_extension(output_extension)}"
        )

        if self.selected_files:
            destination_example = self._build_output_path(self.selected_files[0], output_extension)
            self.destination_label.setText(
                f"Destination example: {destination_example}"
            )
        else:
            self.destination_label.setText("Destination example: Select files to show the output path")

    def convert_selected_files(self):
        if self.converter_thread and self.converter_thread.isRunning():
            QMessageBox.information(self, "Conversion in progress", "Please wait until the current conversion finishes.")
            return

        if not self.selected_files:
            self.statusBar().showMessage("Ready")
            QMessageBox.information(self, "No files selected", "Drop files or click Open before converting.")
            return

        converter = self.selected_converter()
        if converter is None:
            self.statusBar().showMessage("No converter selected")
            QMessageBox.warning(self, "No converter selected", "Select a conversion from the list first.")
            return

        total_files = len(self.selected_files)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(total_files)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Starting conversion...")
        self._update_conversion_controls(False)

        self.current_speed = "0.00 MB/s"
        self.conversion_progress_bar.setValue(0)
        self.conversion_info_label.setText(f"0 / {total_files} files | {self.current_speed}")
        self.pause_button.setVisible(True)
        self.cancel_button.setVisible(True)
        self.done_button.setVisible(False)
        self.pause_button.setText("Pause")
        self.content_stack.setCurrentIndex(1)

        self.current_converter_label.setText(f"Current Converter: {converter.name}")

        output_pairs = self.resolve_output_paths(converter)
        if not output_pairs:
            self.statusBar().showMessage("Conversion canceled")
            self._update_conversion_controls(True)
            self.content_stack.setCurrentIndex(0)
            return

        total_files = len(output_pairs)
        self.progress_bar.setMaximum(total_files)
        self.conversion_info_label.setText(f"0 / {total_files} files | {self.current_speed}")

        self.converter_thread = ConversionWorker(converter, output_pairs)
        self.converter_thread.progress_updated.connect(self._on_conversion_progress)
        self.converter_thread.status_message.connect(self._on_conversion_status)
        self.converter_thread.speed_updated.connect(self._on_conversion_speed)
        self.converter_thread.per_file_progress.connect(self._on_file_progress)
        self.converter_thread.current_file_updated.connect(self._on_current_file)
        self.converter_thread.time_updated.connect(self._on_time_update)
        self.converter_thread.conversion_finished.connect(self._on_conversion_finished)
        self.converter_thread.start()

    def _on_file_progress(self, percent: int):
        self.conversion_progress_bar.setValue(percent)
        if self.converter_thread:
            total = len(self.converter_thread.file_pairs)
            index = self.progress_bar.value()
            self.conversion_info_label.setText(f"{index} / {total} files | {self.current_speed}")

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