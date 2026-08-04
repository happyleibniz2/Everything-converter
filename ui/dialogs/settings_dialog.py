from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
    QHBoxLayout
)

import lang
from ui.options_dialog import PRESETS


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
            if child.text() in ("Browse", "浏览", "参照"):
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