"""The conversion queue view.

Rows are bound to :class:`ConversionJob` objects by ``job_id`` (kept in
``ROLE_JOB_ID`` on column 0), never by row index, so removal and reordering
cannot desynchronise the view from the queue.

Status and progress are *painted* by a delegate instead of being hosted as child
widgets. A real ``ProgressBar`` per row would mean hundreds of live widgets for a
large batch; painting costs nothing for rows scrolled out of view.
"""

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QTableWidgetItem, QWidget
)

from qfluentwidgets import (
    ComboBox, FluentIcon, TableItemDelegate, TableWidget, TransparentToolButton,
    getFont, isDarkTheme, themeColor,
)

import lang
from converters.presets import category_for_extension
from models.conversion_job import JobStatus
from registry import find_converters

# Column layout.
COL_NAME = 0
COL_TARGET = 1
COL_DETAILS = 2
COL_ESTIMATE = 3
COL_STATUS = 4
COL_ACTIONS = 5
COLUMN_COUNT = 6

# Roles carrying job state to the delegate.
ROLE_JOB_ID = Qt.UserRole
ROLE_STATUS = Qt.UserRole + 1
ROLE_PROGRESS = Qt.UserRole + 2

ROW_HEIGHT = 50
THUMB = 34

# Status accent colours, tuned for the light theme and lightened for dark.
STATUS_COLORS = {
    JobStatus.READY: (0x70, 0x70, 0x70),
    JobStatus.QUEUED: (0x8A, 0x62, 0x00),
    JobStatus.RUNNING: (0x00, 0x60, 0xB0),
    JobStatus.DONE: (0x0C, 0x6B, 0x0C),
    JobStatus.FAILED: (0xB4, 0x24, 0x18),
    JobStatus.CANCELLED: (0x60, 0x60, 0x60),
    JobStatus.SKIPPED: (0x6B, 0x57, 0x00),
}

STATUS_LABELS = {
    JobStatus.READY: "Ready",
    JobStatus.QUEUED: "Queued",
    JobStatus.RUNNING: "Converting",
    JobStatus.DONE: "Done",
    JobStatus.FAILED: "Failed",
    JobStatus.CANCELLED: "Cancelled",
    JobStatus.SKIPPED: "Skipped",
}


