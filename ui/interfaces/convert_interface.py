"""The main working surface: drop zone, queue, batch controls, progress dock.

Owns the queue and the conversion coordinator and mediates between them. The
window shell only hosts this widget; all batch behaviour lives here.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
)

from qfluentwidgets import (
    Action, CaptionLabel, FluentIcon, InfoBar, InfoBarPosition, MessageBox,
    PrimaryPushButton, RoundMenu, SubtitleLabel, TransparentPushButton,
)

import lang
from controllers.queue_controller import QueueController
from logger import logger
from models.conversion_job import JobStatus
from models.conversion_options import ConversionOptions
from registry import find_converters
from services.batch_planner import plan_batch, recommended_concurrency
from services.output_planner import OutputPolicy, preview_output_path
from services.preview_service import PreviewService
from services.size_estimator import estimate_output_size
from ui.widgets.batch_bar import BatchBar
from ui.widgets.drop_area import DropArea
from ui.widgets.empty_state import EmptyState
from ui.widgets.progress_dock import ProgressDock
from ui.widgets.queue_table import QueueTable
from utils.formatter import format_size
from workers.conversion_worker import ConversionCoordinator

# Above this size, probe metadata but skip thumbnailing to keep the pool free.
THUMBNAIL_SIZE_LIMIT = 2 * 1024 * 1024 * 1024

# Folder scans stop here; deep trees can hold tens of thousands of files.
FOLDER_SCAN_LIMIT = 5000


class ConvertInterface(QWidget):
    """Queue-centric conversion workflow."""

    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("convertInterface")

        self.settings = QSettings("EverythingConverter", "Settings")
        self.queue = QueueController(self)
        self.previews = PreviewService(self, max_threads=3)
        self.coordinator = ConversionCoordinator(self)

        self._output_files: List[str] = []
        self._active: Dict[int, str] = {}
        self._session_folder: Optional[str] = None
        self._filter_text = ""

        self._build_ui()
        self._connect_signals()
        self._refresh_all()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 18, 26, 18)
        root.setSpacing(12)

        self.heading = SubtitleLabel(lang.lang.get("Convert"), self)
        root.addWidget(self.heading)

        self.drop_area = DropArea(self)
        root.addWidget(self.drop_area)

        self.batch_bar = BatchBar(self)
        root.addWidget(self.batch_bar)

        self.empty_state = EmptyState(self)
        root.addWidget(self.empty_state, 1)

        self.table = QueueTable(self)
        root.addWidget(self.table, 1)

        self.progress_dock = ProgressDock(self)
        self.progress_dock.setVisible(False)
        root.addWidget(self.progress_dock)

        footer = QHBoxLayout()
        footer.setSpacing(12)

        info_column = QVBoxLayout()
        info_column.setSpacing(1)
        self.destination_label = CaptionLabel("", self)
        self.savings_label = CaptionLabel("", self)
        info_column.addWidget(self.destination_label)
        info_column.addWidget(self.savings_label)
        footer.addLayout(info_column, 1)

        self.open_folder_button = TransparentPushButton(
            FluentIcon.FOLDER.icon(), lang.lang.get("Open output folder"), self
        )
        self.open_folder_button.clicked.connect(self._open_output_folder)
        self.open_folder_button.setVisible(False)
        footer.addWidget(self.open_folder_button)

        self.convert_button = PrimaryPushButton(
            FluentIcon.PLAY_SOLID.icon(), lang.lang.get("Convert"), self
        )
        self.convert_button.setMinimumHeight(36)
        self.convert_button.setMinimumWidth(150)
        self.convert_button.clicked.connect(self.start_conversion)
        footer.addWidget(self.convert_button)

        root.addLayout(footer)

    def _connect_signals(self):
        self.drop_area.files_dropped.connect(self.add_paths)
        self.drop_area.browse_requested.connect(self.browse_files)

        self.empty_state.browse_requested.connect(self.browse_files)
        self.empty_state.folder_requested.connect(self.browse_folder)

        bar = self.batch_bar
        bar.add_files.connect(self.browse_files)
        bar.add_folder.connect(self.browse_folder)
        bar.select_all_toggled.connect(self._on_select_all)
        bar.target_for_all_changed.connect(self.apply_target_to_all)
        bar.apply_options_to_all.connect(self.edit_options_for_all)
        bar.clear_queue.connect(self.clear_queue)
        bar.remove_selected.connect(self._remove_selected_rows)
        bar.clear_finished.connect(self._clear_finished)
        bar.retry_failed.connect(self.retry_failed)
        bar.filter_changed.connect(self._apply_filter)

        self.table.target_changed.connect(self._on_target_changed)
        self.table.options_requested.connect(self.edit_options_for_job)
        self.table.remove_requested.connect(self._remove_job)
        self.table.selection_toggled.connect(self._on_selection_toggled)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._update_destination_preview)

        self.previews.preview_ready.connect(self._on_preview_ready)

        self.progress_dock.pause_toggled.connect(self._on_pause_toggled)
        self.progress_dock.cancel_requested.connect(self._on_cancel_requested)
        self.progress_dock.dismiss_requested.connect(self._hide_progress_dock)

        pipeline = self.coordinator
        pipeline.job_started.connect(self._on_job_started)
        pipeline.job_progress.connect(self._on_job_progress)
        pipeline.job_succeeded.connect(self._on_job_succeeded)
        pipeline.job_failed.connect(self._on_job_failed)
        pipeline.job_cancelled.connect(self._on_job_cancelled)
        pipeline.batch_progress.connect(self.progress_dock.set_progress)
        pipeline.batch_counts.connect(self.progress_dock.set_counts)
        pipeline.batch_stats.connect(self.progress_dock.set_stats)
        pipeline.batch_finished.connect(self._on_batch_finished)

    # -------------------------------------------------------- adding files --
    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, lang.lang.get("Select files to convert"), "", self._dialog_filter()
        )
        if files:
            self.add_paths(files)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, lang.lang.get("Select a folder"))
        if folder:
            self.add_paths([folder])

    def _dialog_filter(self) -> str:
        from converters.presets import CATEGORY_EXTENSIONS

        groups, every = [], []
        for category, extensions in CATEGORY_EXTENSIONS.items():
            patterns = " ".join(f"*{extension}" for extension in extensions)
            every.append(patterns)
            groups.append(f"{lang.lang.get(category)} ({patterns})")
        groups.insert(0, f"{lang.lang.get('All supported')} ({' '.join(every)})")
        groups.append(f"{lang.lang.get('All files')} (*)")
        return ";;".join(groups)

    def add_paths(self, paths):
        """Add files, expanding any dropped folders."""
        expanded = []
        for path in paths:
            if os.path.isdir(path):
                expanded.extend(self._scan_folder(path))
            else:
                expanded.append(path)

        if not expanded:
            self._notify(lang.lang.get("Nothing to add"),
                         lang.lang.get("No convertible files were found."), "warning")
            return

        added, duplicates, _rejected = self.queue.add_files(
            expanded, default_options=self._default_options
        )

        for job in added:
            self.table.append_job(job)
            self.previews.request(job.job_id, job.input_path,
                                  job.source_size <= THUMBNAIL_SIZE_LIMIT)

        self._refresh_all()
        self._announce_additions(added, duplicates)

    def _announce_additions(self, added, duplicates):
        if not added:
            if duplicates:
                self._notify(lang.lang.get("Already in queue"),
                             f"{duplicates} {lang.lang.get('file(s) were already queued.')}",
                             "warning")
            return

        unsupported = sum(1 for job in added if not job.has_converter)
        details = []
        if duplicates:
            details.append(f"{duplicates} {lang.lang.get('already queued')}")
        if unsupported:
            details.append(f"{unsupported} {lang.lang.get('unsupported')}")
        self._notify(f"{len(added)} {lang.lang.get('file(s) added')}",
                     " · ".join(details), "warning" if unsupported else "success")

    def _scan_folder(self, folder: str) -> List[str]:
        found = []
        try:
            for root, _dirs, files in os.walk(folder):
                for name in files:
                    full = os.path.join(root, name)
                    if find_converters(full):
                        found.append(full)
                if len(found) >= FOLDER_SCAN_LIMIT:
                    logger.warning("Folder scan truncated at %d files: %s",
                                   FOLDER_SCAN_LIMIT, folder)
                    return found
        except OSError as exc:
            logger.warning("Could not scan %s: %s", folder, exc)
        return found

    def _default_options(self, _job) -> ConversionOptions:
        return ConversionOptions(
            preset=self.settings.value("default_preset", "None", type=str) or "None",
            threads=self.settings.value("threads", 0, type=int),
            delete_source=self.settings.value("delete_source", False, type=bool),
        )

    def _on_preview_ready(self, job_id, info, text, image):
        job = self.queue.job(job_id)
        if job is None:
            return
        job.media_info = info or {}
        job.metadata_text = text
        job.thumbnail = image
        self._recalculate_estimate(job)
        self.table.update_details(job)
        self._update_summary()

    # ---------------------------------------------------------- queue edits --
    def _on_target_changed(self, job_id, converter):
        job = self.queue.job(job_id)
        if job is None:
            return
        self._retarget(job, converter)
        self.batch_bar.reset_target_choice()
        self._update_destination_preview()
        self._update_summary()

    def _retarget(self, job, converter):
        """Point a job at a new output format and invalidate stale codec picks."""
        job.converter = converter
        # Codecs were resolved for the old container; let defaults re-derive.
        job.options.video_codec = None
        job.options.audio_codec = None
        if job.status.is_terminal:
            job.mark_ready()
            self.table.update_status(job)
        self._recalculate_estimate(job)
        self.table.update_estimate(job)

    def apply_target_to_all(self, extension: str):
        """Retarget every selected file that can produce ``extension``."""
        changed = skipped = 0
        for job in self.queue.selected_jobs():
            candidates = [
                converter for converter in find_converters(job.input_path)
                if converter.output_extension.lower() == extension.lower()
            ]
            if not candidates:
                skipped += 1
                continue
            self._retarget(job, candidates[0])
            self.table.sync_target(job)
            changed += 1

        self._update_summary()
        self._update_destination_preview()

        label = extension.upper().lstrip(".")
        if changed and skipped:
            self._notify(f"{changed} {lang.lang.get('files set to')} {label}",
                         f"{skipped} {lang.lang.get('cannot convert to this format')}",
                         "warning")
        elif changed:
            self._notify(f"{changed} {lang.lang.get('files set to')} {label}", "", "success")
        else:
            self._notify(lang.lang.get("No files changed"),
                         lang.lang.get("None of the selected files can convert to this format."),
                         "warning")

    def _on_selection_toggled(self, job_id, checked):
        job = self.queue.job(job_id)
        if job is not None:
            job.selected = checked
            self._update_summary()

    def _on_select_all(self, checked):
        self.queue.set_all_selected(checked)
        for job in self.queue:
            self.table.sync_selection(job)
        self._update_summary()

    def _remove_job(self, job_id):
        # While a batch runs, the remove button cancels that file instead.
        if self.coordinator.is_running:
            job = self.queue.job(job_id)
            if job is not None and job.status.is_active:
                self.coordinator.cancel_job(job_id)
                return
        self.queue.remove(job_id)
        self.table.remove_job(job_id)
        self._refresh_all()

    def _remove_selected_rows(self):
        job_ids = self.table.selected_job_ids() or [
            job.job_id for job in self.queue.selected_jobs()
        ]
        if not job_ids:
            self._notify(lang.lang.get("Nothing selected"),
                         lang.lang.get("Select rows to remove first."), "warning")
            return
        for job_id in job_ids:
            self.queue.remove(job_id)
            self.table.remove_job(job_id)
        self._refresh_all()

    def _clear_finished(self):
        for job_id in [job.job_id for job in self.queue
                       if job.status in (JobStatus.DONE, JobStatus.SKIPPED)]:
            self.queue.remove(job_id)
            self.table.remove_job(job_id)
        self._refresh_all()

    def clear_queue(self):
        if not len(self.queue):
            return
        box = MessageBox(
            lang.lang.get("Clear the queue?"),
            lang.lang.get("Files are removed from the list only. Nothing on disk is deleted."),
            self.window(),
        )
        box.yesButton.setText(lang.lang.get("Clear"))
        box.cancelButton.setText(lang.lang.get("Keep"))
        if box.exec():
            self.queue.clear()
            self.table.setRowCount(0)
            self._output_files.clear()
            self._refresh_all()

    def _apply_filter(self, text):
        self._filter_text = (text or "").strip().lower()
        for row in range(self.table.rowCount()):
            job_id = self.table.job_id_at(row)
            job = self.queue.job(job_id) if job_id is not None else None
            visible = True
            if job is not None and self._filter_text:
                haystack = f"{job.filename} {job.target_extension} {job.metadata_text}".lower()
                visible = self._filter_text in haystack
            self.table.setRowHidden(row, not visible)
    # -------------------------------------------------------------- options --
    def edit_options_for_job(self, job_id):
        job = self.queue.job(job_id)
        if job is None:
            return
        if not job.has_converter:
            self._notify(lang.lang.get("No converter"),
                         lang.lang.get("This file type is not supported yet."), "warning")
            return

        from ui.options_dialog import ConversionOptionsDialog

        dialog = ConversionOptionsDialog(
            [job.input_path], job.converter, self.window(),
            initial_options=job.options, media_info=job.media_info,
        )
        if dialog.exec() == QDialog.Accepted:
            job.options = dialog.get_options()
            self._recalculate_estimate(job)
            self.table.update_estimate(job)
            self._update_summary()

    def edit_options_for_all(self):
        """Edit one options set and apply it to every compatible selected job.

        Options are only meaningful per output category (you cannot give a PNG a
        CRF value), so the dialog is opened for the most common category in the
        selection and applied only to jobs sharing it.
        """
        jobs = [job for job in self.queue.selected_jobs() if job.has_converter]
        if not jobs:
            self._notify(lang.lang.get("Nothing selected"),
                         lang.lang.get("Select at least one supported file."), "warning")
            return

        categories: Dict[str, list] = {}
        for job in jobs:
            categories.setdefault(job.converter.category, []).append(job)
        category = max(categories, key=lambda key: len(categories[key]))
        group = categories[category]
        others = len(jobs) - len(group)

        from ui.options_dialog import ConversionOptionsDialog

        template = group[0]
        dialog = ConversionOptionsDialog(
            [job.input_path for job in group], template.converter, self.window(),
            initial_options=template.options, media_info=template.media_info,
            batch_count=len(group),
        )
        if dialog.exec() != QDialog.Accepted:
            return

        options = dialog.get_options()
        for job in group:
            # Each job keeps its own object so later per-file edits stay isolated.
            job.options = options.copy()
            self._recalculate_estimate(job)
            self.table.update_estimate(job)

        self._update_summary()
        detail = (f"{others} {lang.lang.get('files in other categories were left unchanged')}"
                  if others else "")
        self._notify(f"{lang.lang.get('Options applied to')} {len(group)} {lang.lang.get('files')}",
                     detail, "warning" if others else "success")

    # ----------------------------------------------------------- conversion --
    def start_conversion(self, only_jobs=None):
        if self.coordinator.is_running:
            self._notify(lang.lang.get("Already converting"),
                         lang.lang.get("Wait for the current batch to finish."), "warning")
            return

        candidates = only_jobs if only_jobs else self.queue.convertible_jobs(only_selected=True)
        if not candidates:
            self._notify(lang.lang.get("Nothing to convert"),
                         lang.lang.get("Tick at least one supported file first."), "warning")
            return

        policy = self._resolve_output_policy()
        if policy is None:
            return

        plan = plan_batch(
            candidates, policy,
            default_preset=self.settings.value("default_preset", "None", type=str) or "None",
            default_threads=self.settings.value("threads", 0, type=int),
        )

        for job in plan.skipped:
            self.table.update_status(job)

        if plan.is_empty:
            message = (lang.lang.get("Every output file already exists and was skipped.")
                       if plan.skipped else lang.lang.get("No file has a target format."))
            self._notify(lang.lang.get("Nothing to convert"), message, "warning")
            return

        self._output_files = [job.output_path for job in plan.runnable]
        self._active.clear()

        for job in plan.runnable:
            self.table.update_status(job)

        concurrency = recommended_concurrency(self.settings, len(plan.runnable))
        logger.info("Starting batch: %d file(s), concurrency %d",
                    len(plan.runnable), concurrency)
        for job in plan.runnable:
            logger.info("  %s -> %s (%s)", job.input_path, job.output_path, job.converter.name)

        self.progress_dock.reset()
        self.progress_dock.setVisible(True)
        self._set_busy(True)
        self.coordinator.start(plan.runnable, concurrency=concurrency)

    def _resolve_output_policy(self) -> Optional[OutputPolicy]:
        """Build the output policy, prompting for a folder when required."""
        policy = OutputPolicy.from_settings(self.settings, self._session_folder)
        if not policy.needs_destination_prompt:
            return policy

        folder = QFileDialog.getExistingDirectory(
            self, lang.lang.get("Choose where to save converted files")
        )
        if not folder:
            return None
        self._session_folder = folder
        return OutputPolicy.from_settings(self.settings, folder)

    def _on_job_started(self, job_id):
        job = self.queue.job(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.progress = 0
        self._active[job_id] = job.filename
        self.table.update_status(job)
        self.progress_dock.set_active_files(list(self._active.values()))

    def _on_job_progress(self, job_id, percent):
        job = self.queue.job(job_id)
        if job is None:
            return
        job.progress = percent
        self.table.update_progress(job_id, percent)

    def _on_job_succeeded(self, job_id, output_path):
        job = self.queue.job(job_id)
        if job is None:
            return
        job.status = JobStatus.DONE
        job.progress = 100
        job.output_path = output_path
        job.error = ""
        self._finish_job(job)

    def _on_job_failed(self, job_id, message):
        job = self.queue.job(job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = message
        self._finish_job(job)

    def _on_job_cancelled(self, job_id):
        job = self.queue.job(job_id)
        if job is None:
            return
        job.status = JobStatus.CANCELLED
        self._finish_job(job)

    def _finish_job(self, job):
        self._active.pop(job.job_id, None)
        self.table.update_status(job)
        self.progress_dock.set_active_files(list(self._active.values()))

    def _on_batch_finished(self, succeeded, failed, cancelled):
        self._set_busy(False)
        self.progress_dock.finish(succeeded, failed, cancelled)
        self.open_folder_button.setVisible(bool(succeeded))
        self._refresh_all()

        if failed:
            self._show_errors(succeeded, failed)
        elif cancelled and not succeeded:
            self._notify(lang.lang.get("Cancelled"),
                         lang.lang.get("No files were converted."), "warning")
        else:
            self._notify(lang.lang.get("Conversion complete"),
                         f"{succeeded} {lang.lang.get('file(s) converted successfully.')}",
                         "success")

    def _show_errors(self, succeeded, failed):
        """Surface failures through the diagnostic assistant, not a raw dump."""
        from ui.error_assistant import ErrorAssistant

        failures = [(job.filename, job.error) for job in self.queue.failed_jobs()]
        bar = InfoBar.error(
            title=f"{failed} {lang.lang.get('conversion(s) failed')}",
            content=f"{succeeded} {lang.lang.get('succeeded')}. "
                    f"{lang.lang.get('Select Details for suggested fixes.')}",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=-1, parent=self.window(),
        )
        button = TransparentPushButton(lang.lang.get("Details"), bar)
        button.clicked.connect(lambda: ErrorAssistant(failures, self.window()).exec())
        bar.addWidget(button)

    def _on_pause_toggled(self, paused):
        if paused:
            self.coordinator.pause()
        else:
            self.coordinator.resume()

    def _on_cancel_requested(self):
        box = MessageBox(
            lang.lang.get("Stop converting?"),
            lang.lang.get("Files already finished are kept. The current ones are discarded."),
            self.window(),
        )
        box.yesButton.setText(lang.lang.get("Stop"))
        box.cancelButton.setText(lang.lang.get("Keep going"))
        if box.exec():
            self.coordinator.cancel()

    def _hide_progress_dock(self):
        self.progress_dock.setVisible(False)

    def retry_failed(self):
        failed = self.queue.failed_jobs()
        if not failed:
            return
        for job in failed:
            job.mark_ready()
            job.selected = True
            self.table.update_status(job)
            self.table.sync_selection(job)
        self._refresh_all()
        self.start_conversion(only_jobs=failed)
    # -------------------------------------------------------------- context --
    def _show_context_menu(self, position):
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        job_id = self.table.job_id_at(row)
        job = self.queue.job(job_id) if job_id is not None else None
        if job is None:
            return

        menu = RoundMenu(parent=self.table)

        options_action = Action(FluentIcon.SETTING, lang.lang.get("Conversion options"))
        options_action.triggered.connect(lambda: self.edit_options_for_job(job_id))
        menu.addAction(options_action)

        if job.status is JobStatus.DONE and job.output_path:
            open_action = Action(FluentIcon.PLAY, lang.lang.get("Open converted file"))
            open_action.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(job.output_path))
            )
            menu.addAction(open_action)

        reveal_action = Action(FluentIcon.FOLDER, lang.lang.get("Show in folder"))
        reveal_action.triggered.connect(lambda: self._reveal(job))
        menu.addAction(reveal_action)

        copy_action = Action(FluentIcon.COPY, lang.lang.get("Copy source path"))
        copy_action.triggered.connect(
            lambda: QApplication.clipboard().setText(job.input_path)
        )
        menu.addAction(copy_action)

        if job.status is JobStatus.FAILED:
            menu.addSeparator()
            retry_action = Action(FluentIcon.SYNC, lang.lang.get("Retry this file"))
            retry_action.triggered.connect(lambda: self._retry_single(job))
            menu.addAction(retry_action)

        menu.addSeparator()
        remove_action = Action(FluentIcon.DELETE, lang.lang.get("Remove from queue"))
        remove_action.triggered.connect(lambda: self._remove_job(job_id))
        menu.addAction(remove_action)

        menu.exec(self.table.viewport().mapToGlobal(position))

    def _retry_single(self, job):
        job.mark_ready()
        job.selected = True
        self.table.update_status(job)
        self.table.sync_selection(job)
        self.start_conversion(only_jobs=[job])

    def _reveal(self, job):
        target = Path(job.output_path) if job.output_path and Path(job.output_path).exists() \
            else Path(job.input_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))

    def _open_output_folder(self):
        existing = [path for path in self._output_files if Path(path).exists()]
        if not existing:
            self._notify(lang.lang.get("Nothing to show"),
                         lang.lang.get("No converted files were found."), "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(existing[0]).parent)))

    # ---------------------------------------------------------- refreshing --
    def _recalculate_estimate(self, job):
        if not job.has_converter:
            job.estimate_text = lang.lang.get("Unsupported")
            job.estimate_tooltip = ""
            return
        estimate = estimate_output_size(
            job.input_path, job.converter, job.options,
            default_preset=self.settings.value("default_preset", "None", type=str),
            media_info=job.media_info,
        )
        job.estimate_text = estimate.describe()
        job.estimate_tooltip = estimate.tooltip()

    def _refresh_all(self):
        has_jobs = bool(len(self.queue))
        self.empty_state.setVisible(not has_jobs)
        self.table.setVisible(has_jobs)
        self.batch_bar.setVisible(has_jobs)
        self.drop_area.set_compact(has_jobs)

        self.batch_bar.set_available_targets(self._available_targets())
        self._update_summary()
        self._update_destination_preview()

    def _available_targets(self) -> List[str]:
        """Output formats reachable by at least one queued file."""
        extensions = set()
        for job in self.queue:
            for converter in find_converters(job.input_path):
                extensions.add(converter.output_extension.lower())
        return sorted(extensions)

    def _update_summary(self):
        jobs = self.queue.jobs
        total = len(jobs)
        selected = sum(1 for job in jobs if job.selected)
        self.batch_bar.set_selection_state(selected, total)

        counts = self.queue.status_counts()
        failed = counts.get(JobStatus.FAILED, 0)
        finished = counts.get(JobStatus.DONE, 0) + counts.get(JobStatus.SKIPPED, 0)
        self.batch_bar.set_action_visibility(bool(failed), bool(finished))

        parts = [f"{selected} {lang.lang.get('of')} {total} {lang.lang.get('selected')}"]
        chosen = [job for job in jobs if job.selected]
        if chosen:
            parts.append(format_size(sum(job.source_size for job in chosen)))
        if failed:
            parts.append(f"{failed} {lang.lang.get('failed')}")
        elif finished:
            parts.append(f"{finished} {lang.lang.get('done')}")
        self.batch_bar.set_summary("  ·  ".join(parts))

        runnable = [job for job in chosen if job.has_converter and job.status is not JobStatus.DONE]
        self.convert_button.setEnabled(bool(runnable) and not self.coordinator.is_running)
        if runnable:
            self.convert_button.setText(
                f"{lang.lang.get('Convert')} {len(runnable)} {lang.lang.get('files')}"
                if len(runnable) > 1 else lang.lang.get("Convert")
            )
        else:
            self.convert_button.setText(lang.lang.get("Convert"))

        self._update_savings(runnable)

    def _update_savings(self, jobs):
        """Aggregate the estimated size change across everything about to run."""
        estimates = [
            estimate_output_size(
                job.input_path, job.converter, job.options,
                default_preset=self.settings.value("default_preset", "None", type=str),
                media_info=job.media_info,
            )
            for job in jobs
        ]
        estimates = [item for item in estimates if item.source]
        if not estimates:
            self.savings_label.setText("")
            return

        source_total = sum(item.source for item in estimates)
        output_total = sum(item.estimated for item in estimates)
        delta = source_total - output_total
        percent = (abs(delta) / source_total * 100) if source_total else 0

        if delta > 0:
            text = (f"{lang.lang.get('Estimated output')} {format_size(output_total)} · "
                    f"{lang.lang.get('saves about')} {format_size(delta)} ({percent:.0f}%)")
        else:
            text = (f"{lang.lang.get('Estimated output')} {format_size(output_total)} · "
                    f"{lang.lang.get('grows by about')} {format_size(abs(delta))} ({percent:.0f}%)")
        self.savings_label.setText(text)

    def _update_destination_preview(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        job = None
        if rows:
            job = self.queue.job(self.table.job_id_at(rows[0].row()))
        if job is None:
            selected = self.queue.selected_jobs()
            job = selected[0] if selected else None

        if job is None or not job.has_converter:
            self.destination_label.setText("")
            return

        policy = OutputPolicy.from_settings(self.settings, self._session_folder)
        if policy.needs_destination_prompt:
            self.destination_label.setText(
                f"{lang.lang.get('Saves to')}: {lang.lang.get('you will be asked')}"
            )
            return

        preview = preview_output_path(job.input_path, job.converter.output_extension, policy)
        self.destination_label.setText(f"{lang.lang.get('Saves to')}: {preview}")

    def _set_busy(self, busy):
        self.convert_button.setEnabled(not busy)
        self.batch_bar.set_enabled_during_run(not busy)
        self.drop_area.setEnabled(not busy)
        self.busy_changed.emit(busy)
        if not busy:
            self._update_summary()

    # ------------------------------------------------------------ plumbing --
    def _notify(self, title, content, level="info"):
        factory = {
            "success": InfoBar.success,
            "warning": InfoBar.warning,
            "error": InfoBar.error,
        }.get(level, InfoBar.info)
        factory(
            title=title, content=content, orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=3500, parent=self.window(),
        )

    @property
    def is_busy(self) -> bool:
        return self.coordinator.is_running

    def shutdown(self):
        self.previews.shutdown()
        self.coordinator.shutdown()

    def retranslate(self):
        self.heading.setText(lang.lang.get("Convert"))
        self.drop_area.retranslate()
        self.batch_bar.retranslate()
        self.empty_state.retranslate()
        self.progress_dock.retranslate()
        self.table.retranslate()
        self.open_folder_button.setText(lang.lang.get("Open output folder"))
        for job in self.queue:
            self.table.update_status(job)
        self._update_summary()
        self._update_destination_preview()

