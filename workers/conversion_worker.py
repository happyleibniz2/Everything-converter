"""Runs conversions concurrently and reports progress per job and in aggregate.

Design notes
------------
The previous implementation nested a ``QThread`` inside another ``QThread`` and
called ``wait()``, which forced everything to run strictly one file at a time.
Here a :class:`ConversionCoordinator` lives on the GUI thread and dispatches
:class:`_ConversionTask` runnables onto a ``QThreadPool``, so N files convert at
once. The coordinator owns all aggregate bookkeeping (progress, speed, ETA) and
is the only object the UI talks to.

Progress is weighted by input file size rather than file count: converting a
4 GB movie and a 20 kB PNG should not each be "50% of the batch".
"""

import os
import shutil
import signal
import threading
import time
from pathlib import Path
from typing import Dict, List

import psutil
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from logger import logger
from models.conversion_job import ConversionJob, JobStatus
from utils.paths import TEMP

# Progress weight floor, so zero-byte/unstattable inputs still count for something.
_MIN_WEIGHT = 1024


class _TaskSignals(QObject):
    started = Signal(int)                 # job_id
    progress = Signal(int, int)           # job_id, percent
    finished = Signal(int, str)           # job_id, output_path
    failed = Signal(int, str)             # job_id, error message
    cancelled = Signal(int)               # job_id


class _ConversionTask(QRunnable):
    """Converts one file, writing to a temp path and moving it into place.

    Writing to ``TEMP`` first means a crashed or cancelled conversion never
    leaves a half-written file at the destination.
    """

    def __init__(self, job: ConversionJob, signals: _TaskSignals, control: "_BatchControl"):
        super().__init__()
        self.job = job
        self.signals = signals
        self.control = control
        self.process = None
        self._process_lock = threading.Lock()
        self._cancelled = False
        self.setAutoDelete(True)

    # ---------- process control ----------
    def suspend(self):
        with self._process_lock:
            process = self.process
        if process and process.poll() is None:
            try:
                psutil.Process(process.pid).suspend()
            except Exception as exc:
                if os.name == "posix":
                    try:
                        os.kill(process.pid, signal.SIGSTOP)
                    except Exception as inner:
                        logger.error("Suspend failed for PID %s: %s", process.pid, inner)
                else:
                    logger.error("Suspend failed for PID %s: %s", process.pid, exc)

    def resume(self):
        with self._process_lock:
            process = self.process
        if process and process.poll() is None:
            try:
                psutil.Process(process.pid).resume()
            except Exception as exc:
                if os.name == "posix":
                    try:
                        os.kill(process.pid, signal.SIGCONT)
                    except Exception as inner:
                        logger.error("Resume failed for PID %s: %s", process.pid, inner)
                else:
                    logger.error("Resume failed for PID %s: %s", process.pid, exc)

    def kill(self):
        self._cancelled = True
        with self._process_lock:
            process = self.process
        if process and process.poll() is None:
            try:
                proc = psutil.Process(process.pid)
                for child in proc.children(recursive=True):
                    child.kill()
                proc.kill()
                proc.wait(timeout=3)
            except psutil.NoSuchProcess:
                pass
            except Exception as exc:
                logger.warning("psutil kill failed (%s); using subprocess.kill", exc)
                try:
                    process.kill()
                    process.wait(timeout=3)
                except Exception:
                    pass

    def _set_process(self, process):
        with self._process_lock:
            self.process = process
        # A process spawned while the batch is paused must start out suspended.
        if self.control.is_paused:
            self.suspend()

    def _should_cancel(self) -> bool:
        return self._cancelled or self.control.is_cancelled

    # ---------- execution ----------
    def run(self):
        job = self.job
        # The planner attaches an options-configured converter; fall back to the
        # template so a directly-constructed job still runs.
        converter = job.run_converter or job.converter
        input_file = job.input_path
        output_file = job.output_path

        if self._should_cancel():
            self.signals.cancelled.emit(job.job_id)
            return

        self.signals.started.emit(job.job_id)

        # Unique temp name: parallel jobs must not share a scratch file.
        temp_output = TEMP / f"tmp_{job.job_id}_{Path(output_file).name}"
        moved = False

        try:
            os.makedirs(str(TEMP), exist_ok=True)
            logger.info("Converting %s -> %s via %s", input_file, output_file, converter.name)
            started_at = time.time()

            if hasattr(converter, "convert_with_progress"):
                converter.convert_with_progress(
                    input_file,
                    str(temp_output),
                    progress_callback=self._on_progress,
                    should_cancel=self._should_cancel,
                    process_callback=self._set_process,
                )
            else:
                # Pillow and similar blocking converters give no progress feed.
                self.control.wait_if_paused(self._should_cancel)
                if self._should_cancel():
                    raise _Cancelled()
                converter.convert(input_file, str(temp_output))
                self.signals.progress.emit(job.job_id, 100)

            if self._should_cancel():
                raise _Cancelled()

            destination = Path(output_file)
            os.makedirs(str(destination.parent), exist_ok=True)
            # shutil.move refuses to clobber on some platforms; remove first.
            if destination.exists():
                try:
                    destination.unlink()
                except OSError as exc:
                    raise RuntimeError(f"Cannot replace existing file: {exc}") from exc
            shutil.move(str(temp_output), str(destination))
            moved = True

            logger.info("Done in %.2fs: %s", time.time() - started_at, output_file)

            if job.options.delete_source:
                try:
                    os.remove(input_file)
                    logger.info("Deleted source %s", input_file)
                except OSError as exc:
                    logger.warning("Could not delete source %s: %s", input_file, exc)

            self.signals.progress.emit(job.job_id, 100)
            self.signals.finished.emit(job.job_id, output_file)

        except _Cancelled:
            self.signals.cancelled.emit(job.job_id)
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            if self._should_cancel() or "cancelled" in message.lower():
                self.signals.cancelled.emit(job.job_id)
            else:
                logger.exception("Conversion failed for %s", input_file)
                self.signals.failed.emit(job.job_id, message)
        finally:
            with self._process_lock:
                self.process = None
            if not moved and temp_output.exists():
                try:
                    temp_output.unlink()
                except OSError as exc:
                    logger.warning("Could not remove temp file %s: %s", temp_output, exc)

    def _on_progress(self, percent, _elapsed, _remaining):
        self.control.wait_if_paused(self._should_cancel)
        self.signals.progress.emit(self.job.job_id, int(max(0, min(100, percent))))


