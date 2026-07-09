import os
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QSlider, QPushButton, QFormLayout, QGroupBox, QCheckBox,
    QFileDialog, QTabWidget, QLineEdit, QWidget, QMessageBox
)
from utils.paths import ICONS
from utils.media_info import get_media_info

# Codec mappings
VIDEO_CODECS = {
    "libx264": "H.264 (x264)",
    "libx265": "H.265 / HEVC",
    "libvpx": "VP8",
    "libvpx-vp9": "VP9",
    "mpeg4": "MPEG-4",
    "wmv2": "WMV2",
    "libxvid": "Xvid",
}
AUDIO_CODECS = {
    "aac": "AAC",
    "libmp3lame": "MP3",
    "flac": "FLAC",
    "pcm_s16le": "WAV (PCM)",
    "libvorbis": "Vorbis",
    "opus": "Opus",
}
DEFAULT_VIDEO_CODEC = {
    ".mp4": "libx264",
    ".mkv": "libx264",
    ".mov": "libx264",
    ".avi": "libx264",
    ".webm": "libvpx",
    ".flv": "libx264",
    ".3gp": "libx264",
    ".wmv": "wmv2",
}
DEFAULT_AUDIO_CODEC = {
    ".mp3": "libmp3lame",
    ".aac": "aac",
    ".flac": "flac",
    ".wav": "pcm_s16le",
    ".ogg": "libvorbis",
    ".m4a": "aac",
}

# Presets (same as main_window)
PRESETS = {
    "None": [],
    "Fast (web friendly)": ["-preset", "veryfast", "-crf", "28"],
    "High Quality (local)": ["-preset", "slow", "-crf", "18"],
    "Small Size (mobile)": ["-preset", "veryfast", "-crf", "32", "-vf", "scale=640:-2"],
    "Lossless (large)": ["-preset", "slow", "-crf", "0"],
}