def rounded_pixmap(image, size: int = THUMB) -> QPixmap:
    """Crop an image to a centred square with rounded corners."""
    source = QPixmap.fromImage(image) if not isinstance(image, QPixmap) else image
    if source.isNull():
        return source

    scaled = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    result = QPixmap(size, size)
    result.fill(Qt.transparent)

    painter = QPainter(result)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 5, 5)
    painter.setClipPath(path)
    painter.drawPixmap(
        (size - scaled.width()) // 2,
        (size - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return result


class QueueItemDelegate(TableItemDelegate):
    """Paints the status column as an inline progress bar or a coloured pill."""

    def paint(self, painter, option, index):
        if index.column() != COL_STATUS:
            super().paint(painter, option, index)
            return

        raw_status = index.data(ROLE_STATUS)
        if raw_status is None:
            super().paint(painter, option, index)
            return

        # Base class draws row background / hover / selection. The cell holds no
        # text, so nothing is drawn over what we paint next.
        super().paint(painter, option, index)

        painter.save()
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        painter.setClipRect(option.rect)

        status = JobStatus(raw_status)
        progress = int(index.data(ROLE_PROGRESS) or 0)
        rect = option.rect.adjusted(10, 0, -10, 0)

        if status is JobStatus.RUNNING:
            self._paint_progress(painter, rect, progress)
        else:
            self._paint_pill(painter, rect, status)

        painter.restore()

    def _paint_progress(self, painter, rect, progress):
        height = 5
        bar = QRectF(rect.x(), rect.center().y() - 3, rect.width(), height)

        track = QColor(255, 255, 255, 32) if isDarkTheme() else QColor(0, 0, 0, 28)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(bar, height / 2, height / 2)

        if progress > 0:
            filled = QRectF(bar)
            filled.setWidth(max(float(height), bar.width() * min(100, progress) / 100.0))
            painter.setBrush(themeColor())
            painter.drawRoundedRect(filled, height / 2, height / 2)

        painter.setFont(getFont(10))
        painter.setPen(QColor(255, 255, 255, 200) if isDarkTheme() else QColor(0, 0, 0, 165))
        painter.drawText(rect.adjusted(0, 8, 0, 0), Qt.AlignHCenter | Qt.AlignBottom, f"{progress}%")

    def _paint_pill(self, painter, rect, status):
        red, green, blue = STATUS_COLORS.get(status, (0x80, 0x80, 0x80))
        accent = QColor(red, green, blue)
        if isDarkTheme():
            accent = accent.lighter(165)

        text = lang.lang.get(STATUS_LABELS.get(status, status.value))
        painter.setFont(getFont(11))
        width = min(float(rect.width()), painter.fontMetrics().horizontalAdvance(text) + 24.0)
        height = 20.0
        pill = QRectF(rect.center().x() - width / 2, rect.center().y() - height / 2, width, height)

        background = QColor(accent)
        background.setAlpha(36)
        painter.setPen(Qt.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(pill, height / 2, height / 2)

        painter.setPen(accent)
        painter.drawText(pill, Qt.AlignCenter, text)


class QueueTable(TableWidget):
    """Renders and edits the job queue."""

    target_changed = Signal(int, object)      # job_id, converter
    options_requested = Signal(int)           # job_id
    remove_requested = Signal(int)            # job_id
    selection_toggled = Signal(int, bool)     # job_id, checked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress = False

        self.setColumnCount(COLUMN_COUNT)
        self.setBorderVisible(True)
        self.setBorderRadius(8)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setItemDelegate(QueueItemDelegate(self))

        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_TARGET, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_DETAILS, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_ESTIMATE, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_ACTIONS, QHeaderView.Fixed)
        header.setStretchLastSection(False)
        self.setColumnWidth(COL_TARGET, 108)
        self.setColumnWidth(COL_ESTIMATE, 150)
        self.setColumnWidth(COL_STATUS, 130)
        self.setColumnWidth(COL_ACTIONS, 72)
        # Details and estimate both elide; their tooltips carry the full text.
        self.setTextElideMode(Qt.ElideRight)

        self.retranslate()
        self.itemChanged.connect(self._on_item_changed)

    # ---------- header ----------
    def retranslate(self):
        self.setHorizontalHeaderLabels([
            lang.lang.get("File"),
            lang.lang.get("Convert to"),
            lang.lang.get("Details"),
            lang.lang.get("Estimated size"),
            lang.lang.get("Status"),
            lang.lang.get("Actions"),
        ])

    # ---------- row lifecycle ----------
    def append_job(self, job):
        row = self.rowCount()
        self.insertRow(row)
        self._populate_row(row, job)

    def rebuild(self, jobs):
        self._suppress = True
        try:
            self.setRowCount(0)
            for job in jobs:
                row = self.rowCount()
                self.insertRow(row)
                self._populate_row(row, job)
        finally:
            self._suppress = False

    def remove_job(self, job_id):
        row = self.row_for_job(job_id)
        if row >= 0:
            self.removeRow(row)

    def _populate_row(self, row, job):
        previous = self._suppress
        self._suppress = True
        try:
            name_item = QTableWidgetItem(job.filename)
            name_item.setData(ROLE_JOB_ID, job.job_id)
            name_item.setToolTip(job.input_path)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            name_item.setCheckState(Qt.Checked if job.selected else Qt.Unchecked)
            name_item.setIcon(self._fallback_icon(job))
            self.setItem(row, COL_NAME, name_item)

            self.setCellWidget(row, COL_TARGET, self._build_target_combo(job))

            details = QTableWidgetItem(job.metadata_text or lang.lang.get("Reading…"))
            details.setToolTip(job.metadata_text or "")
            self.setItem(row, COL_DETAILS, details)

            estimate = QTableWidgetItem(job.estimate_text or "—")
            estimate.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            estimate.setToolTip(job.estimate_tooltip or "")
            self.setItem(row, COL_ESTIMATE, estimate)

            status = QTableWidgetItem("")
            status.setData(ROLE_JOB_ID, job.job_id)
            status.setData(ROLE_STATUS, job.status.value)
            status.setData(ROLE_PROGRESS, job.progress)
            self.setItem(row, COL_STATUS, status)

            self.setCellWidget(row, COL_ACTIONS, self._build_actions(job))
        finally:
            self._suppress = previous

    def _build_target_combo(self, job):
        combo = ComboBox()
        combo.setMinimumWidth(92)
        converters = find_converters(job.input_path)
        if converters:
            for converter in converters:
                combo.addItem(converter.output_extension.upper().lstrip("."), userData=converter)
            if job.converter is not None:
                combo.setCurrentIndex(max(0, combo.findData(job.converter)))
        else:
            combo.addItem(lang.lang.get("Unsupported"), userData=None)
            combo.setEnabled(False)

        job_id = job.job_id
        combo.currentIndexChanged.connect(
            lambda _index, cb=combo, jid=job_id: self._emit_target_changed(jid, cb)
        )
        return combo

    def _emit_target_changed(self, job_id, combo):
        if not self._suppress:
            self.target_changed.emit(job_id, combo.currentData())

    def _build_actions(self, job):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(0)
        job_id = job.job_id

        options_button = TransparentToolButton(FluentIcon.SETTING, container)
        options_button.setFixedSize(28, 28)
        options_button.setToolTip(lang.lang.get("Conversion options"))
        options_button.clicked.connect(lambda _=False, jid=job_id: self.options_requested.emit(jid))

        remove_button = TransparentToolButton(FluentIcon.DELETE, container)
        remove_button.setFixedSize(28, 28)
        remove_button.setToolTip(lang.lang.get("Remove from queue"))
        remove_button.clicked.connect(lambda _=False, jid=job_id: self.remove_requested.emit(jid))

        layout.addWidget(options_button)
        layout.addWidget(remove_button)
        return container

    def _fallback_icon(self, job) -> QIcon:
        icon = {
            "Image": FluentIcon.PHOTO,
            "Video": FluentIcon.VIDEO,
            "Audio": FluentIcon.MUSIC,
        }.get(category_for_extension(job.source_extension), FluentIcon.DOCUMENT)
        return icon.icon()

    # ---------- lookup ----------
    def row_for_job(self, job_id) -> int:
        for row in range(self.rowCount()):
            item = self.item(row, COL_NAME)
            if item is not None and item.data(ROLE_JOB_ID) == job_id:
                return row
        return -1

    def job_id_at(self, row):
        item = self.item(row, COL_NAME)
        return item.data(ROLE_JOB_ID) if item is not None else None

    def selected_job_ids(self):
        ids = []
        for index in self.selectionModel().selectedRows():
            job_id = self.job_id_at(index.row())
            if job_id is not None:
                ids.append(job_id)
        return ids

    # ---------- targeted updates ----------
    def update_status(self, job):
        item = self._status_item(job.job_id)
        if item is None:
            return
        item.setData(ROLE_STATUS, job.status.value)
        item.setData(ROLE_PROGRESS, job.progress)
        item.setToolTip(job.error or "")
        self._repaint(item)

    def update_progress(self, job_id, percent):
        item = self._status_item(job_id)
        if item is None:
            return
        item.setData(ROLE_STATUS, JobStatus.RUNNING.value)
        item.setData(ROLE_PROGRESS, int(percent))
        self._repaint(item)

    def _status_item(self, job_id):
        row = self.row_for_job(job_id)
        return self.item(row, COL_STATUS) if row >= 0 else None

    def _repaint(self, item):
        # Repaint only the affected cell; a full viewport update during a
        # parallel batch would burn CPU on every progress tick.
        self.viewport().update(self.visualItemRect(item))

    def update_details(self, job):
        row = self.row_for_job(job.job_id)
        if row < 0:
            return
        previous = self._suppress
        self._suppress = True
        try:
            details = self.item(row, COL_DETAILS)
            if details is not None:
                details.setText(job.metadata_text or "—")
                details.setToolTip(job.metadata_text or "")

            estimate = self.item(row, COL_ESTIMATE)
            if estimate is not None:
                estimate.setText(job.estimate_text or "—")
                estimate.setToolTip(job.estimate_tooltip or "")

            if job.thumbnail is not None:
                name_item = self.item(row, COL_NAME)
                if name_item is not None:
                    name_item.setIcon(QIcon(rounded_pixmap(job.thumbnail)))
        finally:
            self._suppress = previous

    def update_estimate(self, job):
        row = self.row_for_job(job.job_id)
        if row < 0:
            return
        previous = self._suppress
        self._suppress = True
        try:
            estimate = self.item(row, COL_ESTIMATE)
            if estimate is not None:
                estimate.setText(job.estimate_text or "—")
                estimate.setToolTip(job.estimate_tooltip or "")
        finally:
            self._suppress = previous

    def sync_target(self, job):
        """Reflect a programmatic target change in the row's combo box."""
        row = self.row_for_job(job.job_id)
        if row < 0 or job.converter is None:
            return
        combo = self.cellWidget(row, COL_TARGET)
        if not isinstance(combo, ComboBox):
            return
        index = combo.findData(job.converter)
        if index >= 0 and index != combo.currentIndex():
            previous = self._suppress
            self._suppress = True
            try:
                combo.setCurrentIndex(index)
            finally:
                self._suppress = previous

    def sync_selection(self, job):
        row = self.row_for_job(job.job_id)
        if row < 0:
            return
        item = self.item(row, COL_NAME)
        if item is None:
            return
        desired = Qt.Checked if job.selected else Qt.Unchecked
        if item.checkState() == desired:
            return
        previous = self._suppress
        self._suppress = True
        try:
            item.setCheckState(desired)
        finally:
            self._suppress = previous

    # ---------- events ----------
    def _on_item_changed(self, item):
        if self._suppress or item.column() != COL_NAME:
            return
        job_id = item.data(ROLE_JOB_ID)
        if job_id is not None:
            self.selection_toggled.emit(job_id, item.checkState() == Qt.Checked)
