import subprocess
from pathlib import Path
from typing import Callable, Optional, List, Tuple
from logger import logger
from converters.base import Converter
from utils.paths import FFMPEG

class FFmpegConverter(Converter):
    category = "Video"

    def __init__(self, name, input_extensions, output_extension,
                 video_codec=None, audio_codec=None, extra_args=None,
                 threads=None, copy_mode=False, copy_audio=False,
                 start_time=None, end_time=None, scale=None):
        self.name = name
        self.input_extensions = tuple(input_extensions)
        self.output_extension = output_extension
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.extra_args = extra_args or []
        self.threads = threads
        self.copy_mode = copy_mode
        self.copy_audio = copy_audio
        self.start_time = start_time
        self.end_time = end_time
        self.scale = scale

    def _build_command(self, input_file: str, output_file: str) -> List[str]:
        cmd = [str(FFMPEG), "-hide_banner", "-y"]
        if self.start_time:
            cmd.extend(["-ss", self.start_time])
        cmd.extend(["-i", input_file])
        if self.end_time:
            cmd.extend(["-to", self.end_time])

        if self.copy_mode:
            cmd.extend(["-c", "copy"])
        else:
            if self.video_codec:
                cmd.extend(["-c:v", self.video_codec])
            if self.copy_audio:
                cmd.extend(["-c:a", "copy"])
            elif self.audio_codec:
                cmd.extend(["-c:a", self.audio_codec])

        if self.scale and not self.copy_mode:
            cmd.extend(["-vf", f"scale={self.scale}"])
        if self.threads is not None and self.threads > 0:
            cmd.extend(["-threads", str(self.threads)])
        cmd.extend(self.extra_args)
        cmd.append(output_file)
        return cmd

    def convert(self, input_file: str, output_file: str) -> None:
        if not FFMPEG.exists():
            raise FileNotFoundError(f"Bundled FFmpeg executable not found at {FFMPEG}")
        command = self._build_command(input_file, output_file)
        logger.debug("FFmpeg command: %s", " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "FFmpeg conversion failed"
            logger.error("FFmpeg stderr: %s", error_msg)
            raise RuntimeError(error_msg)

    def convert_with_progress(self, input_file, output_file,
                              progress_callback=None, should_cancel=None):
        if not FFMPEG.exists():
            raise FileNotFoundError(f"Bundled FFmpeg executable not found at {FFMPEG}")

        # Get duration
        ffprobe = FFMPEG.parent / "ffprobe.exe"
        duration = None
        if ffprobe.exists():
            try:
                probe = subprocess.run(
                    [str(ffprobe), "-v", "error",
                     "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", input_file],
                    capture_output=True, text=True, timeout=10
                )
                if probe.returncode == 0:
                    duration = float(probe.stdout.strip())
            except Exception:
                pass

        # Build command
        base_cmd = [str(FFMPEG), "-hide_banner", "-y"]
        if self.start_time:
            base_cmd.extend(["-ss", self.start_time])
        base_cmd.extend(["-i", input_file])
        if self.end_time:
            base_cmd.extend(["-to", self.end_time])

        if self.copy_mode:
            base_cmd.extend(["-c", "copy"])
        else:
            if self.video_codec:
                base_cmd.extend(["-c:v", self.video_codec])
            if self.copy_audio:
                base_cmd.extend(["-c:a", "copy"])
            elif self.audio_codec:
                base_cmd.extend(["-c:a", self.audio_codec])

        if self.scale and not self.copy_mode:
            base_cmd.extend(["-vf", f"scale={self.scale}"])
        if self.threads is not None and self.threads > 0:
            base_cmd.extend(["-threads", str(self.threads)])
        base_cmd.extend(self.extra_args)
        base_cmd.extend(["-progress", "pipe:1", "-nostats", output_file])

        logger.debug("FFmpeg command: %s", " ".join(base_cmd))

        # ========== FIX ==========
        # Explicitly use UTF‑8 and replace undecodable bytes with '�'
        proc = subprocess.Popen(
            base_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding='utf-8',       # <-- ADD THIS
            errors='replace'        # <-- ADD THIS
        )
        # =========================

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
                        proc.terminate()
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
                logger.error("FFmpeg stderr: %s", stderr)
                raise RuntimeError(stderr.strip() or "FFmpeg conversion failed")
        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

        if not done and progress_callback:
            progress_callback(100, duration or out_time, 0.0)
