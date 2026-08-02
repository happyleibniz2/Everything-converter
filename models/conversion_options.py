from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConversionOptions:
    preset: str = "None"
    copy_mode: bool = False
    copy_audio: bool = False
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    threads: int = 0
    delete_source: bool = False
    shutdown: bool = False
    extra_args: List[str] = field(default_factory=list)
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    crf: Optional[int] = None
    video_bitrate: Optional[int] = None
    audio_bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    scale: Optional[str] = None

    @classmethod
    def from_mapping(cls, values: Dict[str, Any]) -> "ConversionOptions":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in values.items() if key in allowed})

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if value not in (None, [], {})}
