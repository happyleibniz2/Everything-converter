import os
import subprocess
import time
import shutil
import platform
from pathlib import Path
from PyQt5.QtCore import pyqtSignal, Qt, QThread, QSize, QSettings, QUrl
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QBrush, QDesktopServices
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QProgressBar,
    QScrollArea, QStackedWidget, QStatusBar, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QGroupBox, QSpinBox,
    QTabWidget, QTimeEdit, QButtonGroup, QRadioButton, QListWidgetItem,
    QMenu, QSystemTrayIcon, QSplitter
)
import psutil
from logger import logger
from registry import CONVERTERS, find_converters, search_converters
from converters.extensions import EXTENSION_DESCRIPTIONS
from system_info import APP_VERSION, BUILD_TYPE, ffmpeg_version
from utils.paths import ICONS, RESOURCES, TEMP
from converters.ffmpeg_base import FFmpegConverter
from ui.options_dialog import ConversionOptionsDialog, PRESETS


# ---------- Worker Thread ----------
class ConversionWorker(QThread):
    progress_updated = pyqtSignal(int)
    per_file_progress = pyqtSignal(int)
    status_message = pyqtSignal(str)
    speed_updated = pyqtSignal(str)
    current_file_updated = pyqtSignal(str)
    time_updated = pyqtSignal(str, str)
    conversion_finished = pyqtSignal(int, list)

    def __init__(self, converter, file_pairs, delete_source=False):
        super().__init__()
        self.converter = converter
        self.file_pairs = file_pairs
        self.converted = 0
        self.errors = []
        self.is_paused = False
        self.is_cancelled = False
        self.start_time = None
        self.bytes_processed = 0
        self.delete_source = delete_source
        self.current_process = None

    def pause(self):
        self.is_paused = True
        if self.current_process and self.current_process.poll() is None:
            try:
                psutil.Process(self.current_process.pid).suspend()
                logger.info(f"Suspended FFmpeg PID {self.current_process.pid}")
            except Exception as e:
                logger.error(f"Failed to suspend: {e}")

    def resume(self):
        self.is_paused = False
        if self.current_process and self.current_process.poll() is None:
            try:
                psutil.Process(self.current_process.pid).resume()
                logger.info(f"Resumed FFmpeg PID {self.current_process.pid}")
            except Exception as e:
                logger.error(f"Failed to resume: {e}")

    def cancel(self):
        self.is_cancelled = True
        if self.current_process and self.current_process.poll() is None:
            try:
                proc = psutil.Process(self.current_process.pid)
                children = proc.children(recursive=True)
                for child in children:
                    child.kill()
                proc.kill()
                proc.wait(timeout=2)
                logger.info(f"Force-killed FFmpeg PID {self.current_process.pid}")
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                logger.warning(f"Psutil kill failed, falling back to subprocess: {e}")
                try:
                    self.current_process.kill()
                    self.current_process.wait(timeout=2)
                except Exception:
                    pass

    def run(self):
        total_files = len(self.file_pairs)
        self.start_time = time.time()

        for index, (input_file, output_file) in enumerate(self.file_pairs, start=1):
            if self.is_cancelled:
                break

            while self.is_paused:
                time.sleep(0.1)

            self.current_file_updated.emit(Path(input_file).name)
            self.status_message.emit(f"Converting {index}/{total_files}...")

            temp_output = str(TEMP / f"temp_{Path(output_file).name}")
            os.makedirs(os.path.dirname(temp_output), exist_ok=True)
            moved = False

            try:
                file_size = Path(input_file).stat().st_size
                logger.info("================================================")
                logger.info("Conversion")
                logger.info("Input: %s", input_file)
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

                    self.converter.convert_with_progress(
                        input_file,
                        temp_output,
                        progress_callback=_progress_cb,
                        should_cancel=lambda: self.is_cancelled,
                        process_callback=lambda proc: setattr(self, 'current_process', proc)
                    )
                else:
                    self.converter.convert(input_file, temp_output)

                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                shutil.move(temp_output, output_file)
                moved = True

                duration = time.time() - start_file
                self.bytes_processed += file_size
                self.converted += 1

                if self.delete_source:
                    try:
                        os.remove(input_file)
                        logger.info("Deleted source: %s", input_file)
                    except Exception as e:
                        logger.warning("Could not delete source: %s", e)

                logger.info("Duration: %.2f seconds", duration)
                logger.info("Success")
            except Exception as exc:
                logger.exception("Conversion failed for %s", input_file)
                self.errors.append(f"{Path(input_file).name}: {exc}")
                if self.is_cancelled:
                    self.status_message.emit("Conversion canceled")
                    break
            finally:
                if not moved and os.path.exists(temp_output):
                    try:
                        os.remove(temp_output)
                        logger.info("Removed temporary file: %s", temp_output)
                    except Exception as e:
                        logger.warning("Failed to remove temporary file: %s", e)
                self.current_process = None

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


