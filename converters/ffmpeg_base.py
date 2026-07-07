import subprocess
from pathlib import Path
from typing import Callable, Optional, List, Tuple, Dict, Any

from converters.base import Converter
from utils.paths import FFMPEG


class FFmpegConverter(Converter):
    """
    Generic converter that uses a bundled FFmpeg executable.
    Supports both simple conversion and progress reporting.
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

    def _build_command(self, input_file: str, output_file: str) -> List[str]:
        """Build the ffmpeg command line."""
        cmd = [str(FFMPEG), "-hide_banner", "-y", "-i", input_file]
        if self.video_codec:
            cmd.extend(["-c:v", self.video_codec])
        if self.audio_codec:
            cmd.extend(["-c:a", self.audio_codec])
        cmd.extend(self.extra_args)
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
        """
        Run ffmpeg and report progress.
        Progress callback receives (percent, elapsed_seconds, remaining_seconds).
        """
        if not FFMPEG.exists():
            raise FileNotFoundError("Bundled FFmpeg executable not found.")

        # Try to get total duration via ffprobe (if available)
        ffprobe = FFMPEG.parent / "ffprobe.exe"
        duration = None
        if ffprobe.exists():
            try:
                probe = subprocess.run(
                    [
                        str(ffprobe),
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        input_file,
                    ],
                    capture_output=True,
                    text=True,
                )
                if probe.returncode == 0:
                    duration = float(probe.stdout.strip())
            except Exception:
                duration = None

        # Build command with progress output
        command = self._build_command(input_file, output_file)
        # Insert -progress pipe:1 and -nostats after the input
        # We'll insert right after the input
        # Find the index of -i and the input file, then insert after that
        # Simpler: reconstruct with -progress
        base_cmd = [
            str(FFMPEG),
            "-hide_banner",
            "-y",
            "-i",
            input_file,
            "-progress",
            "pipe:1",
            "-nostats",
        ]
        if self.video_codec:
            base_cmd.extend(["-c:v", self.video_codec])
        if self.audio_codec:
            base_cmd.extend(["-c:a", self.audio_codec])
        base_cmd.extend(self.extra_args)
        base_cmd.append(output_file)

        proc = subprocess.Popen(
            base_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        out_time = 0.0
        try:
            if proc.stdout is None:
                proc.wait()
            else:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue

                    # Check cancellation
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
                                out_time = 0.0
                        elif key == "out_time":
                            # fallback if out_time_ms not present
                            try:
                                parts = val.split(":")
                                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                                out_time = h * 3600 + m * 60 + s
                            except Exception:
                                pass
                        elif key == "progress" and val == "end":
                            # finished
                            if progress_callback:
                                if duration:
                                    progress_callback(100, duration, 0.0)
                                else:
                                    progress_callback(100, out_time, 0.0)

                    # Emit periodic progress
                    if progress_callback and out_time is not None:
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