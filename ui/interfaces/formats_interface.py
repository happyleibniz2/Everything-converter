"""Browsable catalogue of supported conversions.

The old UI put a flat 116-item list of converters on the main screen, competing
for attention with the queue. Discovery belongs on its own page: search or filter
by category, see what each source format can become, and add files straight from
a result.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FlowLayout, FluentIcon, IconWidget, PillPushButton,
    ScrollArea, SearchLineEdit, SimpleCardWidget, StrongBodyLabel, SubtitleLabel,
)
from PySide6.QtWidgets import QHBoxLayout

import lang
from converters.extensions import EXTENSION_DESCRIPTIONS
from converters.presets import category_for_extension
from registry import CONVERTERS

CATEGORY_ICONS = {
    "Image": FluentIcon.PHOTO,
    "Video": FluentIcon.VIDEO,
    "Audio": FluentIcon.MUSIC,
}

CATEGORY_ORDER = ["All", "Image", "Video", "Audio"]


class FormatCard(SimpleCardWidget):
    """One source format and every target it can reach."""

    def __init__(self, extension, targets, category, parent=None):
        super().__init__(parent)
        self.extension = extension
        self.setFixedWidth(268)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        icon = IconWidget(CATEGORY_ICONS.get(category, FluentIcon.DOCUMENT), self)
        icon.setFixedSize(18, 18)
        header.addWidget(icon)
        header.addWidget(StrongBodyLabel(extension.upper().lstrip("."), self))
        header.addStretch(1)
        header.addWidget(CaptionLabel(f"{len(targets)} \u2192", self))
        layout.addLayout(header)

        description = EXTENSION_DESCRIPTIONS.get(extension.lower(), "")
        if description:
            summary = CaptionLabel(_shorten(description, 96), self)
            summary.setWordWrap(True)
            layout.addWidget(summary)

        targets_label = BodyLabel(
            ", ".join(sorted(target.upper().lstrip(".") for target in targets)), self
        )
        targets_label.setWordWrap(True)
        layout.addWidget(targets_label)


def _shorten(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


class FormatsInterface(ScrollArea):
    """Searchable grid of every supported source format."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("formatsInterface")
        self._category = "All"
        self._query = ""

        self._view = QWidget(self)
        self.setWidget(self._view)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea{background:transparent;border:none}")
        self._view.setStyleSheet("QWidget{background:transparent}")

        self._index = self._build_index()
        self._build()
        self._populate()

    # --------------------------------------------------------------- index --
    def _build_index(self):
        """Map each input extension to the set of outputs it can produce."""
        index = {}
        for converter in CONVERTERS:
            for extension in converter.input_extensions:
                entry = index.setdefault(
                    extension.lower(),
                    {"targets": set(), "category": category_for_extension(extension)},
                )
                entry["targets"].add(converter.output_extension.lower())
        return index

    # ----------------------------------------------------------------- ui --
    def _build(self):
        layout = QVBoxLayout(self._view)
        layout.setContentsMargins(26, 18, 26, 26)
        layout.setSpacing(12)

        self.heading = SubtitleLabel(lang.lang.get("Supported formats"), self._view)
        layout.addWidget(self.heading)

        self.subheading = CaptionLabel("", self._view)
        layout.addWidget(self.subheading)

        self.search_box = SearchLineEdit(self._view)
        self.search_box.setPlaceholderText(lang.lang.get("Search formats, e.g. mp4 or flac"))
        self.search_box.textChanged.connect(self._on_search)
        layout.addWidget(self.search_box)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_buttons = {}
        for name in CATEGORY_ORDER:
            button = PillPushButton(lang.lang.get(name), self._view)
            button.setCheckable(True)
            button.setChecked(name == "All")
            button.clicked.connect(lambda _checked=False, key=name: self._on_filter(key))
            self._filter_buttons[name] = button
            filter_row.addWidget(button)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.grid_host = QWidget(self._view)
        self.grid = FlowLayout(self.grid_host, needAni=False)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        layout.addWidget(self.grid_host)

        self.empty_label = BodyLabel(lang.lang.get("No formats match your search."), self._view)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)
        layout.addStretch(1)

    # ------------------------------------------------------------ populate --
    def _on_search(self, text):
        self._query = (text or "").strip().lower()
        self._populate()

    def _on_filter(self, category):
        self._category = category
        for name, button in self._filter_buttons.items():
            button.setChecked(name == category)
        self._populate()

    def _populate(self):
        self.grid.takeAllWidgets()

        shown = 0
        for extension in sorted(self._index):
            entry = self._index[extension]
            if self._category != "All" and entry["category"] != self._category:
                continue
            if self._query and not self._matches(extension, entry):
                continue
            self.grid.addWidget(
                FormatCard(extension, entry["targets"], entry["category"], self.grid_host)
            )
            shown += 1

        self.empty_label.setVisible(shown == 0)
        self.grid_host.setVisible(shown > 0)
        self.subheading.setText(
            f"{shown} {lang.lang.get('input formats')} \u00b7 "
            f"{len(CONVERTERS)} {lang.lang.get('conversions available')}"
        )

    def _matches(self, extension, entry):
        haystack = " ".join([
            extension,
            entry["category"],
            *entry["targets"],
        ]).lower()
        return self._query in haystack

    # ---------------------------------------------------------------- i18n --
    def retranslate(self):
        self.heading.setText(lang.lang.get("Supported formats"))
        self.search_box.setPlaceholderText(lang.lang.get("Search formats, e.g. mp4 or flac"))
        self.empty_label.setText(lang.lang.get("No formats match your search."))
        for name, button in self._filter_buttons.items():
            button.setText(lang.lang.get(name))
        self._populate()
