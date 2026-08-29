
# Everything Converter — The All‑in‑One Multimedia Converter

**Stop juggling multiple tools.** Everything Converter is a powerful, free, and open‑source desktop application that handles all your image, video, and audio conversion needs in one clean interface. Drag, drop, convert — it’s that simple.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Status](https://img.shields.io/badge/status-beta-yellow)

---

## Why Everything Converter?

- **One Tool for Everything** – From PNG to JPG, MP4 to MKV, MP3 to FLAC, and more. No need for separate apps.
- **Parallel Batch Conversion** – Convert several files simultaneously, not one after another. Set one output format for the whole queue, or give each file its own.
- **Batch Options** – Edit encoding settings once and apply them to every selected file.
- **Drag & Drop Simplicity** – Drop files or whole folders and go.
- **Advanced Options When You Need Them** – Fine‑tune codecs, CRF/bitrate, resolution, trimming, and audio per file.
- **Live Progress** – Inline per‑file progress bars plus aggregate throughput, ETA and completion counts.
- **Pause, Resume, Cancel & Retry** – Pause the whole batch, cancel a single file, or retry only what failed.
- **Error Assistant** – Actionable diagnoses instead of raw FFmpeg output.
- **Fluent Design UI** – Mica translucency, light/dark/auto themes and a custom accent colour.
- **Multi‑language** – English, 中文, 日本語 – auto‑detected from your system.
- **Completely Free & Open Source** – MIT licensed, no hidden costs.

---

## What Can You Convert?

| Type | Formats |
|------|---------|
| 🖼️ **Images** | PNG, JPG/JPEG, GIF, WebP, TIFF, BMP, HEIF/HEIC, EPS |
| 🎬 **Video** | MP4, MKV, MOV, AVI, WebM, FLV, 3GP, WMV (with H.264/HEVC/VP8/VP9 support) |
| 🎵 **Audio** | MP3, AAC, FLAC, WAV, OGG (Vorbis), M4A, WMA – plus extraction from video |

---

## Free and Open Source

Everything Converter is **free and open‑source** under the MIT license, with no feature gates,
no upsells, and no limit on how many files you convert in parallel.

Possible future directions (contributions welcome):

| Idea | Notes |
|------|-------|
| 🚀 **GPU Acceleration** | NVENC / AMD AMF / Intel QSV encoders for much faster video conversion. |
| 📄 **PDF, Office & Archives** | The category stubs exist in `converters/`; the backends are not written yet. |
| 💾 **Queue Persistence** | Restore an unfinished queue after a restart. |

---

## Quick Start

### Prerequisites
- Python 3.12+ (if running from source)
- FFmpeg (bundled, but you can also provide your own)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/happyleibniz2/Everything-converter.git
   cd Everything-converter
   ```

2. **Set up a virtual environment (optional)**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**
   ```bash
   python main.py
   ```

> **Note:** If you don't have FFmpeg bundled, download it from [ffmpeg.org](https://ffmpeg.org/) and place `ffmpeg.exe` (and `ffprobe.exe`) in the `ffmpeg/` folder.

### Building a Standalone Executable
Package it for distribution with PyInstaller or Nuitka:
```bash
pyinstaller --onefile --windowed --add-data "resources;resources" --add-data "ffmpeg;ffmpeg" main.py
```

---

## How It Works

1. **Add Files** – Drag & drop files or a whole folder, or use **Add ▸ Add files / Add folder**.
2. **Choose Output** – Pick a format per row, or set **Convert all to:** once for the entire queue.
3. **Tweak Options** (optional) – The gear icon edits one file; **Options for all…** edits every selected file at once.
4. **Convert** – Watch inline per‑file progress plus overall throughput and ETA.
5. **Done** – Open the output folder, or hit **Retry failed** if anything went wrong.

Untick a row's checkbox to leave it out of the run without removing it from the queue.

---

## In‑Depth Features

### Batch Conversion
- **Parallel execution** – Several files encode at once. Set **Files at once** in Settings, or leave it on Auto to use half your CPU cores.
- **Convert all to** – Retarget every compatible file in one action; files that cannot reach that format are reported and left alone.
- **Options for all** – Edit one options sheet and apply it across a whole media category.
- **Per‑file selection** – Checkboxes control what runs; the Convert button reflects the count.
- **Filter, remove selected, clear finished, retry failed** – Manage large queues without starting over.

### Per‑File Customization
- Video codec (H.264, HEVC, VP8/VP9, MPEG‑4, WMV, Xvid)
- CRF (with live quality guidance) or target bitrate
- Resolution presets up to 2160p, or custom dimensions
- Audio codec, bitrate and sample rate
- Trim (start/end)
- Remux only – rewrap streams with no re‑encoding
- Extra FFmpeg arguments, with a live preview of the resulting flags

### Smart Estimation
Estimated output size per file and for the whole batch, accounting for codec efficiency, CRF, downscaling and trimming. Hover any estimate for a confidence rating.

### Safe Output Handling
Conversions are written to a temp file and moved into place on success, so a failure or cancellation never leaves a half‑written file. Naming collisions are resolved across the entire batch, and Overwrite will never destroy a source file.

### Error Assistant
Failures are matched against common FFmpeg problems — missing encoders, permission errors, container/codec mismatches, odd dimensions, out‑of‑memory — and presented with concrete fixes alongside the raw output.

### System Tray & Notifications
Get notified when a batch finishes while the window is in the background.

### Persistent Settings
Theme, accent colour, language, output rules, parallelism and default preset are saved as you change them — no OK button.

---

## Project Structure (For Developers)

```
Everything-converter/
├── app.py                  # Entry point
├── main.py                 # Launcher
├── lang.py                 # i18n manager
├── logger.py               # Logging
├── system_info.py          # System report
├── registry.py             # Converter registry
├── converters/             # Conversion backends
│   ├── base.py
│   ├── image_converter.py  # Pillow
│   ├── video_converter.py  # FFmpeg presets
│   ├── ffmpeg_base.py      # FFmpeg wrapper
│   ├── presets.py          # Codec tables, quality presets (no Qt imports)
│   └── extensions.py       # Format descriptions
├── models/                 # Domain types
│   ├── conversion_job.py   # A queued file + JobStatus lifecycle
│   └── conversion_options.py  # User settings -> ffmpeg arguments
├── services/               # Qt-light logic
│   ├── batch_planner.py    # Eligible jobs, outputs, concurrency
│   ├── output_planner.py   # Overwrite policy + batch collision safety
│   ├── converter_factory.py   # Options -> configured converter
│   ├── preview_service.py  # Off-thread ffprobe + thumbnails
│   └── size_estimator.py   # Output size heuristics
├── controllers/
│   └── queue_controller.py # The queue; jobs addressed by id, not row
├── workers/
│   └── conversion_worker.py   # ConversionCoordinator over a thread pool
├── ui/
│   ├── main_window.py      # FluentWindow shell + navigation
│   ├── interfaces/         # Convert / Formats / Settings pages
│   ├── widgets/            # drop_area, queue_table, batch_bar,
│   │                       #   progress_dock, empty_state
│   ├── options_dialog.py
│   └── error_assistant.py
├── utils/                  # paths, media_info, formatter, output_builder
├── resources/              # Icons, translations, backgrounds
├── ffmpeg/                 # Bundled FFmpeg
└── logs/                   # Runtime logs
```

### Architecture Notes

- **The queue is the single source of truth.** `QueueController` owns a list of
  `ConversionJob`s; the table renders them and the worker consumes them. Jobs are
  addressed by a stable `job_id`, never a row index, so sorting or removing rows
  cannot misattribute options or results.
- **Conversion runs on a thread pool.** `ConversionCoordinator` dispatches one
  runnable per file onto a `QThreadPool` and owns all aggregate bookkeeping.
  Batch progress is weighted by file size, so a 4 GB video and a 20 kB PNG are
  not each "half the batch".
- **Options own their own translation to ffmpeg.** `ConversionOptions.build_extra_args()`
  is the only place user intent becomes command-line flags, which keeps the UI
  out of the business of assembling ffmpeg invocations.
- **Output naming is batch-aware.** `OutputPathPlanner` reserves each path as it
  hands it out, so two queued files that resolve to the same name cannot
  overwrite one another.

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| GUI | PySide6 (Qt 6) |
| Design system | PySide6‑Fluent‑Widgets (WinUI 3 style) |
| Images | Pillow |
| Video/Audio | FFmpeg (bundled) |
| Metadata & thumbnails | FFprobe / FFmpeg / Pillow |
| Concurrency | QThreadPool + QRunnable |
| Process control | psutil (pause / resume / cancel) |
| Settings | QSettings |
| i18n | JSON dictionaries |
| Packaging | PyInstaller / Nuitka |

---

## Contribute

We welcome contributions! Whether it's bug fixes, new converters, translations, or documentation – every bit helps.

1. Fork the repo.
2. Create a branch: `git checkout -b feature/your-idea`.
3. Commit your changes: `git commit -m 'Add your feature'`.
4. Push: `git push origin feature/your-idea`.
5. Open a Pull Request.

Please follow our coding style (Black + Flake8).

---

## Support the Project

If Everything Converter saves you time and makes your life easier, consider supporting its ongoing development. Your support helps us keep the core free and fund future premium features.

| Platform | Link |
|----------|------|
| 🍜 爱发电 (AFDIAN) | [https://afdian.com/a/happyleibniz](https://afdian.com/a/happyleibniz) |
| 🍞 面包多 (Mianbaoduo) | [https://mbd.pub/o/author-bWyblHBqbA==](https://mbd.pub/o/author-bWyblHBqbA==) |

Thank you for your support! 🙏

---

## License

MIT License – see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [FFmpeg](https://ffmpeg.org/) – the backbone of video/audio conversion
- [Pillow](https://python-pillow.org/) – image processing made easy
- [PySide6](https://doc.qt.io/qtforpython-6/) – beautiful cross‑platform GUIs
- [Xiph.Org](https://www.xiph.org/) – for open codecs like Vorbis, Opus, and FLAC

---

## Contact & Support

- **Issues**: [GitHub Issues](https://github.com/happyleibniz2/Everything-converter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/happyleibniz2/Everything-converter/discussions)


