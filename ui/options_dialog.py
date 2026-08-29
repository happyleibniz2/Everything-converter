"""Per-file (or per-batch) encoding options.

Accepts and returns :class:`ConversionOptions` rather than a loose dict, so the
UI and the conversion layer cannot drift apart. When ``batch_count`` exceeds one,
the sheet presents itself as editing many files at once.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QStackedWidget, QWidget

from qfluentwidgets import (
    BodyLabel, CaptionLabel, CheckBox, ComboBox, LineEdit, MessageBoxBase,
    Pivot, Slider, SpinBox, SubtitleLabel, ToolTipFilter,
)

import lang
from converters.presets import (
    AUDIO_BITRATE_CHOICES, AUDIO_CODECS, AUDIO_SAMPLE_RATES,
    DEFAULT_AUDIO_CODEC, DEFAULT_VIDEO_CODEC, PRESETS, PRESET_DESCRIPTIONS,
    RESOLUTION_PRESETS, VIDEO_CODECS, category_for_extension,
)
from models.conversion_options import ConversionOptions
from utils.formatter import format_short_duration, format_size

# Re-exported so existing importers of these tables keep working.
__all__ = [
    "ConversionOptionsDialog", "VIDEO_CODECS", "AUDIO_CODECS",
    "DEFAULT_VIDEO_CODEC", "DEFAULT_AUDIO_CODEC", "PRESETS",
]

MODE_CRF = 0
MODE_BITRATE = 1

# CRF guidance shown live as the slider moves.
CRF_ADVICE = [
    (0, "Lossless, very large files"),
    (18, "Visually transparent"),
    (24, "Good quality, balanced size"),
    (30, "Noticeable loss, small files"),
    (52, "Heavy loss"),
]


def crf_advice(value: int) -> str:
    for threshold, text in CRF_ADVICE:
        if value <= threshold:
            return lang.lang.get(text)
    return ""


class ConversionOptionsDialog(MessageBoxBase):
    """Fluent options sheet: Quality / Video / Audio / Advanced."""

    def __init__(self, input_files, converter, parent=None,
                 initial_options=None, media_info=None, batch_count=1):
        super().__init__(parent)
        self.input_files = list(input_files or [])
        self.converter = converter
        self.batch_count = max(1, int(batch_count))
        self.media_info = media_info or {}

        if isinstance(initial_options, ConversionOptions):
            self.initial = initial_options.copy()
        else:
            self.initial = ConversionOptions.from_mapping(initial_options or {})

        self.target_extension = (converter.output_extension or "").lower()
        # The *output* category decides which controls apply: an "extract audio"
        # converter takes video in but must not offer video encoding options.
        category = category_for_extension(self.target_extension)
        self.has_video = category == "Video" and converter.category == "Video"
        self.has_audio = category in ("Video", "Audio")

        self._pages = {}
        self._build()
        self._load_initial()

        self.yesButton.setText(lang.lang.get("Apply"))
        self.cancelButton.setText(lang.lang.get("Cancel"))
        self.widget.setMinimumWidth(600)

    # ------------------------------------------------------------- building --
    def _build(self):
        self.viewLayout.setSpacing(10)

        self.title_label = SubtitleLabel(self._title_text(), self)
        self.viewLayout.addWidget(self.title_label)

        self.summary_label = CaptionLabel(self._summary_text(), self)
        self.summary_label.setWordWrap(True)
        self.viewLayout.addWidget(self.summary_label)

        self.pivot = Pivot(self)
        self.stack = QStackedWidget(self)
        self.stack.setMinimumHeight(250)
        self.viewLayout.addWidget(self.pivot)
        self.viewLayout.addWidget(self.stack)

        self._add_page("quality", lang.lang.get("Quality"), self._build_quality_page())
        if self.has_video:
            self._add_page("video", lang.lang.get("Video"), self._build_video_page())
        if self.has_audio:
            self._add_page("audio", lang.lang.get("Audio"), self._build_audio_page())
        self._add_page("advanced", lang.lang.get("Advanced"), self._build_advanced_page())

        self.pivot.setCurrentItem("quality")
        self.stack.setCurrentWidget(self._pages["quality"])

    def _add_page(self, key, title, widget):
        self._pages[key] = widget
        self.stack.addWidget(widget)
        self.pivot.addItem(
            routeKey=key, text=title,
            onClick=lambda checked=False, target=widget: self.stack.setCurrentWidget(target),
        )

    def _title_text(self):
        target = self.target_extension.upper().lstrip(".")
        if self.batch_count > 1:
            return (f"{lang.lang.get('Options for')} {self.batch_count} "
                    f"{lang.lang.get('files')} \u2192 {target}")
        return f"{lang.lang.get('Conversion options')} \u2192 {target}"

    def _summary_text(self):
        if self.batch_count > 1:
            return lang.lang.get(
                "These settings replace the options of every selected file in this category."
            )
        if not self.input_files:
            return ""
        path = Path(self.input_files[0])
        parts = [path.name]
        try:
            parts.append(format_size(path.stat().st_size))
        except OSError:
            pass
        if self.media_info.get("duration"):
            parts.append(format_short_duration(self.media_info["duration"]))
        if self.media_info.get("width") and self.media_info.get("height"):
            parts.append(f"{self.media_info['width']}\u00d7{self.media_info['height']}")
        return "  \u00b7  ".join(parts)
    # ---------------------------------------------------------------- pages --
    def _build_quality_page(self):
        page = QWidget(self)
        layout = QFormLayout(page)
        layout.setSpacing(9)

        self.preset_combo = ComboBox(page)
        for name in PRESETS:
            self.preset_combo.addItem(lang.lang.get(name), userData=name)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        layout.addRow(BodyLabel(lang.lang.get("Preset"), page), self.preset_combo)

        self.preset_hint = CaptionLabel("", page)
        self.preset_hint.setWordWrap(True)
        layout.addRow("", self.preset_hint)

        self.copy_mode_check = CheckBox(lang.lang.get("Remux only (no re-encoding)"), page)
        self.copy_mode_check.setToolTip(lang.lang.get(
            "Rewraps existing streams. Almost instant and lossless, but only "
            "works when the target container supports them."
        ))
        self.copy_mode_check.installEventFilter(ToolTipFilter(self.copy_mode_check))
        self.copy_mode_check.stateChanged.connect(self._on_copy_mode_changed)
        layout.addRow(self.copy_mode_check)

        trim_row = QHBoxLayout()
        self.start_time_edit = LineEdit(page)
        self.start_time_edit.setPlaceholderText("00:00:00")
        self.end_time_edit = LineEdit(page)
        self.end_time_edit.setPlaceholderText(lang.lang.get("end"))
        trim_row.addWidget(self.start_time_edit)
        trim_row.addWidget(BodyLabel("\u2192", page))
        trim_row.addWidget(self.end_time_edit)
        layout.addRow(BodyLabel(lang.lang.get("Trim"), page), trim_row)

        self.thread_spin = SpinBox(page)
        self.thread_spin.setRange(0, 64)
        self.thread_spin.setSpecialValueText(lang.lang.get("Auto"))
        self.thread_spin.setToolTip(lang.lang.get("Threads per file. Auto lets ffmpeg decide."))
        self.thread_spin.installEventFilter(ToolTipFilter(self.thread_spin))
        layout.addRow(BodyLabel(lang.lang.get("Threads"), page), self.thread_spin)

        self.delete_source_check = CheckBox(
            lang.lang.get("Delete the original after converting"), page
        )
        layout.addRow(self.delete_source_check)
        return page

    def _build_video_page(self):
        page = QWidget(self)
        layout = QFormLayout(page)
        layout.setSpacing(9)

        self.video_codec_combo = ComboBox(page)
        for key, label in VIDEO_CODECS.items():
            self.video_codec_combo.addItem(label, userData=key)
        layout.addRow(BodyLabel(lang.lang.get("Codec"), page), self.video_codec_combo)

        self.quality_mode_combo = ComboBox(page)
        self.quality_mode_combo.addItem(lang.lang.get("Constant quality (CRF)"), userData=MODE_CRF)
        self.quality_mode_combo.addItem(lang.lang.get("Target bitrate"), userData=MODE_BITRATE)
        self.quality_mode_combo.currentIndexChanged.connect(self._on_quality_mode_changed)
        layout.addRow(BodyLabel(lang.lang.get("Quality mode"), page), self.quality_mode_combo)

        crf_row = QHBoxLayout()
        self.crf_slider = Slider(Qt.Horizontal, page)
        self.crf_slider.setRange(0, 51)
        self.crf_slider.setValue(23)
        self.crf_value_label = BodyLabel("23", page)
        self.crf_value_label.setFixedWidth(24)
        self.crf_slider.valueChanged.connect(self._on_crf_changed)
        crf_row.addWidget(self.crf_slider)
        crf_row.addWidget(self.crf_value_label)
        layout.addRow(BodyLabel(lang.lang.get("CRF"), page), crf_row)

        self.crf_hint = CaptionLabel("", page)
        layout.addRow("", self.crf_hint)

        self.video_bitrate_spin = SpinBox(page)
        self.video_bitrate_spin.setRange(100, 100000)
        self.video_bitrate_spin.setValue(2500)
        self.video_bitrate_spin.setSuffix(" kbps")
        layout.addRow(BodyLabel(lang.lang.get("Bitrate"), page), self.video_bitrate_spin)

        self.resolution_combo = ComboBox(page)
        for label, width, height in RESOLUTION_PRESETS:
            self.resolution_combo.addItem(lang.lang.get(label), userData=(width, height))
        self.resolution_combo.addItem(lang.lang.get("Custom"), userData="custom")
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_changed)
        layout.addRow(BodyLabel(lang.lang.get("Resolution"), page), self.resolution_combo)

        size_row = QHBoxLayout()
        self.width_spin = SpinBox(page)
        self.width_spin.setRange(0, 7680)
        self.height_spin = SpinBox(page)
        self.height_spin.setRange(0, 4320)
        size_row.addWidget(self.width_spin)
        size_row.addWidget(BodyLabel("\u00d7", page))
        size_row.addWidget(self.height_spin)
        layout.addRow(BodyLabel(lang.lang.get("Custom size"), page), size_row)
        return page

    def _build_audio_page(self):
        page = QWidget(self)
        layout = QFormLayout(page)
        layout.setSpacing(9)

        self.copy_audio_check = CheckBox(lang.lang.get("Keep the original audio track"), page)
        self.copy_audio_check.stateChanged.connect(self._on_copy_audio_changed)
        layout.addRow(self.copy_audio_check)

        self.audio_codec_combo = ComboBox(page)
        for key, label in AUDIO_CODECS.items():
            self.audio_codec_combo.addItem(label, userData=key)
        layout.addRow(BodyLabel(lang.lang.get("Codec"), page), self.audio_codec_combo)

        self.audio_bitrate_combo = ComboBox(page)
        for value in AUDIO_BITRATE_CHOICES:
            self.audio_bitrate_combo.addItem(f"{value} kbps", userData=value)
        layout.addRow(BodyLabel(lang.lang.get("Bitrate"), page), self.audio_bitrate_combo)

        self.sample_rate_combo = ComboBox(page)
        self.sample_rate_combo.addItem(lang.lang.get("Same as source"), userData=None)
        for rate in AUDIO_SAMPLE_RATES:
            self.sample_rate_combo.addItem(f"{int(rate) / 1000:.1f} kHz", userData=int(rate))
        layout.addRow(BodyLabel(lang.lang.get("Sample rate"), page), self.sample_rate_combo)

        self.lossless_hint = CaptionLabel("", page)
        self.lossless_hint.setWordWrap(True)
        layout.addRow("", self.lossless_hint)
        return page

    def _build_advanced_page(self):
        page = QWidget(self)
        layout = QFormLayout(page)
        layout.setSpacing(9)

        self.extra_args_edit = LineEdit(page)
        self.extra_args_edit.setPlaceholderText("-tune film -movflags +faststart")
        layout.addRow(BodyLabel(lang.lang.get("Extra ffmpeg arguments"), page),
                      self.extra_args_edit)

        warning = CaptionLabel(lang.lang.get(
            "Passed to ffmpeg verbatim. Invalid arguments will make the conversion fail."
        ), page)
        warning.setWordWrap(True)
        layout.addRow("", warning)

        self.command_preview = CaptionLabel("", page)
        self.command_preview.setWordWrap(True)
        self.command_preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow(BodyLabel(lang.lang.get("Resulting arguments"), page),
                      self.command_preview)
        return page
    # -------------------------------------------------------------- reactions --
    def _on_preset_changed(self, _index):
        name = self.preset_combo.currentData() or "None"
        self.preset_hint.setText(lang.lang.get(PRESET_DESCRIPTIONS.get(name, "")))
        self._update_command_preview()

    def _on_copy_mode_changed(self, _state):
        """Remuxing bypasses every encoder setting, so grey them all out."""
        remux = self.copy_mode_check.isChecked()
        for page_key in ("video", "audio"):
            page = self._pages.get(page_key)
            if page is not None:
                page.setEnabled(not remux)
        self.preset_combo.setEnabled(not remux)
        self.preset_hint.setVisible(not remux)
        self._update_command_preview()

    def _on_copy_audio_changed(self, _state):
        copying = self.copy_audio_check.isChecked()
        for widget in (self.audio_codec_combo, self.audio_bitrate_combo,
                       self.sample_rate_combo):
            widget.setEnabled(not copying)
        self._update_command_preview()

    def _on_quality_mode_changed(self, _index):
        crf_mode = self.quality_mode_combo.currentData() == MODE_CRF
        self.crf_slider.setEnabled(crf_mode)
        self.crf_value_label.setEnabled(crf_mode)
        self.crf_hint.setVisible(crf_mode)
        self.video_bitrate_spin.setEnabled(not crf_mode)
        self._update_command_preview()

    def _on_crf_changed(self, value):
        self.crf_value_label.setText(str(value))
        self.crf_hint.setText(crf_advice(value))
        self._update_command_preview()

    def _on_resolution_changed(self, _index):
        data = self.resolution_combo.currentData()
        custom = data == "custom"
        self.width_spin.setEnabled(custom)
        self.height_spin.setEnabled(custom)
        if not custom and isinstance(data, tuple):
            width, height = data
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)
        self._update_command_preview()

    def _update_command_preview(self):
        """Show the arguments this configuration produces.

        Makes the effect of presets and overrides inspectable instead of opaque.
        """
        if not hasattr(self, "command_preview"):
            return
        try:
            args = self.get_options().build_extra_args()
        except Exception:
            self.command_preview.setText("")
            return
        self.command_preview.setText(" ".join(args) if args else lang.lang.get("None"))

    # ------------------------------------------------------------ load state --
    def _load_initial(self):
        options = self.initial

        index = self.preset_combo.findData(options.preset or "None")
        self.preset_combo.setCurrentIndex(max(0, index))
        self._on_preset_changed(0)

        self.copy_mode_check.setChecked(options.copy_mode)
        self.start_time_edit.setText(options.start_time or "")
        self.end_time_edit.setText(options.end_time or "")
        self.thread_spin.setValue(options.threads or 0)
        self.delete_source_check.setChecked(options.delete_source)

        if self.has_video:
            self._load_video(options)
        if self.has_audio:
            self._load_audio(options)

        self.extra_args_edit.setText(" ".join(options.extra_args or []))

        # Apply dependent enable/disable states after everything is populated.
        self._on_copy_mode_changed(0)
        self._update_command_preview()

    def _load_video(self, options):
        codec = options.video_codec or DEFAULT_VIDEO_CODEC.get(self.target_extension)
        if codec:
            index = self.video_codec_combo.findData(codec)
            if index >= 0:
                self.video_codec_combo.setCurrentIndex(index)

        if options.video_bitrate is not None:
            self.quality_mode_combo.setCurrentIndex(
                self.quality_mode_combo.findData(MODE_BITRATE)
            )
            self.video_bitrate_spin.setValue(int(options.video_bitrate))
        else:
            self.quality_mode_combo.setCurrentIndex(
                self.quality_mode_combo.findData(MODE_CRF)
            )
            self.crf_slider.setValue(int(options.crf) if options.crf is not None else 23)

        source_width = int(self.media_info.get("width") or 0)
        source_height = int(self.media_info.get("height") or 0)

        if options.scale:
            try:
                width, height = (int(part) for part in options.scale.split(":", 1))
                matched = self.resolution_combo.findData((width, height))
                if matched >= 0:
                    self.resolution_combo.setCurrentIndex(matched)
                else:
                    self.resolution_combo.setCurrentIndex(self.resolution_combo.count() - 1)
                self.width_spin.setValue(width)
                self.height_spin.setValue(height)
            except (TypeError, ValueError):
                self.resolution_combo.setCurrentIndex(0)
        else:
            self.resolution_combo.setCurrentIndex(0)
            # Seed the custom fields with the real dimensions so switching to
            # Custom starts from the source rather than zero.
            self.width_spin.setValue(source_width)
            self.height_spin.setValue(source_height)

        self._on_quality_mode_changed(0)
        self._on_crf_changed(self.crf_slider.value())
        self._on_resolution_changed(0)

    def _load_audio(self, options):
        self.copy_audio_check.setChecked(options.copy_audio)

        codec = options.audio_codec or DEFAULT_AUDIO_CODEC.get(self.target_extension)
        if codec:
            index = self.audio_codec_combo.findData(codec)
            if index >= 0:
                self.audio_codec_combo.setCurrentIndex(index)

        bitrate = options.audio_bitrate or 192
        index = self.audio_bitrate_combo.findData(int(bitrate))
        if index < 0:
            # Nearest supported choice, so an odd stored value still shows sensibly.
            nearest = min(AUDIO_BITRATE_CHOICES, key=lambda value: abs(value - int(bitrate)))
            index = self.audio_bitrate_combo.findData(nearest)
        self.audio_bitrate_combo.setCurrentIndex(max(0, index))

        if options.sample_rate:
            index = self.sample_rate_combo.findData(int(options.sample_rate))
            self.sample_rate_combo.setCurrentIndex(max(0, index))
        else:
            self.sample_rate_combo.setCurrentIndex(0)

        # Bitrate is meaningless for lossless codecs; say so rather than lie.
        lossless = self.target_extension in (".flac", ".wav")
        self.audio_bitrate_combo.setEnabled(not lossless)
        self.lossless_hint.setText(
            lang.lang.get("This format is lossless, so the bitrate setting is ignored.")
            if lossless else ""
        )
        self._on_copy_audio_changed(0)

    # ----------------------------------------------------------- read state --
    def get_options(self) -> ConversionOptions:
        options = ConversionOptions(
            preset=self.preset_combo.currentData() or "None",
            copy_mode=self.copy_mode_check.isChecked(),
            start_time=self.start_time_edit.text().strip() or None,
            end_time=self.end_time_edit.text().strip() or None,
            threads=self.thread_spin.value(),
            delete_source=self.delete_source_check.isChecked(),
            extra_args=self.extra_args_edit.text().split() if self.extra_args_edit.text().strip() else [],
        )

        if self.has_video and not options.copy_mode:
            options.video_codec = self.video_codec_combo.currentData()
            if self.quality_mode_combo.currentData() == MODE_CRF:
                options.crf = self.crf_slider.value()
            else:
                options.video_bitrate = self.video_bitrate_spin.value()

            data = self.resolution_combo.currentData()
            width = height = 0
            if data == "custom":
                width, height = self.width_spin.value(), self.height_spin.value()
            elif isinstance(data, tuple):
                width, height = data
            # 0x0 means "Original": emit no scale filter at all.
            options.scale = f"{width}:{height}" if width > 0 and height > 0 else None

        if self.has_audio and not options.copy_mode:
            options.copy_audio = self.copy_audio_check.isChecked()
            if not options.copy_audio:
                options.audio_codec = self.audio_codec_combo.currentData()
                if self.audio_bitrate_combo.isEnabled():
                    options.audio_bitrate = self.audio_bitrate_combo.currentData()
                options.sample_rate = self.sample_rate_combo.currentData()

        return options

