import os
import shutil
import signal
import time
from pathlib import Path

import psutil
from PyQt5.QtCore import QThread, pyqtSignal

import lang
from logger import logger
from utils.paths import TEMP


class BatchConversionWorker(QThread):
    progress_updated = pyqtSignal(int)
    per_file_progress = pyqtSignal(int)
    status_message = pyqtSignal(str)
    speed_updated = pyqtSignal(str)
    current_file_updated = pyqtSignal(str)
    time_updated = pyqtSignal(str, str)
    conversion_finished = pyqtSignal(int, list)

    def __init__(self, task_list, delete_source=False):
        super().__init__()
        self.task_list = task_list
        self.total = len(task_list)
        self.converted = 0
        self.errors = []
        self.is_paused = False
        self.is_cancelled = False
        self.delete_source = delete_source
        self.current_worker = None
        self._stop_requested = False

    def pause(self):
        self.is_paused = True
        if self.current_worker:
            self.current_worker.pause()

    def resume(self):
        self.is_paused = False
        if self.current_worker:
            self.current_worker.resume()

    def cancel(self):
        self.is_cancelled = True
        if self.current_worker:
            self.current_worker.cancel()

    def run(self):
        self.start_time = time.time()
        self.bytes_processed = 0

        for idx, (converter, input_file, output_file) in enumerate(self.task_list, start=1):
            if self.is_cancelled or self._stop_requested:
                break

            while self.is_paused:
                time.sleep(0.1)

            self.current_file_updated.emit(Path(input_file).name)
            self.status_message.emit(f"{lang.lang.get('Converting')} {idx}/{self.total}...")

            worker = ConversionWorker(converter, [(input_file, output_file)], self.delete_source)
            self.current_worker = worker

            worker.per_file_progress.connect(self.per_file_progress.emit)
            worker.speed_updated.connect(self.speed_updated.emit)
            worker.time_updated.connect(self.time_updated.emit)

            worker.start()
            worker.wait()

            if worker.errors:
                self.errors.extend(worker.errors)
            else:
                self.converted += 1

            self.progress_updated.emit(idx)
            self.bytes_processed += worker.bytes_processed

            if self.is_cancelled:
                break

        self.conversion_finished.emit(self.converted, self.errors)


