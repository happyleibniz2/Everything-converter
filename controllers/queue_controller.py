import os
from typing import Iterable, Set


class QueueController:
    """Tracks queue membership independently from the table widget."""

    def __init__(self):
        self._queued_file_keys: Set[str] = set()

    def contains(self, file_path: str) -> bool:
        return os.path.abspath(file_path) in self._queued_file_keys

    def add(self, file_path: str) -> bool:
        key = os.path.abspath(file_path)
        if key in self._queued_file_keys:
            return False
        self._queued_file_keys.add(key)
        return True

    def discard(self, file_path: str) -> None:
        self._queued_file_keys.discard(os.path.abspath(file_path))

    def clear(self) -> None:
        self._queued_file_keys.clear()

    def extend(self, file_paths: Iterable[str]) -> int:
        added = 0
        for file_path in file_paths:
            if self.add(file_path):
                added += 1
        return added
