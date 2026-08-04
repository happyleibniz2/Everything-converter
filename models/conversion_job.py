from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from models.conversion_options import ConversionOptions


@dataclass
class ConversionJob:
    input_path: str
    output_path: str = ""
    converter: Optional[Any] = None
    status: str = "Ready"
    metadata: str = "—"
    options: ConversionOptions = field(default_factory=ConversionOptions)
    progress: int = 0
    error: str = ""
    thumbnail: Optional[str] = None

    @property
    def filename(self) -> str:
        from pathlib import Path
        return Path(self.input_path).name

    def as_row_payload(self) -> Dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "converter": self.converter,
            "status": self.status,
            "metadata": self.metadata,
            "options": self.options.to_dict(),
            "progress": self.progress,
            "error": self.error,
            "thumbnail": self.thumbnail,
        }