# ---------- Drop Area ----------
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


# ---------- Settings Dialog ----------
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(500, 450)
        self.settings = QSettings("EverythingConverter", "Settings")
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        general_widget = QWidget()
        general_layout = QFormLayout(general_widget)

        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.follow_system_checkbox = QCheckBox("Follow System")
        general_layout.addRow(self.dark_mode_checkbox, self.follow_system_checkbox)

        self.output_folder_combo = QComboBox()
        self.output_folder_combo.addItems(["Same folder", "Ask every time", "Custom folder"])
        general_layout.addRow("Output Folder", self.output_folder_combo)

        self.custom_folder_edit = QLineEdit()
        self.custom_folder_edit.setPlaceholderText("Path to custom output folder")
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_custom_folder)
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.custom_folder_edit)
        folder_layout.addWidget(browse_btn)
        general_layout.addRow("Custom Path", folder_layout)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "中文", "日本語"])
        general_layout.addRow("Language", self.language_combo)

        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItems(["Rename", "Overwrite", "Skip", "Ask for name"])
        general_layout.addRow("Overwrite behavior", self.overwrite_combo)

        self.logging_combo = QComboBox()
        self.logging_combo.addItems(["Verbose", "Normal", "Silent"])
        general_layout.addRow("Logging", self.logging_combo)

        tabs.addTab(general_widget, "General")

        adv_widget = QWidget()
        adv_layout = QFormLayout(adv_widget)

        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(0, 64)
        self.thread_spin.setSpecialValueText("Auto")
        self.thread_spin.setToolTip("0 = auto (no -threads), 1-64 = limit")
        adv_layout.addRow("Max threads", self.thread_spin)

        self.shutdown_check = QCheckBox("Shutdown after conversion")
        adv_layout.addRow(self.shutdown_check)

        self.delete_source_check = QCheckBox("Delete source after conversion")
        adv_layout.addRow(self.delete_source_check)

        self.temp_dir_edit = QLineEdit()
        self.temp_dir_edit.setPlaceholderText("Temporary folder (leave empty for system temp)")
        adv_layout.addRow("Temp folder", self.temp_dir_edit)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESETS.keys()))
        adv_layout.addRow("Default Preset", self.preset_combo)

        tabs.addTab(adv_widget, "Advanced")

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def browse_custom_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.custom_folder_edit.setText(folder)

    def load_settings(self):
        self.dark_mode_checkbox.setChecked(self.settings.value("dark_mode", False, type=bool))
        self.follow_system_checkbox.setChecked(self.settings.value("follow_system", True, type=bool))
        self.output_folder_combo.setCurrentIndex(self.settings.value("output_folder_mode", 0, type=int))
        self.custom_folder_edit.setText(self.settings.value("custom_folder", "", type=str))
        self.language_combo.setCurrentIndex(self.settings.value("language", 0, type=int))
        self.overwrite_combo.setCurrentIndex(self.settings.value("overwrite_behavior", 0, type=int))
        self.logging_combo.setCurrentIndex(self.settings.value("logging", 1, type=int))
        self.thread_spin.setValue(self.settings.value("threads", 0, type=int))
        self.shutdown_check.setChecked(self.settings.value("shutdown_after", False, type=bool))
        self.delete_source_check.setChecked(self.settings.value("delete_source", False, type=bool))
        self.temp_dir_edit.setText(self.settings.value("temp_dir", "", type=str))
        preset_idx = self.preset_combo.findText(self.settings.value("default_preset", "None", type=str))
        if preset_idx >= 0:
            self.preset_combo.setCurrentIndex(preset_idx)

    def save_settings(self):
        self.settings.setValue("dark_mode", self.dark_mode_checkbox.isChecked())
        self.settings.setValue("follow_system", self.follow_system_checkbox.isChecked())
        self.settings.setValue("output_folder_mode", self.output_folder_combo.currentIndex())
        self.settings.setValue("custom_folder", self.custom_folder_edit.text())
        self.settings.setValue("language", self.language_combo.currentIndex())
        self.settings.setValue("overwrite_behavior", self.overwrite_combo.currentIndex())
        self.settings.setValue("logging", self.logging_combo.currentIndex())
        self.settings.setValue("threads", self.thread_spin.value())
        self.settings.setValue("shutdown_after", self.shutdown_check.isChecked())
        self.settings.setValue("delete_source", self.delete_source_check.isChecked())
        self.settings.setValue("temp_dir", self.temp_dir_edit.text())
        self.settings.setValue("default_preset", self.preset_combo.currentText())

    def accept(self):
        self.save_settings()
        super().accept()


