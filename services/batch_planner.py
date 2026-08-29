"""Turns queued jobs into runnable work.

Kept separate from the UI so the rules — which jobs are eligible, where each
output goes, how options become a configured converter — can be reasoned about
and tested without a running Qt window.
"""

from dataclasses import dataclass, field
from typing import List

from models.conversion_job import ConversionJob, JobStatus
from services.converter_factory import configure_converter
from services.output_planner import OutputPathPlanner, OutputPolicy


@dataclass
class BatchPlan:
    """The outcome of planning: what will run, and what will not."""

    runnable: List[ConversionJob] = field(default_factory=list)
    skipped: List[ConversionJob] = field(default_factory=list)
    unsupported: List[ConversionJob] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.runnable

    @property
    def total_bytes(self) -> int:
        return sum(job.source_size for job in self.runnable)


def plan_batch(jobs: List[ConversionJob], policy: OutputPolicy,
               default_preset: str = "None", default_threads: int = 0) -> BatchPlan:
    """Assign outputs and configured converters to every eligible job.

    Mutates each runnable job's ``output_path``, ``options`` and ``status``, and
    attaches the configured converter as ``run_converter``. Jobs whose output
    already exists under a Skip policy are marked ``SKIPPED`` rather than run.
    """
    plan = BatchPlan()
    planner = OutputPathPlanner(policy)

    for job in jobs:
        if not job.has_converter:
            plan.unsupported.append(job)
            continue

        extension = job.converter.output_extension
        outcome = planner.plan(job.input_path, extension)

        if outcome.skipped:
            job.output_path = outcome.path
            job.status = JobStatus.SKIPPED
            job.error = ""
            plan.skipped.append(job)
            continue

        job.output_path = outcome.path
        job.options = job.options.merged_with_defaults(
            extension, default_preset=default_preset, default_threads=default_threads
        )
        # Stash the run-ready converter; the template stays on `job.converter`
        # so the UI keeps showing the user's format choice.
        job.run_converter = configure_converter(job.converter, job.options)
        job.reset_for_run()
        plan.runnable.append(job)

    return plan


def recommended_concurrency(settings, job_count: int) -> int:
    """How many conversions to run at once.

    Honours an explicit user setting; otherwise derives a value from the CPU
    count. ffmpeg is already internally threaded, so oversubscribing hurts:
    half the cores is a good default, and there is no point exceeding the
    number of queued files.
    """
    import multiprocessing

    configured = settings.value("parallel_jobs", 0, type=int)
    if configured and configured > 0:
        return max(1, min(configured, job_count))

    try:
        cores = multiprocessing.cpu_count()
    except NotImplementedError:
        cores = 2
    automatic = 1 if cores <= 2 else min(4, cores // 2)
    return max(1, min(automatic, job_count))
