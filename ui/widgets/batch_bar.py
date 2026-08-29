"""Batch-wide controls for the queue.

This is the heart of the batch workflow: set one target format for every file,
apply one set of encoding options to every file, and act on the whole selection
at once. Previously all of this was per-row only, which made a 50-file batch
50 times the work.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, CheckBox, ComboBox, DropDownPushButton, FluentIcon, PushButton,
    RoundMenu, Action, SearchLineEdit, StrongBodyLabel, ToolTipFilter,
    TransparentPushButton,
)

import lang

# Sentinel meaning "leave each file's own target alone".
MIXED_TARGET = "__mixed__"


class BatchBar(QWidget):
    """Selection summary plus batch-wide actions."""

    select_all_toggled = Signal(bool)
    target_for_all_changed = Signal(str)      # extension, e.g. ".mp4"
    apply_options_to_all = Signal()
    clear_queue = Signal()
    remove_selected = Signal()
    clear_finished = Signal()
    retry_failed = Signal()
    add_files = Signal()
    add_folder = Signal()
    filter_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # --- row 1: selection + summary + add buttons ---
        first = QHBoxLayout()
        first.setSpacing(10)

        self.select_all_box = CheckBox(lang.lang.get("Select all"), self)
        self.select_all_box.setTristate(True)
        self.select_all_box.clicked.connect(self._on_select_all_clicked)
        first.addWidget(self.select_all_box)

        self.summary_label = BodyLabel("", self)
        self.summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        first.addWidget(self.summary_label, 1)

        self.filter_box = SearchLineEdit(self)
        self.filter_box.setPlaceholderText(lang.lang.get("Filter queue…"))
        self.filter_box.setFixedWidth(190)
        self.filter_box.textChanged.connect(self.filter_changed)
        first.addWidget(self.filter_box)

        self.add_button = DropDownPushButton(FluentIcon.ADD.icon(), lang.lang.get("Add"), self)
        add_menu = RoundMenu(parent=self.add_button)
        self.add_files_action = Action(FluentIcon.DOCUMENT, lang.lang.get("Add files…"))
        self.add_files_action.triggered.connect(self.add_files)
        self.add_folder_action = Action(FluentIcon.FOLDER, lang.lang.get("Add folder…"))
        self.add_folder_action.triggered.connect(self.add_folder)
        add_menu.addAction(self.add_files_action)
        add_menu.addAction(self.add_folder_action)
        self.add_button.setMenu(add_menu)
        first.addWidget(self.add_button)

        root.addLayout(first)

        # --- row 2: batch operations ---
        second = QHBoxLayout()
        second.setSpacing(8)

        self.convert_all_label = BodyLabel(lang.lang.get("Convert all to:"), self)
        second.addWidget(self.convert_all_label)

        self.target_combo = ComboBox(self)
        self.target_combo.setMinimumWidth(150)
        self.target_combo.setToolTip(
            lang.lang.get("Set one output format for every compatible file in the queue")
        )
        self.target_combo.installEventFilter(ToolTipFilter(self.target_combo))
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        second.addWidget(self.target_combo)

        self.apply_options_button = PushButton(
            FluentIcon.SETTING.icon(), lang.lang.get("Options for all…"), self
        )
        self.apply_options_button.setToolTip(
            lang.lang.get("Edit encoding options once and apply them to every selected file")
        )
        self.apply_options_button.installEventFilter(ToolTipFilter(self.apply_options_button))
        self.apply_options_button.clicked.connect(self.apply_options_to_all)
        second.addWidget(self.apply_options_button)

        second.addStretch(1)

        self.retry_button = TransparentPushButton(
            FluentIcon.SYNC.icon(), lang.lang.get("Retry failed"), self
        )
        self.retry_button.clicked.connect(self.retry_failed)
        self.retry_button.setVisible(False)
        second.addWidget(self.retry_button)

        self.clear_finished_button = TransparentPushButton(
            FluentIcon.COMPLETED.icon(), lang.lang.get("Clear finished"), self
        )
        self.clear_finished_button.clicked.connect(self.clear_finished)
        self.clear_finished_button.setVisible(False)
        second.addWidget(self.clear_finished_button)

        self.remove_selected_button = TransparentPushButton(
            FluentIcon.REMOVE.icon(), lang.lang.get("Remove selected"), self
        )
        self.remove_selected_button.clicked.connect(self.remove_selected)
        second.addWidget(self.remove_selected_button)

        self.clear_button = TransparentPushButton(
            FluentIcon.DELETE.icon(), lang.lang.get("Clear all"), self
        )
        self.clear_button.clicked.connect(self.clear_queue)
        second.addWidget(self.clear_button)

        root.addLayout(second)

    # ---------- target combo ----------
    def set_available_targets(self, extensions):
        """Populate the batch target list with formats the queue can produce."""
        self._suppress = True
        try:
            self.target_combo.clear()
            self.target_combo.addItem(lang.lang.get("Keep per-file choice"), userData=MIXED_TARGET)
            for extension in extensions:
                self.target_combo.addItem(extension.upper().lstrip("."), userData=extension)
            self.target_combo.setCurrentIndex(0)
            self.target_combo.setEnabled(bool(extensions))
        finally:
            self._suppress = False

    def reset_target_choice(self):
        """Return the combo to 'keep per-file choice' after a per-row edit."""
        if self.target_combo.count() and self.target_combo.currentIndex() != 0:
            self._suppress = True
            try:
                self.target_combo.setCurrentIndex(0)
            finally:
                self._suppress = False

    def _on_target_changed(self, _index):
        if self._suppress:
            return
        data = self.target_combo.currentData()
        if data and data != MIXED_TARGET:
            self.target_for_all_changed.emit(data)

    # ---------- selection ----------
    def _on_select_all_clicked(self):
        # Tristate boxes cycle through Partial on click; force a binary decision.
        checked = self.select_all_box.checkState() != Qt.Unchecked
        self.select_all_box.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.select_all_toggled.emit(checked)

    def set_selection_state(self, selected: int, total: int):
        self._suppress = True
        try:
            if total == 0 or selected == 0:
                state = Qt.Unchecked
            elif selected == total:
                state = Qt.Checked
            else:
                state = Qt.PartiallyChecked
            self.select_all_box.setCheckState(state)
        finally:
            self._suppress = False

    # ---------- summary ----------
    def set_summary(self, text: str):
        self.summary_label.setText(text)

    def set_action_visibility(self, has_failed: bool, has_finished: bool):
        self.retry_button.setVisible(has_failed)
        self.clear_finished_button.setVisible(has_finished)

    def set_enabled_during_run(self, idle: bool):
        """Disable mutating actions while a batch is in flight."""
        for widget in (
            self.target_combo, self.apply_options_button, self.clear_button,
            self.remove_selected_button, self.retry_button,
            self.clear_finished_button, self.select_all_box,
        ):
            widget.setEnabled(idle)

    # ---------- i18n ----------
    def retranslate(self):
        self.select_all_box.setText(lang.lang.get("Select all"))
        self.filter_box.setPlaceholderText(lang.lang.get("Filter queue…"))
        self.add_button.setText(lang.lang.get("Add"))
        self.add_files_action.setText(lang.lang.get("Add files…"))
        self.add_folder_action.setText(lang.lang.get("Add folder…"))
        self.convert_all_label.setText(lang.lang.get("Convert all to:"))
        self.apply_options_button.setText(lang.lang.get("Options for all…"))
        self.retry_button.setText(lang.lang.get("Retry failed"))
        self.clear_finished_button.setText(lang.lang.get("Clear finished"))
        self.remove_selected_button.setText(lang.lang.get("Remove selected"))
        self.clear_button.setText(lang.lang.get("Clear all"))
        if self.target_combo.count():
            self._suppress = True
            try:
                self.target_combo.setItemText(0, lang.lang.get("Keep per-file choice"))
            finally:
                self._suppress = False
