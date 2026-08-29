"""Decides where each converted file goes.

Split out from the UI because output naming has real rules: an overwrite policy,
a destination-folder policy, and — critically — awareness of the *other* files in
the same batch. Two queued inputs can easily resolve to the same output name, and
resolving each one independently would make them overwrite each other.
"""

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple


def _as_enum(enum_type, raw, default):
    """Coerce a persisted integer into ``enum_type``, falling back safely.

    Settings survive upgrades, so a value written by an older build can name an
    option that no longer exists. Silently defaulting beats raising ValueError
    on startup.
    """
    try:
        return enum_type(int(raw))
    except (ValueError, TypeError):
        return default


class OverwritePolicy(IntEnum):
    RENAME = 0
    OVERWRITE = 1
    SKIP = 2


class FolderPolicy(IntEnum):
    SAME_AS_SOURCE = 0
    ASK_EVERY_TIME = 1
    CUSTOM = 2


@dataclass(frozen=True)
class OutputPolicy:
    """Snapshot of the user's output preferences for one planning pass."""

    folder_policy: FolderPolicy = FolderPolicy.SAME_AS_SOURCE
    custom_folder: str = ""
    overwrite: OverwritePolicy = OverwritePolicy.RENAME
    # Destination chosen interactively for this batch; overrides folder_policy.
    session_folder: Optional[str] = None

    @classmethod
    def from_settings(cls, settings, session_folder: Optional[str] = None) -> "OutputPolicy":
        return cls(
            folder_policy=_as_enum(FolderPolicy,
                                   settings.value("output_folder_mode", 0, type=int),
                                   FolderPolicy.SAME_AS_SOURCE),
            custom_folder=settings.value("custom_folder", "", type=str) or "",
            overwrite=_as_enum(OverwritePolicy,
                               settings.value("overwrite_behavior", 0, type=int),
                               OverwritePolicy.RENAME),
            session_folder=session_folder,
        )

    @property
    def needs_destination_prompt(self) -> bool:
        """True when the user must be asked for a folder before converting."""
        if self.session_folder:
            return False
        if self.folder_policy is FolderPolicy.ASK_EVERY_TIME:
            return True
        if self.folder_policy is FolderPolicy.CUSTOM and not self.custom_folder:
            return True
        return False


class OutputPlan:
    """Result of planning one job's destination."""

    __slots__ = ("path", "skipped", "overwrites")

    def __init__(self, path: str, skipped: bool = False, overwrites: bool = False):
        self.path = path
        self.skipped = skipped
        self.overwrites = overwrites


def target_directory(input_file: str, policy: OutputPolicy) -> Path:
    if policy.session_folder:
        return Path(policy.session_folder)
    if policy.folder_policy is FolderPolicy.CUSTOM and policy.custom_folder:
        return Path(policy.custom_folder)
    return Path(input_file).parent


class OutputPathPlanner:
    """Allocates unique output paths across a batch.

    Reserve-as-you-go: every path handed out is remembered, so a later job in the
    same batch will never be given a name an earlier job already claimed, even
    though that file does not exist on disk yet.
    """

    def __init__(self, policy: OutputPolicy):
        self.policy = policy
        self._reserved: Set[str] = set()

    def _is_taken(self, path: Path, input_path: Path) -> bool:
        """True when ``path`` cannot be used as-is.

        Any existing file counts, *including the source itself*: writing the
        output over the input would destroy the file being read.
        """
        if _key(path) in self._reserved:
            return True
        return path.exists()

    def _is_source(self, path: Path, input_path: Path) -> bool:
        try:
            return path.exists() and path.resolve() == input_path.resolve()
        except OSError:
            return _key(path) == _key(input_path)

    def plan(self, input_file: str, output_extension: str) -> OutputPlan:
        input_path = Path(input_file)
        directory = target_directory(input_file, self.policy)
        candidate = directory / f"{input_path.stem}{output_extension}"

        if not self._is_taken(candidate, input_path):
            self._reserved.add(_key(candidate))
            return OutputPlan(str(candidate))

        # Something is in the way. Two cases must never honour the policy:
        #  - the blocker is the source file (overwriting it destroys the input);
        #  - the blocker is another job's reserved output (they would clobber
        #    each other, and the second file would silently win).
        # Both fall through to renaming.
        collides_with_source = self._is_source(candidate, input_path)
        reserved_by_peer = _key(candidate) in self._reserved

        if not collides_with_source and not reserved_by_peer:
            if self.policy.overwrite is OverwritePolicy.OVERWRITE:
                self._reserved.add(_key(candidate))
                return OutputPlan(str(candidate), overwrites=True)
            if self.policy.overwrite is OverwritePolicy.SKIP:
                return OutputPlan(str(candidate), skipped=True)

        renamed = self._next_free_name(directory, input_path, output_extension)
        self._reserved.add(_key(renamed))
        return OutputPlan(str(renamed))

    def _next_free_name(self, directory: Path, input_path: Path, extension: str) -> Path:
        counter = 1
        while True:
            candidate = directory / f"{input_path.stem}_{counter}{extension}"
            if not self._is_taken(candidate, input_path):
                return candidate
            counter += 1
            if counter > 9999:  # pathological; give up on prettiness
                import uuid
                return directory / f"{input_path.stem}_{uuid.uuid4().hex[:8]}{extension}"

    def reserve(self, path: str) -> None:
        self._reserved.add(_key(Path(path)))


def _key(path: Path) -> str:
    # Windows paths are case-insensitive; normalise so collisions are detected.
    return str(path).strip().lower()


def preview_output_path(input_file: str, output_extension: str, policy: OutputPolicy) -> str:
    """Single-shot preview for the UI. Does not reserve anything."""
    return OutputPathPlanner(policy).plan(input_file, output_extension).path


def plan_batch(jobs: Iterable[Tuple[str, str]], policy: OutputPolicy) -> List[OutputPlan]:
    """Plan a whole batch of ``(input_file, output_extension)`` pairs."""
    planner = OutputPathPlanner(policy)
    return [planner.plan(input_file, extension) for input_file, extension in jobs]
