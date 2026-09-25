"""Settings as a scrollable page of Fluent setting cards.

Replaces the old tabbed modal dialog. There is no OK button: theme, accent
colour, language, output rules, parallelism and the default preset are each
written to ``QSettings`` (and flushed with ``sync()``) the moment the control
changes, which removes a whole class of "did my change stick?" confusion.
"""

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    CaptionLabel, ColorPickerButton, ComboBox, FluentIcon, LineEdit, PushButton,
    ScrollArea, SettingCard, SettingCardGroup, SpinBox, SubtitleLabel,
    SwitchButton,
)

import lang
from converters.presets import PRESETS
from utils.paths import LOGS

LANGUAGES = [("English", "en_US"), ("\u4e2d\u6587", "zh_CN"), ("\u65e5\u672c\u8a9e", "ja_JP")]
THEMES = [("Follow system", "auto"), ("Light", "light"), ("Dark", "dark")]
OUTPUT_MODES = ["Same folder as the original", "Ask every time", "Custom folder"]
OVERWRITE_MODES = ["Rename (keep both)", "Overwrite", "Skip"]

ACCENT_DEFAULT = "#4f7cff"


def _clamp(index: int, count: int) -> int:
    """Return a valid combo index, falling back to the first option.

    Settings persist across versions, so a value written by an older build may
    name an option that no longer exists. Falling back to index 0 keeps this
    consistent with the conversion layer, which defaults out-of-range policies
    to their first member rather than their last.
    """
    try:
        value = int(index)
    except (TypeError, ValueError):
        return 0
    return value if 0 <= value < count else 0


class ControlCard(SettingCard):
    """Setting card hosting one arbitrary control on the right."""

    def __init__(self, icon, title, content, control, parent=None):
        super().__init__(icon, title, content, parent)
        self.control = control
        control.setParent(self)
        self.hBoxLayout.addWidget(control, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)


