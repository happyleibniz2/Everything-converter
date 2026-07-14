import subprocess
from pathlib import Path
from typing import Callable, Optional, List, Tuple
from logger import logger
from converters.base import Converter
from utils.paths import FFMPEG
import sys,time

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
        cmd = self._build_base_args(input_file)
        cmd.append(output_file)
        return cmd

    def _build_base_args(self, input_file: str) -> List[str]:
        """Build the common ffmpeg argument list (without progress flags or final output).

        This centralizes flag construction so both `convert` and `convert_with_progress`
        use identical parameters.
        """
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

        # Work on a local copy to avoid mutating self.extra_args
        extra = list(self.extra_args or [])

        # If user provided -vf or -filter:v in extra args, merge scale into it
        scale_merged = False
        if self.scale and not self.copy_mode and extra:
            for i, a in enumerate(extra):
                la = a.lower()
                if la == "-vf" or la == "-filter:v":
                    # next element should be the filter string
                    if i + 1 < len(extra):
                        existing = extra[i + 1]
                        extra[i + 1] = f"scale={self.scale},{existing}"
                        scale_merged = True
                        logger.warning("Both scale and user-supplied vf detected; merging scale into user vf.")
                        break
                elif la.startswith("-vf="):
                    existing = a.split("=", 1)[1]
                    extra[i] = f"-vf=scale={self.scale},{existing}"
                    scale_merged = True
                    logger.warning("Both scale and user-supplied vf detected; merged scale into -vf=... argument.")
                    break
                elif la.startswith("-filter:v="):
                    existing = a.split("=", 1)[1]
                    extra[i] = f"-filter:v=scale={self.scale},{existing}"
                    scale_merged = True
                    logger.warning("Both scale and user-supplied filter:v detected; merged scale into -filter:v=... argument.")
                    break

        # Only add our own -vf scale if we didn't merge and scale is requested
        if self.scale and not self.copy_mode and not scale_merged:
            cmd.extend(["-vf", f"scale={self.scale}"])

        if self.threads is not None and self.threads > 0:
            cmd.extend(["-threads", str(self.threads)])

        cmd.extend(extra)
        return cmd

    def convert(self, input_file: str, output_file: str) -> None:
        if not FFMPEG.exists():
            raise FileNotFoundError(f"Bundled FFmpeg executable not found at {FFMPEG}")
        command = self._build_command(input_file, output_file)
        logger.debug("FFmpeg command: %s", " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "FFmpeg conversion failed"
            logger.critical("FFmpeg stderr: %s", error_msg)
            raise RuntimeError(error_msg)

    def convert_with_progress(self, input_file, output_file,
                            progress_callback=None, should_cancel=None,
                            process_callback=None):
        if not FFMPEG.exists():
            logger.critical("Bundled FFmpeg executable not found at %s", FFMPEG)
            raise FileNotFoundError(f"Bundled FFmpeg executable not found at {FFMPEG}")

        # 获取视频时长（可选）
        duration = None
        ffprobe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
        ffprobe = FFMPEG.parent / ffprobe_name
        if ffprobe.exists():
            try:
                probe = subprocess.run(
                    [str(ffprobe), "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", input_file],
                    capture_output=True, text=True, timeout=10,
                    encoding='utf-8', errors='ignore'
                )
                if probe.returncode == 0:
                    duration = float(probe.stdout.strip())
            except Exception:
                pass

        # 构建基础命令（不含 -progress 和输出文件）
        base_cmd = self._build_base_args(input_file)
        base_cmd.extend(["-progress", "pipe:1", "-nostats", output_file])

        logger.debug("FFmpeg command: %s", " ".join(base_cmd))

        proc = subprocess.Popen(
            base_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace'
        )
        if process_callback:
            process_callback(proc)

        output_lines = []
        out_time = 0.0
        done = False
        last_emit = 0.0
        emit_interval = 0.2

        try:
            if proc.stdout is None:
                rc = proc.wait()
            else:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    output_lines.append(line)

                    if should_cancel and should_cancel():
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
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
                            # 强制发射 100%
                            if progress_callback:
                                try:
                                    progress_callback(100, duration or out_time, 0.0)
                                except Exception:
                                    pass

                    # 进度回调节流
                    if progress_callback and out_time is not None and not done:
                        if duration:
                            percent = int(min(100, (out_time / duration) * 100))
                            remaining = max(0.0, duration - out_time)
                        else:
                            percent = 0
                            remaining = 0.0

                        now = time.time()
                        if (now - last_emit) >= emit_interval:
                            last_emit = now
                            try:
                                progress_callback(percent, out_time, remaining)
                            except Exception:
                                pass

                rc = proc.wait()

            if rc != 0:
                error_text = "\n".join(output_lines[-50:])
                logger.error("FFmpeg exited with code %s", rc)
                raise RuntimeError(f"FFmpeg exited with code {rc}: {error_text.strip() or 'FFmpeg conversion failed'}")
        finally:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if proc.stdout:
                proc.stdout.close()

        # 如果循环没收到 end 信号，主动补发 100%
        if not done and progress_callback:
            progress_callback(100, duration or out_time, 0.0)