# ---------- About Dialog ----------
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
        from PyQt5.QtCore import QT_VERSION_STR
        layout.addRow("Qt", QLabel(QT_VERSION_STR))
        layout.addRow("FFmpeg", QLabel(ffmpeg_version()))
        homepage = QLabel('<a href="https://example.com">https://example.com</a>')
        homepage.setOpenExternalLinks(True)
        layout.addRow("Homepage", homepage)
        layout.addRow("License", QLabel("MIT"))

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addRow(close_button)


# ---------- Main Window ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Everything Converter")
        self.resize(1200, 750)
        self.selected_files = []
        self.available_converters = list(CONVERTERS)
        self.converter_thread = None
        self.current_speed = "0.00 MB/s"
        self.settings = QSettings("EverythingConverter", "Settings")

        self.load_general_settings()

        self._create_actions()
        self._create_menu_bar()
        self._create_tool_bar()
        self._create_status_bar()
        self._create_central_ui()

        self.tray_icon = None
        self.setup_tray()

    def load_general_settings(self):
        dark = self.settings.value("dark_mode", False, type=bool)
        if dark:
            self.set_dark_mode(True)

    def setup_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            icon_path = RESOURCES / "icon.ico"
            if icon_path.exists():
                self.tray_icon.setIcon(QIcon(str(icon_path)))
            self.tray_icon.setVisible(True)

    def show_notification(self, title, message):
        if self.tray_icon:
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 5000)

    def set_dark_mode(self, enable):
        if enable:
            dark_style = """
            QMainWindow { background: #2b2b2b; }
            QListWidget, QLineEdit, QComboBox, QSpinBox, QTimeEdit {
                background: #3c3c3c; color: #eee; border: 1px solid #555; border-radius: 6px; padding: 5px;
            }
            QFrame#dropArea { background: #3c3c3c; border: 2px dashed #6a6a6a; border-radius: 14px; }
            QLabel { color: #eee; }
            QPushButton { background: #4a4a4a; color: #eee; border: 1px solid #666; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background: #5a5a5a; }
            QTreeWidget, QListWidget { background: #3c3c3c; color: #eee; }
            QTreeWidget::item { color: #eee; }
            QMenuBar { background: #2b2b2b; color: #eee; }
            QMenuBar::item:selected { background: #4a4a4a; }
            QStatusBar { background: #2b2b2b; color: #eee; }
            QProgressBar { background: #3c3c3c; border: 1px solid #555; border-radius: 4px; }
            QProgressBar::chunk { background: #4f7cff; }
            QGroupBox { color: #eee; border: 1px solid #555; border-radius: 4px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QTabWidget::pane { background: #2b2b2b; border: 1px solid #555; }
            QTabBar::tab { background: #3c3c3c; color: #eee; padding: 8px; }
            QTabBar::tab:selected { background: #4a4a4a; }
            """
            self.setStyleSheet(dark_style)
        else:
            stylesheet_path = Path(__file__).parent / "styles.qss"
            if stylesheet_path.exists():
                self.setStyleSheet(stylesheet_path.read_text())

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
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        # Sidebar
        self.sidebar = QTreeWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setRootIsDecorated(False)
        self.sidebar.setMinimumWidth(150)
        self.sidebar.setStyleSheet("""
            QTreeWidget#sidebar::item {
                color: black;
                text-shadow: 1px 1px 0 white, -1px -1px 0 white, 1px -1px 0 white, -1px 1px 0 white;
            }
        """)
        self.sidebar.itemClicked.connect(self.on_sidebar_item_clicked)

        self.category_items = {}
        self.current_category = None
        self._build_sidebar()

        # Main content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search conversions...")
        self.search_bar.textChanged.connect(self.on_search_text_changed)

        file_list_label = QLabel("File Queue (drag to reorder)")
        self.file_list_widget = QListWidget()
        self.file_list_widget.setDragEnabled(True)
        self.file_list_widget.setAcceptDrops(True)
        self.file_list_widget.setDropIndicatorShown(True)
        self.file_list_widget.setDefaultDropAction(Qt.MoveAction)
        self.file_list_widget.model().rowsMoved.connect(self.on_files_reordered)
        self.file_list_widget.setMinimumHeight(100)
        self.file_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list_widget.customContextMenuRequested.connect(self.show_file_context_menu)

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
        content_layout.addWidget(self.drop_area)
        content_layout.addWidget(file_list_label)
        content_layout.addWidget(self.file_list_widget)
        content_layout.addWidget(QLabel("Converter List"))
        content_layout.addWidget(self.converter_list)
        content_layout.addWidget(self.description_scroll_area)
        content_layout.addWidget(self.destination_label)

        # Stacked widget (main view / conversion view)
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(content)

        # --- Conversion view with progress and completion ---
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

        # Timing container
        self.timing_container = QWidget()
        timing_layout = QHBoxLayout(self.timing_container)
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

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()

        # ---- Completion panel (shown when done) ----
        self.completion_widget = QWidget()
        completion_layout = QVBoxLayout(self.completion_widget)
        completion_layout.setAlignment(Qt.AlignCenter)
        completion_layout.setSpacing(16)

        complete_label = QLabel("✅ Conversion Complete!")
        complete_label.setObjectName("completionTitle")
        complete_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        complete_label.setAlignment(Qt.AlignCenter)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignCenter)

        # Folder icon
        folder_icon_path = ICONS / "folder.svg"
        folder_icon = QIcon(str(folder_icon_path)) if folder_icon_path.exists() else QIcon()
        self.open_folder_btn = QPushButton(folder_icon, "Open Folder")
        self.open_folder_btn.clicked.connect(self._open_output_folder)

        # File icon
        file_icon_path = ICONS / "file.svg"
        file_icon = QIcon(str(file_icon_path)) if file_icon_path.exists() else QIcon()
        self.open_file_btn = QPushButton(file_icon, "Open File")
        self.open_file_btn.clicked.connect(self._open_output_file)

        # Back button
        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self._go_back_to_main)

        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addWidget(self.open_file_btn)
        btn_layout.addWidget(self.back_btn)

        completion_layout.addWidget(complete_label)
        completion_layout.addLayout(btn_layout)
        self.completion_widget.hide()

        # Add all to conversion view
        conversion_layout.addStretch()
        conversion_layout.addWidget(conversion_title)
        conversion_layout.addWidget(self.current_converter_label)
        conversion_layout.addWidget(self.current_file_label)
        conversion_layout.addWidget(self.conversion_progress_bar)
        conversion_layout.addWidget(self.conversion_info_label)
        conversion_layout.addWidget(self.timing_container)
        conversion_layout.addLayout(button_layout)
        conversion_layout.addWidget(self.completion_widget)
        conversion_layout.addStretch()

        self.content_stack.addWidget(conversion_view)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.content_stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 800])

        root_layout.addWidget(splitter)
        self.setCentralWidget(root)

    # ---------- Completion actions ----------
    def _open_output_folder(self):
        if hasattr(self, '_output_files') and self._output_files:
            folder = str(Path(self._output_files[0]).parent)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            QMessageBox.information(self, "No files", "No output files to open.")

    def _open_output_file(self):
        if hasattr(self, '_output_files') and self._output_files:
            path = self._output_files[0]
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.information(self, "No files", "No output files to open.")

    def _go_back_to_main(self):
        """Return to the main file selection view."""
        self.content_stack.setCurrentIndex(0)
        # Reset UI elements
        self.completion_widget.hide()
        self.pause_button.setVisible(True)
        self.cancel_button.setVisible(True)
        self.current_converter_label.show()
        self.current_file_label.show()
        self.conversion_progress_bar.show()
        self.conversion_info_label.show()
        self.timing_container.show()
        self.progress_bar.setValue(0)
        self.conversion_progress_bar.setValue(0)
        self.statusBar().showMessage("Ready")

    # ---------- Sidebar methods ----------
    def _build_sidebar(self):
        self.sidebar.clear()
        self.category_items.clear()
        self.sidebar.setIconSize(QSize(40, 40))

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
                scaled = pixmap.scaled(260, 48, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                brush = QBrush(scaled)
                item.setBackground(0, brush)

        # Favorites
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
        return [c for c in converters if c.category.lower() == self.current_category.lower()]

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
        self.selected_files.extend(files)
        self.update_file_list()
        detected_extensions = sorted({Path(f).suffix.lower() for f in self.selected_files})
        compatible_converters = []
        for ext in detected_extensions:
            compatible_converters.extend(find_converters(ext))
        self.available_converters = list(dict.fromkeys(compatible_converters))

        if detected_extensions:
            self.detected_extension_label.setText(f"Detected: {', '.join(e or '[no ext]' for e in detected_extensions)}")
        else:
            self.detected_extension_label.setText("No file extension detected")

        self.refresh_converter_list()
        if self.available_converters:
            self.converter_list.setCurrentRow(0)
            self.statusBar().showMessage(f"{len(self.selected_files)} file(s) ready — choose a conversion")
        else:
            self.statusBar().showMessage("No converter found")

    def update_file_list(self):
        self.file_list_widget.clear()
        for path in self.selected_files:
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.UserRole, path)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            self.file_list_widget.addItem(item)
        self.drop_area.setVisible(len(self.selected_files) == 0)

    def show_file_context_menu(self, pos):
        item = self.file_list_widget.itemAt(pos)
        if item:
            menu = QMenu()
            remove_action = menu.addAction("Remove from queue")
            move_top = menu.addAction("Move to top")
            action = menu.exec_(self.file_list_widget.mapToGlobal(pos))
            if action == remove_action:
                row = self.file_list_widget.row(item)
                self.file_list_widget.takeItem(row)
                self.selected_files.pop(row)
                self.update_file_list()
            elif action == move_top:
                row = self.file_list_widget.row(item)
                if row > 0:
                    self.file_list_widget.takeItem(row)
                    self.file_list_widget.insertItem(0, item)
                    self.selected_files.insert(0, self.selected_files.pop(row))
                    self.file_list_widget.setCurrentRow(0)

    def on_files_reordered(self, parent, start, end, destination, row):
        new_order = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            path = item.data(Qt.UserRole)
            new_order.append(path)
        self.selected_files = new_order

    def refresh_converter_list(self):
        query = self.search_bar.text()
        converters = search_converters(query, self.available_converters)
        converters = self.filter_converters_by_category(converters)
        self.converter_list.clear()
        for conv in converters:
            input_exts = ", ".join(e.upper().lstrip(".") for e in conv.input_extensions)
            output_ext = conv.output_extension.upper().lstrip(".")
            self.converter_list.addItem(f"{input_exts} → {output_ext}")
            self.converter_list.item(self.converter_list.count()-1).setData(Qt.UserRole, conv)
        if converters:
            self.converter_list.setCurrentRow(0)
        elif query:
            self.converter_list.addItem("No conversions match your search")
        else:
            self.converter_list.addItem("No conversions available")
        self.update_converter_details()

    def selected_converter(self):
        item = self.converter_list.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def update_converter_details(self):
        converter = self.selected_converter()
        if converter is None:
            self.converter_description_label.setText("Select a conversion to see the target format description")
            self.destination_label.setText("Destination path will appear after selecting a conversion")
            return
        output_extension = converter.output_extension
        self.converter_description_label.setText(f"Target format: {self._describe_extension(output_extension)}")
        if self.selected_files:
            example = self._build_output_path(self.selected_files[0], output_extension)
            self.destination_label.setText(f"Destination example: {example}")
        else:
            self.destination_label.setText("Destination example: Select files to show the output path")

    def _describe_extension(self, extension):
        desc = EXTENSION_DESCRIPTIONS.get(extension.lower(), "Unknown file type")
        return f"{extension.upper()} — {desc}"

    def _build_output_path(self, input_file, output_extension):
        settings = QSettings("EverythingConverter", "Settings")
        mode = settings.value("output_folder_mode", 0, type=int)
        custom_folder = settings.value("custom_folder", "", type=str)
        root = Path(input_file).parent
        if mode == 2 and custom_folder:
            root = Path(custom_folder)
        source = Path(input_file)
        output = root / source.with_suffix(output_extension).name
        return str(output)

    def resolve_output_paths(self, converter):
        settings = QSettings("EverythingConverter", "Settings")
        mode = settings.value("output_folder_mode", 0, type=int)
        custom_folder = settings.value("custom_folder", "", type=str)
        overwrite = settings.value("overwrite_behavior", 0, type=int)
        file_pairs = []
        for input_file in self.selected_files:
            base = Path(input_file)
            if mode == 1:
                folder = QFileDialog.getExistingDirectory(self, "Select output folder", str(base.parent))
                if not folder:
                    continue
                out_dir = Path(folder)
            elif mode == 2 and custom_folder:
                out_dir = Path(custom_folder)
                if settings.value("auto_categorize", True, type=bool):
                    out_dir = out_dir / converter.category
                os.makedirs(out_dir, exist_ok=True)
            else:
                out_dir = base.parent

            output_path = out_dir / base.with_suffix(converter.output_extension).name

            while output_path.exists():
                if overwrite == 1:  # Overwrite
                    break
                elif overwrite == 2:  # Skip
                    output_path = None
                    break
                elif overwrite == 0:  # Rename
                    output_path = self.get_unique_output(output_path)
                    break
                elif overwrite == 3:  # Ask for name
                    base_name = output_path.stem
                    ext = output_path.suffix
                    new_name, ok = QInputDialog.getText(
                        self,
                        "File exists",
                        f"File '{output_path.name}' already exists.\nEnter a new name (without extension) or click Cancel to skip:",
                        QLineEdit.Normal,
                        base_name
                    )
                    if not ok:
                        output_path = None
                        break
                    if not new_name.strip():
                        QMessageBox.warning(self, "Invalid name", "Name cannot be empty.")
                        continue
                    new_path = output_path.parent / (new_name.strip() + ext)
                    if new_path.exists():
                        QMessageBox.warning(self, "File exists", f"'{new_path.name}' also exists. Please enter another name.")
                        continue
                    output_path = new_path
                    break
                else:
                    break

            if output_path is None:
                continue

            file_pairs.append((str(input_file), str(output_path)))
        return file_pairs

    def get_unique_output(self, path: Path):
        counter = 1
        base = path.with_suffix('')
        ext = path.suffix
        new_path = path
        while new_path.exists():
            new_path = base.parent / f"{base.stem}_{counter}{ext}"
            counter += 1
        return new_path

    def convert_selected_files(self):
        if self.converter_thread and self.converter_thread.isRunning():
            QMessageBox.information(self, "Conversion in progress", "Please wait.")
            return
        if not self.selected_files:
            QMessageBox.information(self, "No files", "Drop files first.")
            return
        converter = self.selected_converter()
        if converter is None:
            QMessageBox.warning(self, "No converter", "Select a conversion.")
            return

        dlg = ConversionOptionsDialog(self.selected_files, converter, self)
        if dlg.exec() != QDialog.Accepted:
            return
        opts = dlg.get_options()

        preset_args = PRESETS.get(opts.get("preset", "None"), [])
        extra_args = opts.get("extra_args", []) + preset_args
        threads = opts.get("threads", 0)
        copy_mode = opts.get("copy_mode", False)
        copy_audio = opts.get("copy_audio", False)
        start_time = opts.get("start_time")
        end_time = opts.get("end_time")
        scale = opts.get("scale")

        video_codec = opts.get("video_codec")
        audio_codec = opts.get("audio_codec")

        if "crf" in opts:
            extra_args.extend(["-crf", str(opts["crf"])])
        if "video_bitrate" in opts:
            extra_args.extend(["-b:v", f"{opts['video_bitrate']}k"])
        if "audio_bitrate" in opts:
            extra_args.extend(["-b:a", f"{opts['audio_bitrate']}k"])
        if "sample_rate" in opts:
            extra_args.extend(["-ar", str(opts["sample_rate"])])

        new_converter = FFmpegConverter(
            name=converter.name,
            input_extensions=converter.input_extensions,
            output_extension=converter.output_extension,
            video_codec=video_codec if not copy_mode else None,
            audio_codec=audio_codec if not copy_mode and not copy_audio else None,
            extra_args=extra_args,
            threads=threads if threads > 0 else None,
            copy_mode=copy_mode,
            copy_audio=copy_audio,
            start_time=start_time,
            end_time=end_time,
            scale=scale,
        )
        new_converter.category = converter.category

        delete_source = opts.get("delete_source", False)
        shutdown = opts.get("shutdown", False)

        file_pairs = self.resolve_output_paths(new_converter)
        if not file_pairs:
            self.statusBar().showMessage("No files to convert (maybe skipped)")
            return

        self._output_files = [pair[1] for pair in file_pairs]

        total_files = len(file_pairs)
        self.progress_bar.setMaximum(total_files)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Starting conversion...")
        self._update_conversion_controls(False)

        self.current_speed = "0.00 MB/s"
        self.conversion_progress_bar.setValue(0)
        self.conversion_info_label.setText(f"0 / {total_files} files | {self.current_speed}")
        self.pause_button.setVisible(True)
        self.cancel_button.setVisible(True)
        self.pause_button.setText("Pause")
        self.completion_widget.hide()

        # Show all progress widgets
        self.current_converter_label.show()
        self.current_file_label.show()
        self.conversion_progress_bar.show()
        self.conversion_info_label.show()
        self.timing_container.show()

        self.content_stack.setCurrentIndex(1)

        self.current_converter_label.setText(f"Current Converter: {new_converter.name}")

        self.converter_thread = ConversionWorker(new_converter, file_pairs, delete_source)
        self.converter_thread.progress_updated.connect(self._on_conversion_progress)
        self.converter_thread.status_message.connect(self._on_conversion_status)
        self.converter_thread.speed_updated.connect(self._on_conversion_speed)
        self.converter_thread.per_file_progress.connect(self._on_file_progress)
        self.converter_thread.current_file_updated.connect(self._on_current_file)
        self.converter_thread.time_updated.connect(self._on_time_update)
        self.converter_thread.conversion_finished.connect(self._on_conversion_finished)
        self.converter_thread.start()

        self._shutdown_after = shutdown

    def _update_conversion_controls(self, enabled: bool):
        self.convert_action.setEnabled(enabled)
        self.converter_list.setEnabled(enabled)

    def _on_conversion_progress(self, index: int):
        self.progress_bar.setValue(index)
        if self.converter_thread:
            total = len(self.converter_thread.file_pairs)
            percent = int((index / total) * 100) if total else 0
            self.conversion_progress_bar.setValue(percent)
            self.conversion_info_label.setText(f"{index} / {total} files | {self.current_speed}")

    def _on_conversion_status(self, msg):
        self.statusBar().showMessage(msg)

    def _on_conversion_speed(self, speed):
        self.current_speed = speed
        if self.converter_thread:
            total = len(self.converter_thread.file_pairs)
            index = self.progress_bar.value()
            self.conversion_info_label.setText(f"{index} / {total} files | {speed}")

    def _on_current_file(self, filename):
        self.current_file_label.setText(f"File: {filename}")

    def _on_time_update(self, elapsed, remaining):
        self.elapsed_label.setText(elapsed)
        self.remaining_label.setText(remaining)

    def _on_file_progress(self, percent):
        self.conversion_progress_bar.setValue(percent)

    def _on_conversion_finished(self, converted, errors):
        self._update_conversion_controls(True)
        self.progress_bar.setValue(0)
        self.pause_button.setVisible(False)
        self.cancel_button.setVisible(False)
        self.conversion_progress_bar.setValue(100)

        if errors:
            self.statusBar().showMessage("Error")
            self.show_notification("Conversion Errors", f"{len(errors)} files failed.")
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Conversion finished with errors")
            msg.setText(f"{len(errors)} file(s) failed to convert.\nClick 'Show Details' to see the list.")
            msg.setDetailedText("\n".join(errors))
            msg.exec()
            # Show completion panel anyway so user can go back
            self.completion_widget.show()
            self.current_converter_label.hide()
            self.current_file_label.hide()
            self.conversion_progress_bar.hide()
            self.conversion_info_label.hide()
            self.timing_container.hide()
        elif converted:
            self.statusBar().showMessage("Done")
            self.show_notification("Conversion Complete", f"Successfully converted {converted} file(s).")
            # Show completion panel and hide progress widgets
            self.completion_widget.show()
            self.current_converter_label.hide()
            self.current_file_label.hide()
            self.conversion_progress_bar.hide()
            self.conversion_info_label.hide()
            self.timing_container.hide()
        else:
            self.statusBar().showMessage("Ready")

        if hasattr(self, '_shutdown_after') and self._shutdown_after and converted > 0:
            reply = QMessageBox.question(self, "Shutdown", "All conversions done. Shutdown computer now?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                if platform.system() == "Windows":
                    subprocess.run(["shutdown", "/s", "/t", "60"], shell=True)
                else:
                    subprocess.run(["shutdown", "-h", "+1"], shell=True)

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
            self.statusBar().showMessage("Canceling conversion...")
            self.cancel_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.converter_thread.cancel()

    def show_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()
        self.load_general_settings()
        dark = self.settings.value("dark_mode", False, type=bool)
        self.set_dark_mode(dark)

    def show_about(self):
        AboutDialog(self).exec()