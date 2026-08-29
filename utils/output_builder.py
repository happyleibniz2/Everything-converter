"""Backwards-compatible shim over :mod:`services.output_planner`.

New code should use ``OutputPathPlanner`` directly so that collisions are
resolved across a whole batch rather than one file at a time.
"""

from PySide6.QtCore import QSettings

from services.output_planner import OutputPolicy, preview_output_path


def build_output_path(input_file: str, output_extension: str, settings: QSettings) -> str:
    return preview_output_path(input_file, output_extension, OutputPolicy.from_settings(settings))
