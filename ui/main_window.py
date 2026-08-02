# ui/main_window.py

import os
import platform
from pathlib import Path
from PyQt5.QtCore import Qt, QSize, QSettings, QUrl
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QBrush, QDesktopServices
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QMainWindow, QMessageBox, QPushButton, QProgressBar,
    QScrollArea, QStackedWidget, QStatusBar, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QGroupBox, QSpinBox,
    QTabWidget, QListWidget, QListWidgetItem,
    QMenu, QSystemTrayIcon, QSplitter, QHeaderView, QAbstractItemView
)
import lang
from logger import logger
from registry import CONVERTERS, find_converters, search_converters
from converters.extensions import EXTENSION_DESCRIPTIONS
from system_info import APP_VERSION, BUILD_TYPE, ffmpeg_version
from utils.paths import ICONS, RESOURCES
from converters.ffmpeg_base import FFmpegConverter
from ui.options_dialog import ConversionOptionsDialog, PRESETS, DEFAULT_VIDEO_CODEC, DEFAULT_AUDIO_CODEC
from ui.error_assistant import ErrorAssistant
from ui.widgets.drop_area import DropArea
from workers.conversion_worker import BatchConversionWorker
from utils.media_info import get_media_info
from services.size_estimator import estimate_output_size
from controllers.queue_controller import QueueController