class SettingsInterface(ScrollArea):
    """Live-applied application preferences.

    There is no OK/Apply button anywhere on this page: every control writes
    straight to ``QSettings`` the moment it changes, and ``settingsChanged``
    lets the rest of the app react (re-estimating queue sizes, refreshing
    destination previews, ...) without ever losing an edit.
    """

    language_changed = Signal(str)
    appearance_changed = Signal()
    #: Emitted after a preference has been persisted; carries the key.
    settingsChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsInterface")
        self.settings = QSettings("EverythingConverter", "Settings")
        self._loading = False

        self._view = QWidget(self)
        self.setWidget(self._view)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Otherwise the scroll area paints an opaque panel over the mica window.
        self.setStyleSheet("QScrollArea{background:transparent;border:none}")
        self._view.setStyleSheet("QWidget{background:transparent}")

        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self._view)
        layout.setContentsMargins(26, 18, 26, 26)
        layout.setSpacing(18)

        self.heading = SubtitleLabel(lang.lang.get("Settings"), self._view)
        layout.addWidget(self.heading)
        # Make it obvious there is nothing to confirm: edits persist live.
        self.autosave_note = CaptionLabel(
            lang.lang.get("Changes are saved automatically as you make them."),
            self._view)
        layout.addWidget(self.autosave_note)
        layout.addWidget(self._appearance_group())
        layout.addWidget(self._output_group())
        layout.addWidget(self._performance_group())
        layout.addWidget(self._maintenance_group())
        layout.addStretch(1)

    # ---------------------------------------------------------- appearance --
    def _appearance_group(self):
        group = SettingCardGroup(lang.lang.get("Appearance"), self._view)

        self.theme_combo = ComboBox()
        for label, value in THEMES:
            self.theme_combo.addItem(lang.lang.get(label), userData=value)
        self.theme_combo.setMinimumWidth(160)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.theme_card = ControlCard(
            FluentIcon.BRUSH, lang.lang.get("Theme"),
            lang.lang.get("Light, dark, or match Windows"), self.theme_combo, group)
        group.addSettingCard(self.theme_card)

        self.accent_button = ColorPickerButton(ACCENT_DEFAULT, lang.lang.get("Accent colour"))
        self.accent_button.colorChanged.connect(self._on_accent_changed)
        self.accent_card = ControlCard(
            FluentIcon.PALETTE, lang.lang.get("Accent colour"),
            lang.lang.get("Used for highlights and progress"), self.accent_button, group)
        group.addSettingCard(self.accent_card)

        self.mica_switch = SwitchButton()
        self.mica_switch.checkedChanged.connect(self._on_mica_changed)
        self.mica_card = ControlCard(
            FluentIcon.TRANSPARENT, lang.lang.get("Translucent background"),
            lang.lang.get("Mica effect, Windows 11 only"), self.mica_switch, group)
        group.addSettingCard(self.mica_card)

        self.language_combo = ComboBox()
        for label, code in LANGUAGES:
            self.language_combo.addItem(label, userData=code)
        self.language_combo.setMinimumWidth(160)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.language_card = ControlCard(
            FluentIcon.LANGUAGE, lang.lang.get("Language"),
            lang.lang.get("Interface language"), self.language_combo, group)
        group.addSettingCard(self.language_card)
        return group

    # -------------------------------------------------------------- output --
    def _output_group(self):
        group = SettingCardGroup(lang.lang.get("Output"), self._view)

        self.output_mode_combo = ComboBox()
        for label in OUTPUT_MODES:
            self.output_mode_combo.addItem(lang.lang.get(label))
        self.output_mode_combo.setMinimumWidth(220)
        self.output_mode_combo.currentIndexChanged.connect(self._on_output_mode_changed)
        self.output_mode_card = ControlCard(
            FluentIcon.SAVE_AS, lang.lang.get("Where to save"),
            lang.lang.get("Destination for converted files"), self.output_mode_combo, group)
        group.addSettingCard(self.output_mode_card)

        folder_host = QWidget()
        folder_row = QHBoxLayout(folder_host)
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(6)
        self.folder_edit = LineEdit()
        self.folder_edit.setMinimumWidth(230)
        self.folder_edit.setPlaceholderText(lang.lang.get("Choose a folder"))
        # textEdited fires only for user keystrokes (setText during _load does
        # not re-store); editingFinished catches focus-out and Enter as well.
        self.folder_edit.textEdited.connect(
            lambda text: self._store("custom_folder", text))
        self.folder_edit.editingFinished.connect(self._on_folder_edited)
        self.browse_button = PushButton(FluentIcon.FOLDER.icon(), lang.lang.get("Browse"))
        self.browse_button.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(self.browse_button)

        self.folder_card = ControlCard(
            FluentIcon.FOLDER, lang.lang.get("Custom folder"),
            lang.lang.get("Used when Custom folder is selected"), folder_host, group)
        group.addSettingCard(self.folder_card)

        self.overwrite_combo = ComboBox()
        for label in OVERWRITE_MODES:
            self.overwrite_combo.addItem(lang.lang.get(label))
        self.overwrite_combo.setMinimumWidth(220)
        self.overwrite_combo.currentIndexChanged.connect(
            lambda index: self._store("overwrite_behavior", index))
        self.overwrite_card = ControlCard(
            FluentIcon.COPY, lang.lang.get("If the file already exists"),
            lang.lang.get("How naming collisions are handled"), self.overwrite_combo, group)
        group.addSettingCard(self.overwrite_card)

        self.delete_source_switch = SwitchButton()
        self.delete_source_switch.checkedChanged.connect(
            lambda checked: self._store("delete_source", checked))
        self.delete_source_card = ControlCard(
            FluentIcon.DELETE, lang.lang.get("Delete originals after converting"),
            lang.lang.get("Applies to files added from now on. This cannot be undone."),
            self.delete_source_switch, group)
        group.addSettingCard(self.delete_source_card)
        return group

    # --------------------------------------------------------- performance --
    def _performance_group(self):
        group = SettingCardGroup(lang.lang.get("Performance"), self._view)

        self.parallel_spin = SpinBox()
        self.parallel_spin.setRange(0, 16)
        self.parallel_spin.setSpecialValueText(lang.lang.get("Auto"))
        self.parallel_spin.setMinimumWidth(160)
        self.parallel_spin.valueChanged.connect(
            lambda value: self._store("parallel_jobs", value))
        self.parallel_card = ControlCard(
            FluentIcon.SPEED_HIGH, lang.lang.get("Files at once"),
            lang.lang.get("How many conversions run in parallel. Auto uses half your cores."),
            self.parallel_spin, group)
        group.addSettingCard(self.parallel_card)

        self.threads_spin = SpinBox()
        self.threads_spin.setRange(0, 64)
        self.threads_spin.setSpecialValueText(lang.lang.get("Auto"))
        self.threads_spin.setMinimumWidth(160)
        self.threads_spin.valueChanged.connect(lambda value: self._store("threads", value))
        self.threads_card = ControlCard(
            FluentIcon.IOT, lang.lang.get("Threads per file"),
            lang.lang.get("Passed to ffmpeg as -threads. Auto lets ffmpeg choose."),
            self.threads_spin, group)
        group.addSettingCard(self.threads_card)

        self.preset_combo = ComboBox()
        for name in PRESETS:
            self.preset_combo.addItem(lang.lang.get(name), userData=name)
        self.preset_combo.setMinimumWidth(220)
        self.preset_combo.currentIndexChanged.connect(
            lambda _index: self._store("default_preset",
                                       self.preset_combo.currentData() or "None"))
        self.preset_card = ControlCard(
            FluentIcon.SETTING, lang.lang.get("Default quality preset"),
            lang.lang.get("Applied to files added from now on"), self.preset_combo, group)
        group.addSettingCard(self.preset_card)
        return group

    # --------------------------------------------------------- maintenance --
    def _maintenance_group(self):
        group = SettingCardGroup(lang.lang.get("Maintenance"), self._view)

        self.logs_button = PushButton(FluentIcon.FOLDER.icon(), lang.lang.get("Open"))
        self.logs_button.clicked.connect(self._open_logs)
        self.logs_card = ControlCard(
            FluentIcon.DOCUMENT, lang.lang.get("Log files"),
            lang.lang.get("Useful when reporting a problem"), self.logs_button, group)
        group.addSettingCard(self.logs_card)
        return group
    # ------------------------------------------------------------ handlers --
    def _store(self, key, value):
        """Persist one preference immediately — there is no OK button.

        ``QSettings.sync()`` forces the write to disk now rather than at an
        arbitrary later point, so a crash can never lose a change. Suppressed
        during ``_load`` so populating widgets does not re-save; the
        ``settingsChanged`` signal lets other parts of the app react live.
        """
        if self._loading:
            return
        self.settings.setValue(key, value)
        self.settings.sync()
        self.settingsChanged.emit(key)

    def _on_theme_changed(self, _index):
        value = self.theme_combo.currentData() or "auto"
        self._store("theme_mode", value)
        # Keep the legacy key in sync; older paths still read dark_mode.
        self._store("dark_mode", value == "dark")
        if not self._loading:
            self.appearance_changed.emit()

    def _on_accent_changed(self, color):
        self._store("accent_color", color.name())
        if not self._loading:
            self.appearance_changed.emit()

    def _on_mica_changed(self, checked):
        self._store("mica_enabled", checked)
        if not self._loading:
            self.appearance_changed.emit()

    def _on_language_changed(self, _index):
        code = self.language_combo.currentData() or "en_US"
        self._store("language", code)
        if not self._loading:
            self.language_changed.emit(code)

    def _on_output_mode_changed(self, index):
        self._store("output_folder_mode", index)
        # The custom-folder row is only meaningful for the Custom option.
        self.folder_card.setEnabled(index == 2)

    def _on_folder_edited(self):
        """Save the typed folder as soon as focus leaves the line edit."""
        self._store("custom_folder", self.folder_edit.text())

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, lang.lang.get("Select output folder"))
        if folder:
            self.folder_edit.setText(folder)
            self._store("custom_folder", folder)

    def _open_logs(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOGS)))

    def _sanitise(self, key: str, count: int) -> int:
        """Read a combo index, repairing the stored value if it is out of range."""
        raw = self.settings.value(key, 0, type=int)
        valid = _clamp(raw, count)
        if valid != raw:
            self.settings.setValue(key, valid)
        return valid

    # ---------------------------------------------------------------- load --
    def _load(self):
        self._loading = True
        try:
            stored_theme = self.settings.value("theme_mode", "", type=str)
            if not stored_theme:
                # Migrate from the old boolean-only setting.
                stored_theme = "dark" if self.settings.value("dark_mode", False, type=bool) else "auto"
            index = self.theme_combo.findData(stored_theme)
            self.theme_combo.setCurrentIndex(max(0, index))

            self.accent_button.setColor(
                self.settings.value("accent_color", ACCENT_DEFAULT, type=str) or ACCENT_DEFAULT
            )
            self.mica_switch.setChecked(self.settings.value("mica_enabled", True, type=bool))

            code = self.settings.value("language", "en_US", type=str) or "en_US"
            index = self.language_combo.findData(code)
            self.language_combo.setCurrentIndex(max(0, index))

            # An older build offered a fourth "Ask for name" overwrite option.
            # Rewrite any out-of-range value so the stored setting and the
            # conversion layer cannot disagree about what the user chose.
            mode = self._sanitise("output_folder_mode", self.output_mode_combo.count())
            self.output_mode_combo.setCurrentIndex(mode)
            self.folder_card.setEnabled(mode == 2)
            self.folder_edit.setText(self.settings.value("custom_folder", "", type=str))

            self.overwrite_combo.setCurrentIndex(
                self._sanitise("overwrite_behavior", self.overwrite_combo.count())
            )
            self.delete_source_switch.setChecked(
                self.settings.value("delete_source", False, type=bool)
            )

            self.parallel_spin.setValue(self.settings.value("parallel_jobs", 0, type=int))
            self.threads_spin.setValue(self.settings.value("threads", 0, type=int))

            preset = self.settings.value("default_preset", "None", type=str) or "None"
            index = self.preset_combo.findData(preset)
            self.preset_combo.setCurrentIndex(max(0, index))
        finally:
            self._loading = False

    # ---------------------------------------------------------------- i18n --
    def retranslate(self):
        self.heading.setText(lang.lang.get("Settings"))
        self.autosave_note.setText(
            lang.lang.get("Changes are saved automatically as you make them."))

        # Rebuild translated combo entries while preserving each selection.
        self._loading = True
        try:
            for combo, labels in (
                (self.theme_combo, [label for label, _value in THEMES]),
                (self.output_mode_combo, OUTPUT_MODES),
                (self.overwrite_combo, OVERWRITE_MODES),
            ):
                current = combo.currentIndex()
                for position, label in enumerate(labels):
                    combo.setItemText(position, lang.lang.get(label))
                combo.setCurrentIndex(current)

            current = self.preset_combo.currentIndex()
            for position, name in enumerate(PRESETS):
                self.preset_combo.setItemText(position, lang.lang.get(name))
            self.preset_combo.setCurrentIndex(current)
        finally:
            self._loading = False

        for card, title, content in (
            (self.theme_card, "Theme", "Light, dark, or match Windows"),
            (self.accent_card, "Accent colour", "Used for highlights and progress"),
            (self.mica_card, "Translucent background", "Mica effect, Windows 11 only"),
            (self.language_card, "Language", "Interface language"),
            (self.output_mode_card, "Where to save", "Destination for converted files"),
            (self.folder_card, "Custom folder", "Used when Custom folder is selected"),
            (self.overwrite_card, "If the file already exists",
             "How naming collisions are handled"),
            (self.delete_source_card, "Delete originals after converting",
             "Applies to files added from now on. This cannot be undone."),
            (self.parallel_card, "Files at once",
             "How many conversions run in parallel. Auto uses half your cores."),
            (self.threads_card, "Threads per file",
             "Passed to ffmpeg as -threads. Auto lets ffmpeg choose."),
            (self.preset_card, "Default quality preset", "Applied to files added from now on"),
            (self.logs_card, "Log files", "Useful when reporting a problem"),
        ):
            card.setTitle(lang.lang.get(title))
            card.setContent(lang.lang.get(content))

        self.browse_button.setText(lang.lang.get("Browse"))
        self.logs_button.setText(lang.lang.get("Open"))
        self.folder_edit.setPlaceholderText(lang.lang.get("Choose a folder"))
        for spin in (self.parallel_spin, self.threads_spin):
            spin.setSpecialValueText(lang.lang.get("Auto"))

