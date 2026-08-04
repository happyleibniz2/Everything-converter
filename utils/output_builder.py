from pathlib import Path
from PySide6.QtCore import QSettings


def build_output_path(input_file: str, output_extension: str, settings: QSettings) -> str:
    input_path = Path(input_file)
    output_dir = input_path.parent
    mode = settings.value("output_folder_mode", 0, type=int)
    if mode == 2:
        custom = settings.value("custom_folder", "", type=str)
        if custom:
            output_dir = Path(custom)

    output_path = output_dir / f"{input_path.stem}{output_extension}"
    counter = 1
    while output_path.exists() and output_path.resolve() != input_path.resolve():
        output_path = output_dir / f"{input_path.stem}_{counter}{output_extension}"
        counter += 1
    return str(output_path)