class _Cancelled(Exception):
    """Raised internally to unwind a cancelled conversion."""


class _BatchControl:
    """Thread-safe pause/cancel flags shared by every running task."""

    def __init__(self):
        self._resumed = threading.Event()
        self._resumed.set()
        self._cancelled = threading.Event()

    @property
    def is_paused(self) -> bool:
        return not self._resumed.is_set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def pause(self):
        self._resumed.clear()

    def resume(self):
        self._resumed.set()

    def cancel(self):
        self._cancelled.set()
        self._resumed.set()   # release anyone blocked in wait_if_paused

    def wait_if_paused(self, should_cancel=None):
        while not self._resumed.wait(timeout=0.1):
            if should_cancel and should_cancel():
                return


class ConversionCoordinator(QObject):
    """Drives a batch of jobs across a pool of worker threads."""

    # Per-job updates, keyed by job_id.
    job_started = Signal(int)
    job_progress = Signal(int, int)
    job_succeeded = Signal(int, str)
    job_failed = Signal(int, str)
    job_cancelled = Signal(int)

    # Aggregate updates for the progress dock.
    batch_progress = Signal(int)                  # weighted percent 0-100
    batch_counts = Signal(int, int, int)          # completed, failed, total
    batch_stats = Signal(float, float, float)     # bytes/sec, elapsed sec, eta sec
    batch_finished = Signal(int, int, int)        # succeeded, failed, cancelled

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._signals = _TaskSignals()
        self._control = _BatchControl()

        self._signals.started.connect(self._on_started)
        self._signals.progress.connect(self._on_progress)
        self._signals.finished.connect(self._on_finished)
        self._signals.failed.connect(self._on_failed)
        self._signals.cancelled.connect(self._on_cancelled)

        self._tasks: Dict[int, _ConversionTask] = {}
        self._weights: Dict[int, float] = {}
        self._percent: Dict[int, int] = {}
        self._total_weight = 0.0
        self._total = 0
        self._succeeded = 0
        self._failed = 0
        self._cancelled_count = 0
        self._settled = 0
        self._start_time = 0.0
        self._running = False
        self._finish_emitted = False

    # ---------- lifecycle ----------
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._control.is_paused

    def start(self, jobs: List[ConversionJob], concurrency: int = 1) -> int:
        """Dispatch ``jobs``. Returns the number actually queued."""
        if self._running:
            raise RuntimeError("A batch is already running")
        if not jobs:
            return 0

        self._control = _BatchControl()
        self._tasks.clear()
        self._weights.clear()
        self._percent.clear()
        self._succeeded = self._failed = self._cancelled_count = self._settled = 0
        self._finish_emitted = False
        self._total = len(jobs)
        self._start_time = time.time()
        self._running = True

        for job in jobs:
            self._weights[job.job_id] = max(_MIN_WEIGHT, job.source_size)
            self._percent[job.job_id] = 0
        self._total_weight = sum(self._weights.values()) or 1.0

        self._pool.setMaxThreadCount(max(1, int(concurrency)))
        self.batch_counts.emit(0, 0, self._total)
        self.batch_progress.emit(0)

        for job in jobs:
            task = _ConversionTask(job, self._signals, self._control)
            self._tasks[job.job_id] = task
            self._pool.start(task)

        return self._total

    def pause(self):
        if not self._running:
            return
        self._control.pause()
        for task in list(self._tasks.values()):
            task.suspend()

    def resume(self):
        if not self._running:
            return
        self._control.resume()
        for task in list(self._tasks.values()):
            task.resume()

    def cancel(self):
        if not self._running:
            return
        self._control.cancel()
        # Drop everything not yet started, then kill what is running.
        self._pool.clear()
        for task in list(self._tasks.values()):
            task.kill()

    def cancel_job(self, job_id: int):
        task = self._tasks.get(job_id)
        if task:
            task.kill()

    def wait(self, timeout_ms: int = 10000) -> bool:
        return self._pool.waitForDone(timeout_ms)

    def shutdown(self):
        if self._running:
            self.cancel()
        self._pool.waitForDone(5000)

    # ---------- task callbacks ----------
    def _on_started(self, job_id: int):
        self.job_started.emit(job_id)

    def _on_progress(self, job_id: int, percent: int):
        self._percent[job_id] = percent
        self.job_progress.emit(job_id, percent)
        self._emit_aggregate()

    def _on_finished(self, job_id: int, output_path: str):
        self._percent[job_id] = 100
        self._succeeded += 1
        self.job_succeeded.emit(job_id, output_path)
        self._settle(job_id)

    def _on_failed(self, job_id: int, message: str):
        self._failed += 1
        self.job_failed.emit(job_id, message)
        self._settle(job_id)

    def _on_cancelled(self, job_id: int):
        self._cancelled_count += 1
        self.job_cancelled.emit(job_id)
        self._settle(job_id)

    def _settle(self, job_id: int):
        self._tasks.pop(job_id, None)
        self._settled += 1
        self.batch_counts.emit(self._succeeded, self._failed, self._total)
        self._emit_aggregate()

        if self._settled >= self._total and not self._finish_emitted:
            self._finish_emitted = True
            self._running = False
            self.batch_progress.emit(100)
            self.batch_finished.emit(self._succeeded, self._failed, self._cancelled_count)

    # ---------- aggregate maths ----------
    def _emit_aggregate(self):
        if self._total_weight <= 0:
            return

        done_weight = sum(
            self._weights.get(job_id, 0) * (percent / 100.0)
            for job_id, percent in self._percent.items()
        )
        fraction = min(1.0, done_weight / self._total_weight)
        self.batch_progress.emit(int(fraction * 100))

        elapsed = max(0.001, time.time() - self._start_time)
        speed = done_weight / elapsed
        # Extrapolate from observed throughput; only meaningful once underway.
        eta = ((self._total_weight - done_weight) / speed) if speed > 0 and fraction > 0.01 else 0.0
        self.batch_stats.emit(speed, elapsed, eta)