class ConversionWorker(QThread):
    progress_updated = pyqtSignal(int)
    per_file_progress = pyqtSignal(int)
    status_message = pyqtSignal(str)
    speed_updated = pyqtSignal(str)
    current_file_updated = pyqtSignal(str)
    time_updated = pyqtSignal(str, str)
    conversion_finished = pyqtSignal(int, list)

    def __init__(self, converter, file_pairs, delete_source=False):
        super().__init__()
        self.converter = converter
        self.file_pairs = file_pairs
        self.converted = 0
        self.errors = []
        self.is_paused = False
        self.is_cancelled = False
        self.start_time = None
        self.bytes_processed = 0
        self.delete_source = delete_source
        self.current_process = None

    def pause(self):
        self.is_paused = True
        if self.current_process and self.current_process.poll() is None:
            try:
                psutil.Process(self.current_process.pid).suspend()
                logger.info(f"Suspended FFmpeg PID {self.current_process.pid}")
            except Exception as e:
                # Fallback: try POSIX signals if psutil suspend fails
                try:
                    if os.name == 'posix':
                        os.kill(self.current_process.pid, signal.SIGSTOP)
                        logger.info(f"Sent SIGSTOP to FFmpeg PID {self.current_process.pid}")
                    else:
                        logger.error(f"Failed to suspend FFmpeg PID {self.current_process.pid}: {e}")
                except Exception as e2:
                    logger.error(f"Suspend fallback failed: {e2}")

    def resume(self):
        self.is_paused = False
        if self.current_process and self.current_process.poll() is None:
            try:
                psutil.Process(self.current_process.pid).resume()
                logger.info(f"Resumed FFmpeg PID {self.current_process.pid}")
            except Exception as e:
                # Fallback: try POSIX signals if psutil resume fails
                try:
                    if os.name == 'posix':
                        os.kill(self.current_process.pid, signal.SIGCONT)
                        logger.info(f"Sent SIGCONT to FFmpeg PID {self.current_process.pid}")
                    else:
                        logger.error(f"Failed to resume FFmpeg PID {self.current_process.pid}: {e}")
                except Exception as e2:
                    logger.error(f"Resume fallback failed: {e2}")

    def cancel(self):
        self.is_cancelled = True
        if self.current_process and self.current_process.poll() is None:
            try:
                proc = psutil.Process(self.current_process.pid)
                children = proc.children(recursive=True)
                for child in children:
                    child.kill()
                proc.kill()
                proc.wait(timeout=2)
                logger.info(f"Force-killed FFmpeg PID {self.current_process.pid}")
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                logger.warning(f"Psutil kill failed, falling back to subprocess: {e}")
                try:
                    self.current_process.kill()
                    self.current_process.wait(timeout=2)
                except Exception:
                    pass

    def run(self):
        total_files = len(self.file_pairs)
        self.start_time = time.time()

        for index, (input_file, output_file) in enumerate(self.file_pairs, start=1):
            if self.is_cancelled:
                break

            while self.is_paused:
                time.sleep(0.1)

            self.current_file_updated.emit(Path(input_file).name)
            self.status_message.emit(f"{lang.lang.get('Converting')} {index}/{total_files}...")

            temp_output = str(TEMP / f"temp_{Path(output_file).name}")
            os.makedirs(os.path.dirname(temp_output), exist_ok=True)
            moved = False

            try:
                file_size = Path(input_file).stat().st_size
                logger.info("================================================")
                logger.info("Conversion")
                logger.info("Input: %s", input_file)
                logger.info("Output: %s", output_file)
                logger.info("Converter: %s", self.converter.name)
                start_file = time.time()

                if hasattr(self.converter, "convert_with_progress"):
                    def _progress_cb(percent, elapsed_sec, remaining_sec):
                        while self.is_paused:
                            time.sleep(0.1)

                        elapsed_text = time.strftime("%H:%M:%S", time.gmtime(elapsed_sec))
                        remaining_text = time.strftime("%H:%M:%S", time.gmtime(remaining_sec)) if remaining_sec else "00:00:00"

                        try:
                            bytes_for_file = int(file_size * (percent / 100.0))
                        except Exception:
                            bytes_for_file = 0

                        total_processed = self.bytes_processed + bytes_for_file
                        total_elapsed = time.time() - self.start_time if self.start_time else elapsed_sec
                        speed_mbps = (total_processed / (1024 * 1024)) / max(total_elapsed, 0.001)

                        self.per_file_progress.emit(int(percent))
                        self.time_updated.emit(elapsed_text, remaining_text)
                        self.speed_updated.emit(f"{speed_mbps:.2f} MB/s")

                    self.converter.convert_with_progress(
                        input_file,
                        temp_output,
                        progress_callback=_progress_cb,
                        should_cancel=lambda: self.is_cancelled,
                        process_callback=lambda proc: setattr(self, 'current_process', proc)
                    )
                else:
                    self.converter.convert(input_file, temp_output)

                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                shutil.move(temp_output, output_file)
                moved = True

                duration = time.time() - start_file
                self.bytes_processed += file_size
                self.converted += 1

                if self.delete_source:
                    try:
                        os.remove(input_file)
                        logger.info("Deleted source: %s", input_file)
                    except Exception as e:
                        logger.warning("Could not delete source: %s", e)

                logger.info("Duration: %.2f seconds", duration)
                logger.info("Success")
            except Exception as exc:
                logger.exception("Conversion failed for %s", input_file)
                self.errors.append(f"{Path(input_file).name}: {exc}")
                if self.is_cancelled:
                    self.status_message.emit(lang.lang.get("Cancel"))
                    break
            finally:
                if not moved and os.path.exists(temp_output):
                    try:
                        os.remove(temp_output)
                        logger.info("Removed temporary file: %s", temp_output)
                    except Exception as e:
                        logger.warning("Failed to remove temporary file: %s", e)
                self.current_process = None

            elapsed = time.time() - self.start_time
            remaining = 0.0
            if index > 0 and index < total_files:
                remaining = elapsed / index * (total_files - index)

            elapsed_text = time.strftime("%H:%M:%S", time.gmtime(elapsed))
            remaining_text = time.strftime("%H:%M:%S", time.gmtime(remaining))

            speed_mbps = (self.bytes_processed / (1024 * 1024)) / max(elapsed, 0.001)
            self.speed_updated.emit(f"{speed_mbps:.2f} MB/s")
            self.time_updated.emit(elapsed_text, remaining_text)
            self.progress_updated.emit(index)
            self.per_file_progress.emit(100)

        self.conversion_finished.emit(self.converted, self.errors)


# ---------- Drop Area (unchanged) ----------
