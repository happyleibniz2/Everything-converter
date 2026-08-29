"""Owns the conversion queue as a list of jobs.

The queue is the app's single source of truth: the table view renders it, the
batch worker consumes it, and results are written back to it. Jobs are addressed
by ``job_id``, never by row index, so sorting/removal/reordering cannot
misattribute options or results.
"""

import os
from typing import Callable, Dict, Iterable, List, Optional

from PySide6.QtCore import QObject, Signal

from models.conversion_job import ConversionJob, JobStatus
from models.conversion_options import ConversionOptions
from registry import find_converters


class QueueController(QObject):
    """A de-duplicated, observable list of :class:`ConversionJob`."""

    jobs_added = Signal(list)          # list[ConversionJob]
    job_removed = Signal(int)          # job_id
    job_changed = Signal(int)          # job_id
    queue_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._jobs: List[ConversionJob] = []
        self._by_id: Dict[int, ConversionJob] = {}
        self._keys: Dict[str, int] = {}     # normalised path -> job_id

    # ---------- container protocol ----------
    def __len__(self) -> int:
        return len(self._jobs)

    def __iter__(self):
        return iter(self._jobs)

    def __bool__(self) -> bool:
        return bool(self._jobs)

    @property
    def jobs(self) -> List[ConversionJob]:
        return list(self._jobs)

    def job(self, job_id: int) -> Optional[ConversionJob]:
        return self._by_id.get(job_id)

    def index_of(self, job_id: int) -> int:
        for index, job in enumerate(self._jobs):
            if job.job_id == job_id:
                return index
        return -1

    def at(self, index: int) -> Optional[ConversionJob]:
        if 0 <= index < len(self._jobs):
            return self._jobs[index]
        return None

    def contains(self, file_path: str) -> bool:
        return _key(file_path) in self._keys

    # ---------- mutation ----------
    def add_files(self, file_paths: Iterable[str],
                  default_options: Optional[Callable[[ConversionJob], ConversionOptions]] = None):
        """Add files, skipping duplicates and directories.

        Returns ``(added_jobs, duplicate_count, rejected_paths)``.
        """
        added: List[ConversionJob] = []
        duplicates = 0
        rejected: List[str] = []

        for file_path in file_paths:
            if not file_path:
                continue
            if os.path.isdir(file_path):
                rejected.append(file_path)
                continue
            if not os.path.isfile(file_path):
                rejected.append(file_path)
                continue
            if self.contains(file_path):
                duplicates += 1
                continue

            job = ConversionJob(input_path=file_path)
            candidates = find_converters(file_path)
            job.converter = candidates[0] if candidates else None
            if default_options is not None:
                job.options = default_options(job)

            self._jobs.append(job)
            self._by_id[job.job_id] = job
            self._keys[_key(file_path)] = job.job_id
            added.append(job)

        if added:
            self.jobs_added.emit(added)
        return added, duplicates, rejected

    def remove(self, job_id: int) -> bool:
        job = self._by_id.pop(job_id, None)
        if job is None:
            return False
        self._jobs = [item for item in self._jobs if item.job_id != job_id]
        self._keys.pop(_key(job.input_path), None)
        self.job_removed.emit(job_id)
        return True

    def remove_many(self, job_ids: Iterable[int]) -> int:
        return sum(1 for job_id in list(job_ids) if self.remove(job_id))

    def remove_finished(self) -> int:
        return self.remove_many([
            job.job_id for job in self._jobs
            if job.status in (JobStatus.DONE, JobStatus.SKIPPED)
        ])

    def clear(self) -> None:
        self._jobs.clear()
        self._by_id.clear()
        self._keys.clear()
        self.queue_cleared.emit()

    def move(self, job_id: int, delta: int) -> bool:
        """Shift a job up or down in the queue by ``delta`` positions."""
        index = self.index_of(job_id)
        if index < 0:
            return False
        target = max(0, min(len(self._jobs) - 1, index + delta))
        if target == index:
            return False
        self._jobs.insert(target, self._jobs.pop(index))
        return True

    def reorder(self, job_ids: List[int]) -> None:
        """Reorder to match ``job_ids``; unlisted jobs keep their relative order."""
        ranking = {job_id: position for position, job_id in enumerate(job_ids)}
        self._jobs.sort(key=lambda job: ranking.get(job.job_id, len(ranking)))

    def notify_changed(self, job_id: int) -> None:
        self.job_changed.emit(job_id)

    # ---------- queries ----------
    def selected_jobs(self) -> List[ConversionJob]:
        return [job for job in self._jobs if job.selected]

    def convertible_jobs(self, only_selected: bool = True) -> List[ConversionJob]:
        """Jobs that can actually run: selected, with a converter, not already done."""
        source = self.selected_jobs() if only_selected else self._jobs
        return [job for job in source
                if job.has_converter and job.status is not JobStatus.DONE]

    def failed_jobs(self) -> List[ConversionJob]:
        return [job for job in self._jobs if job.status is JobStatus.FAILED]

    def active_jobs(self) -> List[ConversionJob]:
        return [job for job in self._jobs if job.status.is_active]

    def status_counts(self) -> Dict[JobStatus, int]:
        counts: Dict[JobStatus, int] = {}
        for job in self._jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        return counts

    def total_source_size(self, only_selected: bool = True) -> int:
        source = self.selected_jobs() if only_selected else self._jobs
        return sum(job.source_size for job in source)

    def set_all_selected(self, selected: bool) -> None:
        for job in self._jobs:
            job.selected = selected

    def reset_all(self) -> None:
        for job in self._jobs:
            job.mark_ready()


def _key(file_path: str) -> str:
    return os.path.normcase(os.path.abspath(file_path))
