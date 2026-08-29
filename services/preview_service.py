"""Off-thread metadata probing and thumbnail generation.

Probing runs ffprobe and thumbnailing runs ffmpeg/Pillow; both are far too slow
to do on the GUI thread while a user is dropping dozens of files. This service
owns a small worker pool and emits results back to the UI as they arrive.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Qt
from PySide6.QtGui import QImage, QPixmap

from converters.presets import category_for_extension
from logger import logger
from utils.formatter import format_short_duration, format_size
from utils.media_info import get_media_info
from utils.paths import FFMPEG, TEMP

THUMBNAIL_SIZE = (64, 64)

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class _PreviewSignals(QObject):
    ready = Signal(int, dict, str, object)   # job_id, media_info, metadata_text, QImage|None
    failed = Signal(int, str)                # job_id, message


class _PreviewTask(QRunnable):
    """Probes one file and renders its thumbnail."""

    def __init__(self, job_id: int, file_path: str, signals: _PreviewSignals,
                 want_thumbnail: bool = True):
        super().__init__()
        self.job_id = job_id
        self.file_path = file_path
        self.signals = signals
        self.want_thumbnail = want_thumbnail
        self.setAutoDelete(True)

    def run(self):
        try:
            info = get_media_info(self.file_path) or {}
            text = describe_media(self.file_path, info)
            image = None
            if self.want_thumbnail:
                image = render_thumbnail(self.file_path)
            self.signals.ready.emit(self.job_id, info, text, image)
        except Exception as exc:  # never let a probe kill the pool
            logger.warning("Preview failed for %s: %s", self.file_path, exc)
            self.signals.failed.emit(self.job_id, str(exc))


class PreviewService(QObject):
    """Queues preview work and reports results per job id."""

    preview_ready = Signal(int, dict, str, object)
    preview_failed = Signal(int, str)

    def __init__(self, parent=None, max_threads: int = 4):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(1, max_threads))
        self._signals = _PreviewSignals()
        self._signals.ready.connect(self.preview_ready)
        self._signals.failed.connect(self.preview_failed)

    def request(self, job_id: int, file_path: str, want_thumbnail: bool = True) -> None:
        self._pool.start(_PreviewTask(job_id, file_path, self._signals, want_thumbnail))

    def shutdown(self, timeout_ms: int = 2000) -> None:
        self._pool.clear()
        self._pool.waitForDone(timeout_ms)


# ---------------------------------------------------------------- describe ----

def describe_media(file_path: str, info: Optional[Dict] = None) -> str:
    """Build the one-line technical summary shown in the queue."""
    info = info if info is not None else (get_media_info(file_path) or {})
    path = Path(file_path)
    category = category_for_extension(path.suffix)
    parts = []

    if info.get("width") and info.get("height"):
        parts.append(f"{info['width']}×{info['height']}")
    if info.get("video_codec"):
        parts.append(str(info["video_codec"]).upper())

    # ffprobe reports a nominal 25 fps and a frame "duration" for still images,
    # which is meaningless. Only report timing for genuinely time-based media.
    if category != "Image":
        fps = info.get("fps")
        if fps:
            try:
                parts.append(f"{float(fps):.0f} fps")
            except (TypeError, ValueError):
                pass
        if info.get("duration"):
            parts.append(format_short_duration(info["duration"]))

    if info.get("audio_codec"):
        parts.append(str(info["audio_codec"]).upper())
    if info.get("sample_rate"):
        parts.append(f"{info['sample_rate'] / 1000.0:.1f} kHz")
    if info.get("channels"):
        parts.append("Stereo" if int(info["channels"]) >= 2 else "Mono")

    if not parts:
        # Unprobeable files: fall back to Pillow, then to the raw extension.
        dimensions = _image_dimensions(file_path)
        if dimensions:
            parts.append(f"{dimensions[0]}×{dimensions[1]}")
        parts.append(path.suffix.upper().lstrip(".") or "FILE")

    try:
        size = path.stat().st_size
        if size:
            parts.append(format_size(size))
    except OSError:
        pass

    return " · ".join(parts) if parts else "—"


def _image_dimensions(file_path: str):
    if category_for_extension(Path(file_path).suffix) != "Image":
        return None
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size
    except Exception:
        return None


# --------------------------------------------------------------- thumbnail ----

def render_thumbnail(file_path: str) -> Optional[QImage]:
    """Return a small preview image, or ``None`` when one cannot be made."""
    path = Path(file_path)
    category = category_for_extension(path.suffix)
    try:
        if category == "Image":
            return _thumbnail_from_image(path)
        if category == "Video":
            return _thumbnail_from_video(path)
    except Exception as exc:
        logger.debug("Thumbnail failed for %s: %s", file_path, exc)
    return None


def _thumbnail_from_image(path: Path) -> Optional[QImage]:
    from PIL import Image, ImageOps

    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGBA")
        img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
        data = img.tobytes("raw", "RGBA")
        # QImage does not copy the buffer, so copy() before `data` is collected.
        image = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
        return image.copy()


def _thumbnail_from_video(path: Path) -> Optional[QImage]:
    if not FFMPEG.exists():
        return None

    info = get_media_info(str(path)) or {}
    duration = float(info.get("duration") or 0)
    # Seek a little way in; frame 0 is often black or a fade-in.
    seek = f"{min(duration * 0.1, 5.0):.2f}" if duration > 1 else "0"

    target = TEMP / f"thumb_{abs(hash(str(path)))}.png"
    command = [
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", seek, "-i", str(path),
        "-frames:v", "1",
        "-vf", f"scale={THUMBNAIL_SIZE[0]}:{THUMBNAIL_SIZE[1]}:force_original_aspect_ratio=decrease",
        str(target),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not target.exists():
            return None
        image = QImage(str(target))
        return image.copy() if not image.isNull() else None
    finally:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass


def placeholder_pixmap(category: str, size: int = 64) -> QPixmap:
    """Neutral square used until a real thumbnail arrives."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    return pixmap