class ConversionOptionsDialog(QDialog):
    def __init__(self, input_files, converter, parent=None):
        super().__init__(parent)
        self.input_files = input_files
        self.converter = converter
        self.media_info = get_media_info(input_files[0]) if input_files else {}
        self.setWindowTitle("Conversion Options")
        self.resize(720, 600)
        self.setModal(True)
        self._build_ui()
        self._populate_defaults()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # --- File info ---
        info_widget = QWidget()
        info_layout = QHBoxLayout(info_widget)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(64, 64)
        self._set_file_icon()
        info_layout.addWidget(self.icon_label)

        details_layout = QVBoxLayout()
        self.file_name_label = QLabel(Path(self.input_files[0]).name)
        self.file_name_label.setStyleSheet("font-weight: bold;")
        details_layout.addWidget(self.file_name_label)

        size = os.path.getsize(self.input_files[0])
        self.size_label = QLabel(f"Size: {self._format_size(size)}")
        details_layout.addWidget(self.size_label)

        if self.media_info:
            dur = self.media_info.get("duration", 0)
            if dur:
                self.duration_label = QLabel(f"Duration: {self._format_time(dur)}")
                details_layout.addWidget(self.duration_label)
            if "width" in self.media_info and "height" in self.media_info:
                self.res_label = QLabel(f"Resolution: {self.media_info['width']}x{self.media_info['height']}")
                details_layout.addWidget(self.res_label)
        info_layout.addLayout(details_layout)
        info_layout.addStretch()
        main_layout.addWidget(info_widget)

        # --- Tabs ---
        self.tabs = QTabWidget()

        # General tab (preset, copy, trim, threads, delete source, shutdown)
        general_tab = QWidget()
        general_layout = QFormLayout(general_tab)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESETS.keys()))
        general_layout.addRow("Preset", self.preset_combo)

        self.copy_mode_check = QCheckBox("Copy streams (no re-encode, remux only)")
        general_layout.addRow(self.copy_mode_check)

        self.copy_audio_check = QCheckBox("Copy audio (no re-encode)")
        general_layout.addRow(self.copy_audio_check)

        trim_layout = QHBoxLayout()
        self.start_time_edit = QLineEdit()
        self.start_time_edit.setPlaceholderText("Start (HH:MM:SS)")
        self.end_time_edit = QLineEdit()
        self.end_time_edit.setPlaceholderText("End (HH:MM:SS)")
        trim_layout.addWidget(QLabel("From:"))
        trim_layout.addWidget(self.start_time_edit)
        trim_layout.addWidget(QLabel("To:"))
        trim_layout.addWidget(self.end_time_edit)
        general_layout.addRow("Trim", trim_layout)

        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(0, 64)
        self.thread_spin.setSpecialValueText("Auto")
        general_layout.addRow("Threads", self.thread_spin)

        self.delete_source_check = QCheckBox("Delete source after conversion")
        general_layout.addRow(self.delete_source_check)

        self.shutdown_check = QCheckBox("Shutdown computer after conversion")
        general_layout.addRow(self.shutdown_check)

        self.tabs.addTab(general_tab, "General")

        # Video tab
        if self.converter.category == "Video":
            video_tab = QWidget()
            video_layout = QVBoxLayout(video_tab)

            # Video codec
            codec_layout = QHBoxLayout()
            codec_layout.addWidget(QLabel("Video Codec:"))
            self.video_codec_combo = QComboBox()
            self._populate_codec_combo(self.video_codec_combo, VIDEO_CODECS, self.converter.output_extension)
            codec_layout.addWidget(self.video_codec_combo)
            video_layout.addLayout(codec_layout)

            # Quality (CRF / Bitrate)
            quality_group = QGroupBox("Quality")
            quality_layout = QFormLayout(quality_group)
            self.quality_mode_combo = QComboBox()
            self.quality_mode_combo.addItems(["CRF (Constant Rate Factor)", "Bitrate (kbps)"])
            self.quality_mode_combo.currentIndexChanged.connect(self._on_quality_mode_changed)
            quality_layout.addRow("Mode:", self.quality_mode_combo)

            self.crf_slider = QSlider(Qt.Horizontal)
            self.crf_slider.setRange(0, 51)
            self.crf_slider.setValue(23)
            self.crf_slider.setTickInterval(5)
            self.crf_slider.setTickPosition(QSlider.TicksBelow)
            self.crf_label = QLabel("23")
            self.crf_slider.valueChanged.connect(lambda v: self.crf_label.setText(str(v)))
            crf_row = QHBoxLayout()
            crf_row.addWidget(self.crf_slider)
            crf_row.addWidget(self.crf_label)
            quality_layout.addRow("CRF value:", crf_row)

            self.bitrate_spin = QSpinBox()
            self.bitrate_spin.setRange(100, 50000)
            self.bitrate_spin.setValue(2000)
            self.bitrate_spin.setSuffix(" kbps")
            self.bitrate_spin.setEnabled(False)
            quality_layout.addRow("Bitrate:", self.bitrate_spin)
            video_layout.addWidget(quality_group)

            # Scaling
            scale_group = QGroupBox("Resolution")
            scale_layout = QFormLayout(scale_group)
            self.scale_preset_combo = QComboBox()
            self.scale_preset_combo.addItems(["Original", "720p (1280x720)", "1080p (1920x1080)", "480p (854x480)", "Custom"])
            self.scale_preset_combo.currentIndexChanged.connect(self._on_scale_preset_changed)
            scale_layout.addRow("Preset:", self.scale_preset_combo)

            self.scale_width = QSpinBox()
            self.scale_width.setRange(0, 7680)
            self.scale_width.setValue(0)
            self.scale_width.setEnabled(False)
            self.scale_height = QSpinBox()
            self.scale_height.setRange(0, 4320)
            self.scale_height.setValue(0)
            self.scale_height.setEnabled(False)
            wh_layout = QHBoxLayout()
            wh_layout.addWidget(QLabel("Width:"))
            wh_layout.addWidget(self.scale_width)
            wh_layout.addWidget(QLabel("Height:"))
            wh_layout.addWidget(self.scale_height)
            scale_layout.addRow("Custom size:", wh_layout)
            video_layout.addWidget(scale_group)

            self.tabs.addTab(video_tab, "Video")

        # Audio tab (if Video or Audio)
        if self.converter.category in ("Video", "Audio"):
            audio_tab = QWidget()
            audio_layout = QVBoxLayout(audio_tab)

            codec_layout = QHBoxLayout()
            codec_layout.addWidget(QLabel("Audio Codec:"))
            self.audio_codec_combo = QComboBox()
            self._populate_codec_combo(self.audio_codec_combo, AUDIO_CODECS, self.converter.output_extension)
            codec_layout.addWidget(self.audio_codec_combo)
            audio_layout.addLayout(codec_layout)

            bitrate_layout = QHBoxLayout()
            bitrate_layout.addWidget(QLabel("Bitrate (kbps):"))
            self.audio_bitrate_spin = QSpinBox()
            self.audio_bitrate_spin.setRange(32, 512)
            self.audio_bitrate_spin.setValue(128)
            self.audio_bitrate_spin.setSuffix(" kbps")
            bitrate_layout.addWidget(self.audio_bitrate_spin)
            audio_layout.addLayout(bitrate_layout)

            sr_layout = QHBoxLayout()
            sr_layout.addWidget(QLabel("Sample Rate (Hz):"))
            self.sample_rate_combo = QComboBox()
            self.sample_rate_combo.addItems(["44100", "48000", "96000", "192000"])
            sr_layout.addWidget(self.sample_rate_combo)
            audio_layout.addLayout(sr_layout)

            self.tabs.addTab(audio_tab, "Audio")

        # Advanced (extra args)
        extra_tab = QWidget()
        extra_layout = QVBoxLayout(extra_tab)
        self.extra_args_edit = QLineEdit()
        self.extra_args_edit.setPlaceholderText("e.g. -preset slow -tune film")
        extra_layout.addWidget(QLabel("Additional ffmpeg arguments:"))
        extra_layout.addWidget(self.extra_args_edit)
        self.tabs.addTab(extra_tab, "Advanced")

        main_layout.addWidget(self.tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.convert_btn)
        btn_layout.addWidget(self.cancel_btn)
        main_layout.addLayout(btn_layout)

    def _set_file_icon(self):
        ext = Path(self.input_files[0]).suffix.lower()
        icon_map = {
            ".mp4": "video.svg", ".mkv": "video.svg", ".mov": "video.svg", ".avi": "video.svg",
            ".mp3": "audio.svg", ".wav": "audio.svg", ".flac": "audio.svg", ".aac": "audio.svg",
            ".ogg": "audio.svg", ".m4a": "audio.svg",
            ".jpg": "image.svg", ".jpeg": "image.svg", ".png": "image.svg",
        }
        icon_name = icon_map.get(ext, "file.svg")
        icon_path = ICONS / icon_name
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                self.icon_label.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self.icon_label.setText("📄")

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _format_time(self, seconds):
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            m, s = divmod(seconds, 60)
            return f"{int(m):02d}:{int(s):02d}"
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

    def _populate_codec_combo(self, combo, codec_dict, output_ext):
        for key, display in codec_dict.items():
            combo.addItem(display, key)
        default_codec = None
        if self.converter.category == "Video":
            default_codec = DEFAULT_VIDEO_CODEC.get(output_ext)
        elif self.converter.category == "Audio":
            default_codec = DEFAULT_AUDIO_CODEC.get(output_ext)
        if default_codec:
            idx = combo.findData(default_codec)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _populate_defaults(self):
        # Load from media info if available
        if self.media_info:
            if "width" in self.media_info:
                self.scale_width.setValue(self.media_info["width"])
                self.scale_height.setValue(self.media_info["height"])

    def _on_quality_mode_changed(self, index):
        is_crf = (index == 0)
        self.crf_slider.setEnabled(is_crf)
        self.crf_label.setEnabled(is_crf)
        self.bitrate_spin.setEnabled(not is_crf)

    def _on_scale_preset_changed(self, index):
        presets = {
            1: (1280, 720),
            2: (1920, 1080),
            3: (854, 480),
        }
        if index in presets:
            w, h = presets[index]
            self.scale_width.setValue(w)
            self.scale_height.setValue(h)
            self.scale_width.setEnabled(False)
            self.scale_height.setEnabled(False)
        elif index == 4:
            self.scale_width.setEnabled(True)
            self.scale_height.setEnabled(True)
        else:
            self.scale_width.setValue(0)
            self.scale_height.setValue(0)
            self.scale_width.setEnabled(False)
            self.scale_height.setEnabled(False)

    def get_options(self):
        """Return a dict of all user choices."""
        opts = {}

        # General
        opts["preset"] = self.preset_combo.currentText()
        opts["copy_mode"] = self.copy_mode_check.isChecked()
        opts["copy_audio"] = self.copy_audio_check.isChecked()
        opts["start_time"] = self.start_time_edit.text().strip() or None
        opts["end_time"] = self.end_time_edit.text().strip() or None
        opts["threads"] = self.thread_spin.value()
        opts["delete_source"] = self.delete_source_check.isChecked()
        opts["shutdown"] = self.shutdown_check.isChecked()

        # Video
        if self.converter.category == "Video":
            opts["video_codec"] = self.video_codec_combo.currentData()
            mode = self.quality_mode_combo.currentIndex()
            if mode == 0:
                opts["crf"] = self.crf_slider.value()
            else:
                opts["video_bitrate"] = self.bitrate_spin.value()
            if self.scale_preset_combo.currentIndex() == 0:
                opts["scale"] = None
            else:
                w = self.scale_width.value()
                h = self.scale_height.value()
                opts["scale"] = f"{w}:{h}" if w > 0 and h > 0 else None

        # Audio
        if self.converter.category in ("Video", "Audio"):
            opts["audio_codec"] = self.audio_codec_combo.currentData()
            opts["audio_bitrate"] = self.audio_bitrate_spin.value()
            opts["sample_rate"] = int(self.sample_rate_combo.currentText())

        # Extra args
        extra = self.extra_args_edit.text().strip()
        if extra:
            opts["extra_args"] = extra.split()
        else:
            opts["extra_args"] = []

        return opts