# ---------- Batch Conversion Worker (unchanged) ----------
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.settings = QSettings("EverythingConverter", "Settings")
        self.setWindowTitle(lang.lang.get("Settings"))
        self.resize(500, 450)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        general_widget = QWidget()
        general_layout = QFormLayout(general_widget)

        self.dark_mode_checkbox = QCheckBox(lang.lang.get("Dark mode"))
        self.follow_system_checkbox = QCheckBox(lang.lang.get("Follow system"))
        general_layout.addRow(self.dark_mode_checkbox, self.follow_system_checkbox)

        self.output_folder_combo = QComboBox()
        self.output_folder_combo.addItems([lang.lang.get("Same folder"), lang.lang.get("Ask every time"), lang.lang.get("Custom folder")])
        general_layout.addRow(lang.lang.get("Output Folder"), self.output_folder_combo)

        self.custom_folder_edit = QLineEdit()
        self.custom_folder_edit.setPlaceholderText(lang.lang.get("Path to custom output folder"))
        browse_btn = QPushButton(lang.lang.get("Browse"))
        browse_btn.clicked.connect(self.browse_custom_folder)
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.custom_folder_edit)
        folder_layout.addWidget(browse_btn)
        general_layout.addRow(lang.lang.get("Custom Path"), folder_layout)

        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en_US")
        self.language_combo.addItem("中文", "zh_CN")
        self.language_combo.addItem("日本語", "ja_JP")
        general_layout.addRow(lang.lang.get("Language"), self.language_combo)

        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItems([lang.lang.get("Rename"), lang.lang.get("Overwrite"), lang.lang.get("Skip"), lang.lang.get("Ask for name")])
        general_layout.addRow(lang.lang.get("Overwrite behavior"), self.overwrite_combo)

        self.logging_combo = QComboBox()
        self.logging_combo.addItems([lang.lang.get("Verbose"), lang.lang.get("Normal"), lang.lang.get("Silent")])
        general_layout.addRow(lang.lang.get("Logging"), self.logging_combo)

        tabs.addTab(general_widget, lang.lang.get("General"))

        adv_widget = QWidget()
        adv_layout = QFormLayout(adv_widget)

        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(0, 64)
        self.thread_spin.setSpecialValueText("Auto")
        self.thread_spin.setToolTip(lang.lang.get("0 = auto (no -threads), 1-64 = limit"))
        adv_layout.addRow(lang.lang.get("Max threads"), self.thread_spin)

        self.shutdown_check = QCheckBox(lang.lang.get("Shutdown after conversion"))
        adv_layout.addRow(self.shutdown_check)

        self.delete_source_check = QCheckBox(lang.lang.get("Delete source after conversion"))
        adv_layout.addRow(self.delete_source_check)

        self.temp_dir_edit = QLineEdit()
        self.temp_dir_edit.setPlaceholderText(lang.lang.get("Temporary folder (leave empty for system temp)"))
        adv_layout.addRow(lang.lang.get("Temp folder"), self.temp_dir_edit)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESETS.keys()))
        adv_layout.addRow(lang.lang.get("Default Preset"), self.preset_combo)

        tabs.addTab(adv_widget, lang.lang.get("Advanced"))

        close_btn = QPushButton(lang.lang.get("Close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def browse_custom_folder(self):
        folder = QFileDialog.getExistingDirectory(self, lang.lang.get("Select output folder"))
        if folder:
            self.custom_folder_edit.setText(folder)

    def load_settings(self):
        self.dark_mode_checkbox.setChecked(self.settings.value("dark_mode", False, type=bool))
        self.follow_system_checkbox.setChecked(self.settings.value("follow_system", True, type=bool))
        self.output_folder_combo.setCurrentIndex(self.settings.value("output_folder_mode", 0, type=int))
        self.custom_folder_edit.setText(self.settings.value("custom_folder", "", type=str))
        lang_code = self.settings.value("language", "en_US", type=str)
        idx = self.language_combo.findData(lang_code)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)
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
        lang_code = self.language_combo.currentData()
        self.settings.setValue("language", lang_code)
        self.settings.setValue("overwrite_behavior", self.overwrite_combo.currentIndex())
        self.settings.setValue("logging", self.logging_combo.currentIndex())
        self.settings.setValue("threads", self.thread_spin.value())
        self.settings.setValue("shutdown_after", self.shutdown_check.isChecked())
        self.settings.setValue("delete_source", self.delete_source_check.isChecked())
        self.settings.setValue("temp_dir", self.temp_dir_edit.text())
        self.settings.setValue("default_preset", self.preset_combo.currentText())

    def accept(self):
        self.save_settings()
        # Reload language in global lang
        lang_code = self.language_combo.currentData()
        lang.lang.load_language(lang_code)
        # Retranslate main window and this dialog
        if self.parent_window:
            self.parent_window.retranslate_ui()
        self.retranslate_ui()
        super().accept()

    def retranslate_ui(self):
        self.setWindowTitle(lang.lang.get("Settings"))
        # Update combo box items
        output_mode = self.output_folder_combo.currentIndex()
        overwrite_mode = self.overwrite_combo.currentIndex()
        logging_mode = self.logging_combo.currentIndex()
        language_data = self.language_combo.currentData()
        preset_text = self.preset_combo.currentText()

        self.output_folder_combo.clear()
        self.output_folder_combo.addItems([lang.lang.get("Same folder"), lang.lang.get("Ask every time"), lang.lang.get("Custom folder")])
        self.output_folder_combo.setCurrentIndex(min(output_mode, self.output_folder_combo.count() - 1))

        self.overwrite_combo.clear()
        self.overwrite_combo.addItems([lang.lang.get("Rename"), lang.lang.get("Overwrite"), lang.lang.get("Skip"), lang.lang.get("Ask for name")])
        self.overwrite_combo.setCurrentIndex(min(overwrite_mode, self.overwrite_combo.count() - 1))

        self.logging_combo.clear()
        self.logging_combo.addItems([lang.lang.get("Verbose"), lang.lang.get("Normal"), lang.lang.get("Silent")])
        self.logging_combo.setCurrentIndex(min(logging_mode, self.logging_combo.count() - 1))

        self.dark_mode_checkbox.setText(lang.lang.get("Dark mode"))
        self.follow_system_checkbox.setText(lang.lang.get("Follow system"))
        self.custom_folder_edit.setPlaceholderText(lang.lang.get("Path to custom output folder"))
        # Find browse button
        for child in self.findChildren(QPushButton):
            if child.text() == "Browse" or child.text() == "浏览" or child.text() == "参照":
                child.setText(lang.lang.get("Browse"))
        # Tab titles
        tabs = self.findChild(QTabWidget)
        if tabs:
            tabs.setTabText(0, lang.lang.get("General"))
            tabs.setTabText(1, lang.lang.get("Advanced"))
        # Advanced group
        self.thread_spin.setToolTip(lang.lang.get("0 = auto (no -threads), 1-64 = limit"))
        self.shutdown_check.setText(lang.lang.get("Shutdown after conversion"))
        self.delete_source_check.setText(lang.lang.get("Delete source after conversion"))
        self.temp_dir_edit.setPlaceholderText(lang.lang.get("Temporary folder (leave empty for system temp)"))
        # close button
        for btn in self.findChildren(QPushButton):
            if btn.text() in ("Close", "关闭", "閉じる"):
                btn.setText(lang.lang.get("Close"))

        if language_data is not None:
            idx = self.language_combo.findData(language_data)
            if idx >= 0:
                self.language_combo.setCurrentIndex(idx)
        preset_idx = self.preset_combo.findText(preset_text)
        if preset_idx >= 0:
            self.preset_combo.setCurrentIndex(preset_idx)

    # ---------- About Dialog (unchanged, can add translation later) ----------
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(lang.lang.get("About Everything Converter"))
        self.resize(420, 320)

        layout = QFormLayout(self)
        title = QLabel(f"<b>{lang.lang.get('EverythingConverter')}</b>")
        title.setTextFormat(Qt.RichText)
        layout.addRow(title)
        layout.addRow(lang.lang.get("Version"), QLabel(APP_VERSION))
        layout.addRow(lang.lang.get("Build"), QLabel(BUILD_TYPE))
        layout.addRow(lang.lang.get("Python"), QLabel(platform.python_version()))
        from PyQt5.QtCore import QT_VERSION_STR
        layout.addRow(lang.lang.get("Qt"), QLabel(QT_VERSION_STR))
        layout.addRow(lang.lang.get("FFmpeg"), QLabel(ffmpeg_version()))
        homepage = QLabel('<a href="https://example.com">https://example.com</a>')
        homepage.setOpenExternalLinks(True)
        layout.addRow(lang.lang.get("Homepage"), homepage)
        layout.addRow(lang.lang.get("License"), QLabel("MIT"))

        close_button = QPushButton(lang.lang.get("Close"))
        close_button.clicked.connect(self.accept)
        layout.addRow(close_button)


# ---------- Main Window ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("EverythingConverter", "Settings")
        self.available_converters = list(CONVERTERS)
        self.converter_thread = None
        self.current_speed = "0.00 MB/s"
        self._output_files = []
        self.queue_controller = QueueController()
        self._row_options = {}
        self._is_conversion_paused = False

        self.load_general_settings()

        self._create_actions()
        self._create_menu_bar()
        self._create_tool_bar()
        self._create_status_bar()
        self._create_central_ui()
        self.retranslate_ui()

        self.tray_icon = None
        self.setup_tray()

    def retranslate_ui(self):
        self.setWindowTitle(lang.lang.get("EverythingConverter"))
        # Actions
        self.exit_action.setText(lang.lang.get("Exit"))
        self.open_action.setText(lang.lang.get("Open"))
        self.convert_action.setText(lang.lang.get("Convert"))
        self.settings_action.setText(lang.lang.get("Settings"))
        self.about_action.setText(lang.lang.get("About Everything Converter"))
        # Menu bar - since we don't store references, we set directly
        file_menu = self.menuBar().actions()[0]
        tools_menu = self.menuBar().actions()[1]
        help_menu = self.menuBar().actions()[2]
        file_menu.setText(lang.lang.get("File"))
        tools_menu.setText(lang.lang.get("Tools"))
        help_menu.setText(lang.lang.get("Help"))
        # Status bar
        self.statusBar().showMessage(lang.lang.get("Ready"))
        # Drop area
        self.drop_area.retranslate()
        # Search placeholder
        self.search_bar.setPlaceholderText(lang.lang.get("Search conversions..."))
        # File queue header label
        self.file_queue_label.setText(lang.lang.get("File Queue (each file can choose its own target format)"))
        # Buttons
        self.add_file_btn.setText(lang.lang.get("Add Files"))
        self.clear_all_btn.setText(lang.lang.get("Clear All"))
        # Converter list label
        self.converter_list_label.setText(lang.lang.get("Converter List (global fallback if no per-file selection)"))
        # Detected extension label
        self.detected_extension_label.setText(lang.lang.get("Drop a file to detect available conversions"))
        # Destination label
        self.destination_label.setText(lang.lang.get("Destination path will appear after selecting a conversion"))
        # Converter description label
        self.converter_description_label.setText(lang.lang.get("Select a conversion to see the target format description"))
        # Conversion view
        self.conversion_title.setText(lang.lang.get("Converting files..."))
        self.current_converter_label.setText(f"{lang.lang.get('Current Converter:')} -")
        self.current_file_label.setText(f"{lang.lang.get('File:')} -")
        self.conversion_info_label.setText("0 / 0 files | 0.00 MB/s")
        # Timing labels (children of timing_container)
        for child in self.timing_container.findChildren(QLabel):
            if child.text() in ("Elapsed:", "已用时间:", "経過時間:"):
                child.setText(lang.lang.get("Elapsed:"))
            elif child.text() in ("Remaining:", "剩余时间:", "残り時間:"):
                child.setText(lang.lang.get("Remaining:"))
        self.pause_button.setText(lang.lang.get("Pause"))
        self.cancel_button.setText(lang.lang.get("Cancel"))
        # Completion panel
        self.complete_label.setText(lang.lang.get("Conversion Complete!"))
        self.open_folder_btn.setText(lang.lang.get("Open Folder"))
        self.open_file_btn.setText(lang.lang.get("Open File"))
        self.back_btn.setText(lang.lang.get("Back"))
        # Sidebar items (they are set dynamically, but the first item is Favorites)
        if self.sidebar.topLevelItemCount() > 0:
            fav_item = self.sidebar.topLevelItem(0)
            if fav_item:
                fav_item.setText(0, f"{lang.lang.get('Favorites')} (0)")
        # File formats header
        if self.sidebar.topLevelItemCount() > 1:
            formats_item = self.sidebar.topLevelItem(1)
            if formats_item:
                formats_item.setText(0, lang.lang.get("File Formats"))
        # Refresh sidebar counts
        self.update_sidebar_counts()

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
            QTableWidget, QListWidget, QLineEdit, QComboBox, QSpinBox, QTimeEdit {
                background: #3c3c3c; color: #eee; border: 1px solid #555; border-radius: 6px; padding: 5px;
            }
            QTableWidget::item { color: #eee; }
            QHeaderView::section { background: #3c3c3c; color: #eee; border: 1px solid #555; }
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
        self.exit_action = QAction(lang.lang.get("Exit"), self)
        self.exit_action.triggered.connect(self.close)

        self.open_action = QAction(lang.lang.get("Open"), self)
        self.open_action.triggered.connect(self.browse_files)

        self.convert_action = QAction(lang.lang.get("Convert"), self)
        self.convert_action.triggered.connect(self.convert_selected_files)

        self.settings_action = QAction(lang.lang.get("Settings"), self)
        self.settings_action.triggered.connect(self.show_settings)

        self.about_action = QAction(lang.lang.get("About Everything Converter"), self)
        self.about_action.triggered.connect(self.show_about)

    def _create_menu_bar(self):
        file_menu = self.menuBar().addMenu(lang.lang.get("File"))
        file_menu.addAction(self.exit_action)

        tools_menu = self.menuBar().addMenu(lang.lang.get("Tools"))
        tools_menu.addAction(self.settings_action)

        help_menu = self.menuBar().addMenu(lang.lang.get("Help"))
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
        status_bar.showMessage(lang.lang.get("Ready"))

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
        self.sidebar.setRootIsDecorated(True)
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
        self.search_bar.setPlaceholderText(lang.lang.get("Search conversions..."))
        self.search_bar.textChanged.connect(self.on_search_text_changed)

        # File queue header with buttons
        file_queue_widget = QWidget()
        file_queue_layout = QHBoxLayout(file_queue_widget)
        file_queue_layout.setContentsMargins(0, 0, 0, 0)
        self.file_queue_label = QLabel(lang.lang.get("File Queue (each file can choose its own target format)"))
        file_queue_layout.addWidget(self.file_queue_label)
        file_queue_layout.addStretch()
        self.add_file_btn = QPushButton(lang.lang.get("Add Files"))
        self.add_file_btn.clicked.connect(self.browse_files)
        self.clear_all_btn = QPushButton(lang.lang.get("Clear All"))
        self.clear_all_btn.clicked.connect(self.clear_all_files)
        file_queue_layout.addWidget(self.add_file_btn)
        file_queue_layout.addWidget(self.clear_all_btn)

        self.file_table = QTableWidget(0, 6)
        self.file_table.setHorizontalHeaderLabels([
            lang.lang.get("Filename"),
            lang.lang.get("Target"),
            lang.lang.get("Metadata"),
            lang.lang.get("Estimate"),
            lang.lang.get("Status"),
            lang.lang.get("Options")
        ])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.file_table.setColumnWidth(1, 190)
        self.file_table.setColumnWidth(2, 240)
        self.file_table.setColumnWidth(3, 190)
        self.file_table.setColumnWidth(4, 140)
        self.file_table.setColumnWidth(5, 72)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.setDragEnabled(False)
        self.file_table.setMinimumHeight(150)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.doubleClicked.connect(self._open_selected_row_options)
        self.file_table.customContextMenuRequested.connect(self.show_file_context_menu)

        self.main_convert_btn = QPushButton(lang.lang.get("Convert"))
        self.main_convert_btn.setObjectName("mainConvertButton")
        self.main_convert_btn.setMinimumHeight(42)
        self.main_convert_btn.setStyleSheet("QPushButton#mainConvertButton { background: #2e7d32; color: white; font-weight: bold; }")
        self.main_convert_btn.clicked.connect(self.convert_selected_files)

        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self.handle_files)
        self.drop_area.browse_requested.connect(self.browse_files)

        self.detected_extension_label = QLabel(lang.lang.get("Drop a file to detect available conversions"))
        self.detected_extension_label.setObjectName("detectedExtensionLabel")

        self.converter_list_label = QLabel(lang.lang.get("Converter List (global fallback if no per-file selection)"))
        self.converter_list = QListWidget()
        self.converter_list.setObjectName("converterList")
        self.converter_list.setMinimumHeight(110)
        self.converter_list.currentItemChanged.connect(self.update_converter_details)
        self.converter_list.itemDoubleClicked.connect(self.convert_selected_files)

        self.converter_description_label = QLabel(lang.lang.get("Select a conversion to see the target format description"))
        self.converter_description_label.setObjectName("converterDescriptionLabel")
        self.converter_description_label.setWordWrap(True)
        self.converter_description_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.converter_description_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.description_scroll_area = QScrollArea()
        self.description_scroll_area.setWidgetResizable(True)
        self.description_scroll_area.setWidget(self.converter_description_label)
        self.description_scroll_area.setMaximumHeight(150)
        self.description_scroll_area.setFrameShape(QFrame.StyledPanel)

        self.destination_label = QLabel(lang.lang.get("Destination path will appear after selecting a conversion"))
        self.destination_label.setObjectName("destinationLabel")
        self.destination_label.setWordWrap(True)

        content_layout.addWidget(self.search_bar)
        content_layout.addWidget(self.detected_extension_label)
        content_layout.addWidget(self.drop_area)
        content_layout.addWidget(file_queue_widget)
        content_layout.addWidget(self.file_table)
        content_layout.addWidget(self.main_convert_btn, alignment=Qt.AlignRight)
        content_layout.addWidget(self.converter_list_label)
        content_layout.addWidget(self.converter_list)
        content_layout.addWidget(self.description_scroll_area)
        content_layout.addWidget(self.destination_label)

        # Stacked widget
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(content)

        # Conversion view
        conversion_view = QWidget()
        conversion_layout = QVBoxLayout(conversion_view)
        conversion_layout.setAlignment(Qt.AlignCenter)
        conversion_layout.setSpacing(16)

        self.conversion_title = QLabel(lang.lang.get("Converting files..."))
        self.conversion_title.setObjectName("conversionTitle")
        self.conversion_title.setAlignment(Qt.AlignCenter)

        self.current_converter_label = QLabel(f"{lang.lang.get('Current Converter:')} -")
        self.current_converter_label.setAlignment(Qt.AlignCenter)

        self.current_file_label = QLabel(f"{lang.lang.get('File:')} -")
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

        self.timing_container = QWidget()
        timing_layout = QHBoxLayout(self.timing_container)
        timing_layout.addWidget(QLabel(lang.lang.get("Elapsed:")))
        self.elapsed_label = QLabel("00:00:00")
        timing_layout.addWidget(self.elapsed_label)
        timing_layout.addStretch()
        timing_layout.addWidget(QLabel(lang.lang.get("Remaining:")))
        self.remaining_label = QLabel("00:00:00")
        timing_layout.addWidget(self.remaining_label)

        self.pause_button = QPushButton(lang.lang.get("Pause"))
        self.pause_button.clicked.connect(self.toggle_pause_conversion)

        self.cancel_button = QPushButton(lang.lang.get("Cancel"))
        self.cancel_button.clicked.connect(self.cancel_conversion)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()

        # Completion panel
        self.completion_widget = QWidget()
        completion_layout = QVBoxLayout(self.completion_widget)
        completion_layout.setAlignment(Qt.AlignCenter)
        completion_layout.setSpacing(16)

        self.complete_label = QLabel(lang.lang.get("Conversion Complete!"))
        self.complete_label.setObjectName("completionTitle")
        self.complete_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.complete_label.setAlignment(Qt.AlignCenter)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignCenter)

        folder_icon_path = ICONS / "folder.svg"
        folder_icon = QIcon(str(folder_icon_path)) if folder_icon_path.exists() else QIcon()
        self.open_folder_btn = QPushButton(folder_icon, lang.lang.get("Open Folder"))
        self.open_folder_btn.clicked.connect(self._open_output_folder)

        file_icon_path = ICONS / "file.svg"
        file_icon = QIcon(str(file_icon_path)) if file_icon_path.exists() else QIcon()
        self.open_file_btn = QPushButton(file_icon, lang.lang.get("Open File"))
        self.open_file_btn.clicked.connect(self._open_output_file)

        self.back_btn = QPushButton(lang.lang.get("Back"))
        self.back_btn.clicked.connect(self._go_back_to_main)

        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addWidget(self.open_file_btn)
        btn_layout.addWidget(self.back_btn)

        completion_layout.addWidget(self.complete_label)
        completion_layout.addLayout(btn_layout)
        self.completion_widget.hide()

        conversion_layout.addStretch()
        conversion_layout.addWidget(self.conversion_title)
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

        favorites_item = QTreeWidgetItem([f"{lang.lang.get('Favorites')} (0)"])
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

        file_formats = QTreeWidgetItem([lang.lang.get("File Formats")])
        file_formats.setExpanded(True)
        self.sidebar.addTopLevelItem(file_formats)

        categories = [
            ("Image", "image.svg", "Image"),
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
                fav_item.setText(0, f"{lang.lang.get('Favorites')} ({total_converters})")

    def filter_converters_by_category(self, converters):
        if not self.current_category:
            return converters
        return [c for c in converters if c.category.lower() == self.current_category.lower()]

    # ---------- File handling ----------
    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            lang.lang.get("Open files"),
            "",
            "All files (*)",
        )
        if files:
            self.handle_files(files)

    def clear_all_files(self):
        if self.file_table.rowCount() == 0:
            return
        reply = QMessageBox.question(
            self, lang.lang.get("Clear All"),
            lang.lang.get("Remove all files from the conversion queue?"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.file_table.setRowCount(0)
            self.queue_controller.clear()
            self.drop_area.setVisible(True)
            self.statusBar().showMessage(lang.lang.get("Queue cleared"))

    def handle_files(self, files):
        for file_path in files:
            self._add_file_to_table(file_path)
        self.drop_area.setVisible(True)
        self.statusBar().showMessage(f"{self.file_table.rowCount()} {lang.lang.get('file(s) in queue')}")

    def _add_file_to_table(self, file_path):
        if not self.queue_controller.add(file_path):
            self.statusBar().showMessage(lang.lang.get("File already in queue"))
            return

        row = self.file_table.rowCount()
        self.file_table.insertRow(row)

        name_item = QTableWidgetItem(Path(file_path).name)
        name_item.setData(Qt.UserRole, file_path)
        self.file_table.setItem(row, 0, name_item)

        combo = QComboBox()
        converters = find_converters(file_path)
        if converters:
            for conv in converters:
                combo.addItem(f"{conv.output_extension.upper()}", conv)
            combo.setCurrentIndex(0)
        else:
            combo.addItem(lang.lang.get("无可用转换"), None)
            combo.setEnabled(False)
        self.file_table.setCellWidget(row, 1, combo)

        metadata = self._format_queue_metadata(file_path)
        self.file_table.setItem(row, 2, QTableWidgetItem(metadata))

        estimate_item = QTableWidgetItem(self._estimate_output_size_text(file_path, combo.currentData() if converters else None, {}))
        self.file_table.setItem(row, 3, estimate_item)

        status_item = QTableWidgetItem("🟢 Ready")
        status_item.setTextAlignment(Qt.AlignCenter)
        self.file_table.setItem(row, 4, status_item)

        combo.currentIndexChanged.connect(lambda _idx, r=row: self._refresh_row_estimate(r))

        options_btn = QPushButton("⚙")
        options_btn.setFixedSize(32, 24)
        options_btn.clicked.connect(lambda _, r=row: self._open_row_options(r))
        self.file_table.setCellWidget(row, 5, options_btn)

        self._row_options[row] = {}
        self._update_queue_preview()

    def _format_queue_metadata(self, file_path):
        info = get_media_info(file_path) or {}
        ext = Path(file_path).suffix.lower()
        size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
        parts = []

        if info.get("width") and info.get("height"):
            parts.append(f"{info['width']}×{info['height']}")
        if info.get("video_codec"):
            parts.append(info["video_codec"].upper())
        if info.get("fps"):
            parts.append(f"{float(info['fps']):.0f} FPS")
        if info.get("duration"):
            parts.append(self._format_short_duration(info["duration"]))
        if info.get("audio_codec"):
            parts.append(info["audio_codec"].upper())
        if info.get("sample_rate"):
            rate_khz = info["sample_rate"] / 1000.0
            parts.append(f"{rate_khz:.1f} kHz")
        if info.get("channels"):
            channels_name = "Stereo" if info["channels"] >= 2 else "Mono"
            parts.append(channels_name)
        if info.get("bits_per_sample"):
            parts.append(f"{info['bits_per_sample']}-bit")

        if not parts:
            if ext in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}:
                parts.append(Path(file_path).suffix.upper().lstrip("."))
            elif ext in {".mp3", ".flac", ".wav", ".ogg", ".aac", ".m4a"}:
                parts.append(Path(file_path).suffix.upper().lstrip("."))
            elif size:
                parts.append(self._format_size(size))
            else:
                parts.append("—")

        return " | ".join(parts) if parts else "—"

    def _estimate_output_size_text(self, file_path, converter, opts):
        size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
        if not size:
            return "—"
        estimate = estimate_output_size(
            file_path,
            converter,
            opts,
            default_preset=self.settings.value("default_preset", "None", type=str),
        )
        return (
            f"≈{self._format_size(estimate['estimated'])} | "
            f"Save {self._format_size(estimate['saved'])} "
            f"({estimate['percent']:.0f}%) {estimate['confidence']}"
        )

    def _refresh_row_estimate(self, row):
        if row < 0 or row >= self.file_table.rowCount():
            return
        item = self.file_table.item(row, 0)
        combo = self.file_table.cellWidget(row, 1)
        if not item or not combo:
            return
        self.file_table.setItem(row, 3, QTableWidgetItem(
            self._estimate_output_size_text(item.data(Qt.UserRole), combo.currentData(), self._row_options.get(row, {}))
        ))
        self._update_queue_preview()

    def _format_short_duration(self, seconds):
        seconds = float(seconds or 0)
        if seconds <= 0:
            return "—"
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            m, s = divmod(seconds, 60)
            return f"{int(m):02d}:{int(s):02d}"
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

    def _format_size(self, size):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _open_row_options(self, row):
        file_path = self.file_table.item(row, 0).data(Qt.UserRole)
        converter = self.file_table.cellWidget(row, 1).currentData() if self.file_table.cellWidget(row, 1) else None
        if converter is None:
            converter = self.selected_converter()
        if converter is None:
            QMessageBox.warning(self, lang.lang.get("No converter"), lang.lang.get("Please select a converter first."))
            return

        dlg = ConversionOptionsDialog([file_path], converter, self, initial_options=self._row_options.get(row, {}))
        if dlg.exec() == QDialog.Accepted:
            opts = dlg.get_options()
            self._row_options[row] = opts
            self._refresh_row_estimate(row)
            self._update_queue_preview()

    def _open_selected_row_options(self):
        row = self.file_table.currentRow()
        if row >= 0:
            self._open_row_options(row)

    def _update_queue_preview(self):
        current_row = self.file_table.currentRow()
        if current_row >= 0:
            file_path = self.file_table.item(current_row, 0).data(Qt.UserRole)
            combo = self.file_table.cellWidget(current_row, 1)
            converter = combo.currentData() if combo else None
            if converter is None:
                self.destination_label.setText(lang.lang.get("Destination path will appear after selecting a conversion"))
                return
            preview = self._build_output_path(file_path, converter.output_extension)
            self.destination_label.setText(f"{lang.lang.get('Output:')} {preview}")

    # ---------- Conversion ----------
    def convert_selected_files(self):
        if self.converter_thread and self.converter_thread.isRunning():
            QMessageBox.information(self, lang.lang.get("Conversion in progress"), lang.lang.get("Please wait."))
            return
        if self.file_table.rowCount() == 0:
            QMessageBox.information(self, lang.lang.get("No files"), lang.lang.get("Add files first."))
            return

        task_list = []
        delete_source = False
        shutdown = False
        for row in range(self.file_table.rowCount()):
            name_item = self.file_table.item(row, 0)
            input_file = name_item.data(Qt.UserRole)
            combo = self.file_table.cellWidget(row, 1)
            converter = combo.currentData() if combo else None
            if converter is None:
                converter = self.selected_converter()
            if converter is None:
                continue

            opts = dict(self._row_options.get(row, {}))
            opts.setdefault("preset", self.settings.value("default_preset", "None", type=str))
            opts.setdefault("copy_mode", False)
            opts.setdefault("copy_audio", False)
            opts.setdefault("start_time", None)
            opts.setdefault("end_time", None)
            opts.setdefault("threads", self.settings.value("default_threads", 0, type=int))
            opts.setdefault("delete_source", False)
            opts.setdefault("shutdown", False)
            opts.setdefault("extra_args", [])
            opts.setdefault("video_codec", DEFAULT_VIDEO_CODEC.get(converter.output_extension, None))
            opts.setdefault("audio_codec", DEFAULT_AUDIO_CODEC.get(converter.output_extension, None))

            preset_args = PRESETS.get(opts.get("preset", "None"), [])
            extra_args = list(opts.get("extra_args", [])) + list(preset_args)
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
            if "start_time" in opts and opts["start_time"] is not None:
                extra_args.extend(["-ss", str(opts["start_time"])])
            if "end_time" in opts and opts["end_time"] is not None:
                extra_args.extend(["-to", str(opts["end_time"])])
            if scale:
                extra_args.extend(["-vf", f"scale={scale}"])

            output_path = self._build_output_path(input_file, converter.output_extension, opts)
            configured_converter = self._configured_converter(converter, opts, extra_args)
            task_list.append((configured_converter, input_file, output_path))
            self._set_row_status(row, "🟡 Waiting")

        if not task_list:
            QMessageBox.warning(self, lang.lang.get("No converter"), lang.lang.get("No queued file has an available converter."))
            return

        self._output_files = [output_file for _, _, output_file in task_list]
        self.progress_bar.setMaximum(len(task_list))
        self.progress_bar.setValue(0)
        self.conversion_progress_bar.setValue(0)
        self.conversion_info_label.setText(f"0 / {len(task_list)} files | 0.00 MB/s")

        logger.info("Starting conversion:")
        for idx, (converter, input_file, output_file) in enumerate(task_list, start=1):
            logger.info(f"  {idx}. {converter.name}: {input_file} -> {output_file}")

        self.converter_thread = BatchConversionWorker(task_list, delete_source=delete_source)
        self.converter_thread.progress_updated.connect(self.update_conversion_progress)
        self.converter_thread.per_file_progress.connect(self.update_per_file_progress)
        self.converter_thread.status_message.connect(self.update_status_message)
        self.converter_thread.speed_updated.connect(self.update_speed)
        self.converter_thread.current_file_updated.connect(self.update_current_file)
        self.converter_thread.time_updated.connect(self.update_time_labels)
        self.converter_thread.conversion_finished.connect(self.finish_conversion)

        self.set_ui_enabled(False)
        self.converter_thread.start()

    def update_conversion_progress(self, value):
        self.progress_bar.setValue(value)
        total = self.progress_bar.maximum()
        self.conversion_info_label.setText(f"{value} / {total} files | {self.current_speed}")

    def update_per_file_progress(self, value):
        self.conversion_progress_bar.setValue(value)

    def update_status_message(self, message):
        self.statusBar().showMessage(message)

    def update_speed(self, speed):
        self.current_speed = speed
        total = self.progress_bar.maximum()
        done = self.progress_bar.value()
        self.conversion_info_label.setText(f"{done} / {total} files | {speed}")

    def update_current_file(self, file_name):
        self.current_file_label.setText(f"{lang.lang.get('File:')} {file_name}")
        self._set_row_status_by_filename(file_name, "🔵 Processing")

    def update_time_labels(self, elapsed, remaining):
        self.elapsed_label.setText(elapsed)
        self.remaining_label.setText(remaining)

    def finish_conversion(self, converted, errors):
        self.set_ui_enabled(True)
        self.progress_bar.setValue(100)
        self.conversion_progress_bar.setValue(100)
        self.statusBar().showMessage(lang.lang.get("Conversion complete"))

        self._mark_conversion_finished_rows(converted, errors)
        self.completion_widget.show()

        if errors and len(errors) > 0:
            error_message = lang.lang.get("Conversion completed with errors:")
            for error in errors:
                error_message += f"\n- {error}"
            QMessageBox.warning(self, lang.lang.get("Errors occurred"), error_message)
        else:
            QMessageBox.information(self, lang.lang.get("Success"), lang.lang.get("All files converted successfully"))

        # Update row statuses
        for row in range(self.file_table.rowCount()):
            name_item = self.file_table.item(row, 0)
            input_file = name_item.data(Qt.UserRole)
            combo = self.file_table.cellWidget(row, 1)
            converter = combo.currentData() if combo else None

            if converter is None:
                continue

            file_name = Path(input_file).name
            failed_names = {str(err).split(":", 1)[0].strip() for err in errors}
            if file_name in failed_names:
                self._set_row_status(row, "🔴 Failed ✕")
            else:
                self._set_row_status(row, "✅ Done ✓")

    def _set_row_status(self, row, text):
        if row < 0 or row >= self.file_table.rowCount():
            return
        item = self.file_table.item(row, 4)
        if item is None:
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            self.file_table.setItem(row, 4, item)
        else:
            item.setText(text)
            item.setTextAlignment(Qt.AlignCenter)

    def _set_row_status_by_filename(self, filename, text):
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item and Path(item.data(Qt.UserRole)).name == filename:
                self._set_row_status(row, text)
                return

    def _mark_conversion_finished_rows(self, converted, errors):
        failed_names = set()
        for err in errors:
            failed_names.add(str(err).split(":", 1)[0].strip())

        for row in range(self.file_table.rowCount()):
            file_name = Path(self.file_table.item(row, 0).data(Qt.UserRole)).name
            if file_name in failed_names:
                self._set_row_status(row, "🔴 Failed ✕")
            else:
                self._set_row_status(row, "✅ Done ✓")
    # ---------- Converter list and app actions ----------
    def refresh_converter_list(self):
        self.converter_list.clear()
        converters = self.filter_converters_by_category(search_converters(self.search_bar.text(), self.available_converters))
        for converter in converters:
            item = QListWidgetItem(f"{converter.name} ({converter.output_extension.upper()})")
            item.setData(Qt.UserRole, converter)
            self.converter_list.addItem(item)

    def selected_converter(self):
        item = self.converter_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def update_converter_details(self, current, previous=None):
        converter = current.data(Qt.UserRole) if current else None
        if not converter:
            self.converter_description_label.setText(lang.lang.get("Select a conversion to see the target format description"))
            self.destination_label.setText(lang.lang.get("Destination path will appear after selecting a conversion"))
            return
        inputs = ", ".join(converter.input_extensions)
        desc = EXTENSION_DESCRIPTIONS.get(converter.output_extension.lower(), "")
        self.converter_description_label.setText(
            f"{converter.name}\nInput: {inputs}\nOutput: {converter.output_extension.upper()}\n{desc}"
        )
        self._update_queue_preview()

    def _build_output_path(self, input_file, output_extension, opts=None):
        input_path = Path(input_file)
        output_dir = input_path.parent
        mode = self.settings.value("output_folder_mode", 0, type=int)
        if mode == 2:
            custom = self.settings.value("custom_folder", "", type=str)
            if custom:
                output_dir = Path(custom)
        output_path = output_dir / f"{input_path.stem}{output_extension}"
        counter = 1
        while output_path.exists() and output_path.resolve() != input_path.resolve():
            output_path = output_dir / f"{input_path.stem}_{counter}{output_extension}"
            counter += 1
        return str(output_path)

    def _configured_converter(self, converter, opts, extra_args):
        if isinstance(converter, FFmpegConverter):
            return FFmpegConverter(
                converter.name, converter.input_extensions, converter.output_extension,
                video_codec=opts.get("video_codec"), audio_codec=opts.get("audio_codec"),
                extra_args=extra_args, threads=opts.get("threads", 0),
                copy_mode=opts.get("copy_mode", False), copy_audio=opts.get("copy_audio", False),
                start_time=opts.get("start_time"), end_time=opts.get("end_time"),
                scale=opts.get("scale")
            )
        return converter

    def show_file_context_menu(self, pos):
        row = self.file_table.currentRow()
        if row < 0:
            return
        menu = QMenu(self)
        edit_action = menu.addAction(lang.lang.get("Edit Options"))
        remove_action = menu.addAction(lang.lang.get("Remove"))
        open_folder_action = menu.addAction(lang.lang.get("Reveal Output Folder"))
        copy_path_action = menu.addAction(lang.lang.get("Copy Path"))
        action = menu.exec_(self.file_table.viewport().mapToGlobal(pos))
        if action == edit_action:
            self._open_row_options(row)
        elif action == remove_action:
            item = self.file_table.item(row, 0)
            if item:
                self.queue_controller.discard(item.data(Qt.UserRole))
            self.file_table.removeRow(row)
        elif action == open_folder_action:
            self._open_output_folder()
        elif action == copy_path_action:
            item = self.file_table.item(row, 0)
            if item:
                QApplication.clipboard().setText(item.data(Qt.UserRole))

    def set_ui_enabled(self, enabled):
        self.convert_action.setEnabled(enabled)
        self.main_convert_btn.setEnabled(enabled)
        # Keep queue browsing and adding files available while conversion runs.
        self.open_action.setEnabled(True)
        self.add_file_btn.setEnabled(True)
        self.clear_all_btn.setEnabled(True)
        self.converter_list.setEnabled(True)
        self.file_table.setEnabled(True)
        self.content_stack.setCurrentIndex(0 if enabled else 1)

    def _open_output_folder(self):
        path = Path(self._output_files[0]).parent if self._output_files else Path.cwd()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_output_file(self):
        if self._output_files:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._output_files[0]))

    def _go_back_to_main(self):
        self.completion_widget.hide()
        self.content_stack.setCurrentIndex(0)

    def show_settings(self):
        SettingsDialog(self).exec()

    def show_about(self):
        AboutDialog(self).exec()

    def toggle_pause_conversion(self):
        if not self.converter_thread:
            return
        if self._is_conversion_paused:
            self.converter_thread.resume()
            self.pause_button.setText(lang.lang.get("Pause"))
        else:
            self.converter_thread.pause()
            self.pause_button.setText(lang.lang.get("Resume"))
        self._is_conversion_paused = not self._is_conversion_paused

    def cancel_conversion(self):
        if self.converter_thread:
            self.converter_thread.cancel()
