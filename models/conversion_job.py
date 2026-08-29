import itertools
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from models.conversion_options import ConversionOptions


class JobStatus(Enum):
    """Lifecycle of a single queued conversion."""

    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.DONE, JobStatus.FAILED,
                        JobStatus.CANCELLED, JobStatus.SKIPPED)

    @property
    def is_active(self) -> bool:
        return self in (JobStatus.QUEUED, JobStatus.RUNNING)


# Presentation metadata for each status: (translation key, glyph).
STATUS_DISPLAY = {
    JobStatus.READY: ("Ready", "○"),
    JobStatus.QUEUED: ("Queued", "◔"),
    JobStatus.RUNNING: ("Converting", "◕"),
    JobStatus.DONE: ("Done", "✓"),
    JobStatus.FAILED: ("Failed", "✕"),
    JobStatus.CANCELLED: ("Cancelled", "⊘"),
    JobStatus.SKIPPED: ("Skipped", "→"),
}

_job_ids = itertools.count(1)


@dataclass
class ConversionJob:
    """One file's journey through the queue.

    Jobs are identified by a stable ``job_id`` rather than a table row index, so
    that reordering, sorting and removal cannot misattribute options or results.
    """

    input_path: str
    converter: Optional[Any] = None
    options: ConversionOptions = field(default_factory=ConversionOptions)
    output_path: str = ""
    # Converter template above reflects the user's format choice; this is the
    # options-configured instance the worker actually runs. Set by the planner.
    run_converter: Optional[Any] = None
    status: JobStatus = JobStatus.READY
    progress: int = 0
    error: str = ""
    metadata_text: str = ""
    estimate_text: str = ""
    estimate_tooltip: str = ""
    media_info: dict = field(default_factory=dict)
    thumbnail: Optional[Any] = None
    selected: bool = True
    job_id: int = field(default_factory=lambda: next(_job_ids))

    # ---------- derived ----------
    @property
    def filename(self) -> str:
        return Path(self.input_path).name

    @property
    def source_extension(self) -> str:
        return Path(self.input_path).suffix.lower()

    @property
    def target_extension(self) -> str:
        return self.converter.output_extension if self.converter else ""

    @property
    def source_size(self) -> int:
        try:
            return Path(self.input_path).stat().st_size
        except OSError:
            return 0

    @property
    def has_converter(self) -> bool:
        return self.converter is not None

    def reset_for_run(self) -> None:
        """Clear the results of a previous attempt before re-queueing."""
        self.status = JobStatus.QUEUED
        self.progress = 0
        self.error = ""

    def mark_ready(self) -> None:
        self.status = JobStatus.READY
        self.progress = 0
        self.error = ""
