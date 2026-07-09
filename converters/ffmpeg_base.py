import subprocess
from pathlib import Path
from typing import Callable, Optional, List, Tuple

from converters.base import Converter
from utils.paths import FFMPEG


class FFmpegConverter(Converter):
    """
    Generic converter that uses a bundled FFmpeg executable.
    Supports both simple conversion and progress reporting with overrides.
    """

    category = "Video"  # can be overridden for audio etc.

    def __init__(
        self,
        name: str,
        input_extensions: Tuple[str, ...],
        output_extension: str,
        video_codec: Optional[str] = None,
        audio_codec: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ):
        self.name = name
        self.input_extensions = tuple(input_extensions)
        self.output_extension = output_extension
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.extra_args = extra_args or []

        # Override storage (initially None)
        self._video_codec_override = None
        self._audio_codec_override = None
        self._extra_args_override = None

    def set_override(self, video_codec=None, audio_codec=None, extra_args=None):
        """Set temporary overrides for codecs and extra arguments."""
        self._video_codec_override = video_codec
        self._audio_codec_override = audio_codec
        self._extra_args_override = extra_args

    def _build_command(self, input_file: str, output_file: str) -> List[str]:
        """Build the ffmpeg command using overrides if present."""
        cmd = [str(FFMPEG), "-hide_banner", "-y", "-i", input_file]

        vcodec = self._video_codec_override if self._video_codec_override is not None else self.video_codec
        acodec = self._audio_codec_override if self._audio_codec_override is not None else self.audio_codec
        extra = self._extra_args_override if self._extra_args_override is not None else self.extra_args

        if vcodec:
            cmd.extend(["-c:v", vcodec])
        if acodec:
            cmd.extend(["-c:a", acodec])
        if extra:
            cmd.extend(extra)
        cmd.append(output_file)
        return cmd

    def convert(self, input_file: str, output_file: str) -> None:
        """Run conversion without progress reporting (blocking)."""
        if not FFMPEG.exists():
            raise FileNotFoundError("Bundled FFmpeg executable not found.")

        command = self._build_command(input_file, output_file)
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            error_message = result.stderr.strip() or "FFmpeg conversion failed"
            raise RuntimeError(error_message)

    def convert_with_progress(
        self,
        input_file: str,
        output_file: str,
        progress_callback: Optional[Callable[[int, float, float], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> None:
        if not FFMPEG.exists():
            raise FileNotFoundError("Bundled FFmpeg executable not found.")

        ffprobe = FFMPEG.parent / "ffprobe.exe"
        duration = None
        if ffprobe.exists():
            try:
                probe = subprocess.run(
                    [
                        str(ffprobe),
                        "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        input_file,
                    ],
                    capture_output=True,
                    text=True,
                )
                if probe.returncode == 0:
                    duration = float(probe.stdout.strip())
            except Exception:
                pass

        base_cmd = [
            str(FFMPEG),
            "-hide_banner",
            "-y",
            "-i", input_file,
            "-progress", "pipe:1",
            "-nostats",
        ]
        vcodec = self._video_codec_override if self._video_codec_override is not None else self.video_codec
        acodec = self._audio_codec_override if self._audio_codec_override is not None else self.audio_codec
        extra = self._extra_args_override if self._extra_args_override is not None else self.extra_args

        if vcodec:
            base_cmd.extend(["-c:v", vcodec])
        if acodec:
            base_cmd.extend(["-c:a", acodec])
        if extra:
            base_cmd.extend(extra)
        base_cmd.append(output_file)

        proc = subprocess.Popen(
            base_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        out_time = 0.0
        done = False
        try:
            if proc.stdout is None:
                proc.wait()
            else:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue

                    if should_cancel and should_cancel():
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        raise RuntimeError("Cancelled")

                    if "=" in line:
                        key, val = line.split("=", 1)
                        if key == "out_time_ms":
                            try:
                                out_time = int(val) / 1000.0
                            except Exception:
                                pass
                        elif key == "out_time":
                            try:
                                parts = val.split(":")
                                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                                out_time = h * 3600 + m * 60 + s
                            except Exception:
                                pass
                        elif key == "progress" and val == "end":
                            done = True
                            if progress_callback:
                                progress_callback(100, duration or out_time, 0.0)

                    if progress_callback and out_time is not None and not done:
                        if duration:
                            percent = int(min(100, (out_time / duration) * 100))
                            remaining = max(0.0, duration - out_time)
                        else:
                            percent = 0
                            remaining = 0.0
                        progress_callback(percent, out_time, remaining)

            rc = proc.wait()
            if rc != 0:
                stderr = proc.stderr.read() if proc.stderr is not None else ""
                raise RuntimeError(stderr.strip() or "FFmpeg conversion failed")

        finally:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass

        # If we never got a progress=end, force 100% now
        if not done and progress_callback:
            progress_callback(100, duration or out_time, 0.0)