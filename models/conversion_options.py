from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from converters.presets import (
    PRESETS,
    DEFAULT_VIDEO_CODEC,
    DEFAULT_AUDIO_CODEC,
)


@dataclass
class ConversionOptions:
    """Everything the user can tune for a single conversion.

    Owns the translation from user intent to ffmpeg arguments so that the UI
    never has to assemble command lines itself.
    """

    preset: str = "None"
    copy_mode: bool = False
    copy_audio: bool = False
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    threads: int = 0
    delete_source: bool = False
    extra_args: List[str] = field(default_factory=list)
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    crf: Optional[int] = None
    video_bitrate: Optional[int] = None
    audio_bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    scale: Optional[str] = None

    # ---------- construction ----------
    @classmethod
    def from_mapping(cls, values: Dict[str, Any]) -> "ConversionOptions":
        allowed = set(cls.__dataclass_fields__)
        payload = {key: value for key, value in (values or {}).items() if key in allowed}
        payload.setdefault("extra_args", [])
        if payload.get("extra_args") is None:
            payload["extra_args"] = []
        return cls(**payload)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    def copy(self) -> "ConversionOptions":
        return replace(self, extra_args=list(self.extra_args))

    def merged_with_defaults(self, output_extension: str, default_preset: str = "None",
                             default_threads: int = 0) -> "ConversionOptions":
        """Return a copy with codec/preset/threads gaps filled in for a target format."""
        merged = self.copy()
        if not merged.preset:
            merged.preset = default_preset or "None"
        if merged.threads in (None, 0):
            merged.threads = default_threads or 0
        if merged.video_codec is None:
            merged.video_codec = DEFAULT_VIDEO_CODEC.get(output_extension)
        if merged.audio_codec is None:
            merged.audio_codec = DEFAULT_AUDIO_CODEC.get(output_extension)
        return merged

    # ---------- ffmpeg translation ----------
    def build_extra_args(self) -> List[str]:
        """Assemble the full ffmpeg extra-argument list for these options.

        Ordering matters: user-supplied ``extra_args`` come first so that the
        preset and explicit quality flags below can override them, and ``-vf``
        merging in ``FFmpegConverter`` sees a stable layout.
        """
        args: List[str] = list(self.extra_args or [])
        args.extend(PRESETS.get(self.preset or "None", []))

        # Stream copy makes every encoder flag meaningless, so skip them.
        if not self.copy_mode:
            if self.crf is not None:
                args = _replace_flag(args, "-crf", str(self.crf))
            elif self.video_bitrate is not None:
                args.extend(["-b:v", f"{self.video_bitrate}k"])

            if not self.copy_audio:
                if self.audio_bitrate is not None:
                    args.extend(["-b:a", f"{self.audio_bitrate}k"])
                if self.sample_rate is not None:
                    args.extend(["-ar", str(self.sample_rate)])

        return args

    def converter_kwargs(self) -> Dict[str, Any]:
        """Keyword arguments for rebuilding a configured ``FFmpegConverter``.

        ``start_time``/``end_time``/``scale`` are passed as first-class fields
        rather than raw args because ``FFmpegConverter`` must place ``-ss``
        before ``-i`` and merge ``scale`` into any user ``-vf`` chain.
        """
        return {
            "video_codec": None if self.copy_mode else self.video_codec,
            "audio_codec": None if self.copy_mode else self.audio_codec,
            "extra_args": self.build_extra_args(),
            "threads": self.threads or 0,
            "copy_mode": self.copy_mode,
            "copy_audio": self.copy_audio,
            "start_time": self.start_time or None,
            "end_time": self.end_time or None,
            "scale": self.scale or None,
        }

    # ---------- display ----------
    def summary(self) -> str:
        """Short human readable description of the non-default choices."""
        parts: List[str] = []
        if self.copy_mode:
            parts.append("Remux (no re-encode)")
        else:
            if self.video_codec:
                parts.append(self.video_codec)
            if self.crf is not None:
                parts.append(f"CRF {self.crf}")
            elif self.video_bitrate is not None:
                parts.append(f"{self.video_bitrate} kbps")
            if self.scale:
                parts.append(self.scale.replace(":", "x"))
            if self.copy_audio:
                parts.append("copy audio")
            elif self.audio_bitrate is not None:
                parts.append(f"audio {self.audio_bitrate} kbps")
        if self.preset and self.preset != "None":
            parts.append(self.preset)
        if self.start_time or self.end_time:
            parts.append(f"trim {self.start_time or '0'}→{self.end_time or 'end'}")
        return " · ".join(parts) if parts else "Default settings"


def _replace_flag(args: List[str], flag: str, value: str) -> List[str]:
    """Set ``flag value`` in ``args``, replacing an existing occurrence.

    Presets embed flags like ``-crf``; an explicit user choice must win without
    ffmpeg seeing the flag twice.
    """
    result = list(args)
    for index, item in enumerate(result):
        if item == flag and index + 1 < len(result):
            result[index + 1] = value
            return result
    result.extend([flag, value])
    return result
