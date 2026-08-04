
# Everything Converter — The All-in-One Multimedia Converter

**Stop juggling multiple tools.** Everything Converter is a powerful, free, and open-source desktop application that handles all your image, video, and audio conversion needs in one clean interface. Drag, drop, convert—it's that simple.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Status](https://img.shields.io/badge/status-beta-yellow)

---

## Why Everything Converter?

- **One Tool for Everything** – From PNG to JPG, MP4 to MKV, MP3 to FLAC, and more. No need for separate apps.
- **Batch Processing** – Convert hundreds of files at once, each with its own target format.
- **Drag & Drop Simplicity** – Just drop your files and go. No complicated settings unless you want them.
- **Advanced Options When You Need Them** – Fine-tune video codecs, quality, scaling, trimming, and audio settings per file.
- **Real‑time Progress** – See speed, time remaining, and per‑file progress as your conversions run.
- **Pause & Resume** – Control conversions at your own pace.
- **Error Assistant** – Get helpful suggestions when something goes wrong.
- **Dark & Light Themes** – Work comfortably day or night.
- **Multi‑language** – English, 中文, 日本語 – more coming.
- **Completely Free & Open Source** – MIT licensed, no hidden costs.

---

## What Can You Convert?

| Type | Formats |
|------|---------|
| 🖼️ **Images** | PNG, JPG/JPEG, GIF, WebP, TIFF, BMP, HEIF/HEIC, EPS |
| 🎬 **Video** | MP4, MKV, MOV, AVI, WebM, FLV, 3GP, WMV (with H.264/HEVC/VP8/VP9 support) |
| 🎵 **Audio** | MP3, AAC, FLAC, WAV, OGG (Vorbis), M4A, WMA – plus extraction from video |

---

## Quick Start

### Prerequisites
- Python 3.10+ (if running from source)
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

1. **Add Files** – Drag & drop or click to browse.
2. **Choose Output** – Each file gets a dropdown with all compatible formats.
3. **Tweak Options** (optional) – Click the gear icon to set codec, quality, trim, scale, and more per file.
4. **Convert** – Hit the big Convert button and watch the magic happen.
5. **Done** – Open the output folder or open converted files directly.

It's that simple.

---

## In-Depth Features

### Per‑File Customization
Not all files are the same. You can set different conversion parameters for each file:
- Video codec (H.264, HEVC, VP9, etc.)
- Audio codec and bitrate
- CRF or target bitrate
- Scale/resize
- Trim (start/end time)
- Copy streams (no re‑encode)
- Extra FFmpeg arguments

### Smart Estimation
Before converting, see estimated output size and space saved – so you know what to expect.

### Error Assistant
When a conversion fails, you get actionable suggestions instead of cryptic errors. No more googling.

### System Tray & Notifications
Minimize to tray and get notified when your batch finishes – ideal for long conversions.

### Persistent Settings
Your preferences (theme, language, output folder, default preset) are saved automatically.

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
│   └── extensions.py       # Format descriptions
├── ui/                     # PySide6 GUI
│   ├── main_window.py
│   ├── drop_area.py
│   ├── options_dialog.py
│   ├── settings_dialog.py
│   ├── about_dialog.py
│   └── error_assistant.py
├── utils/                  # Helpers
│   ├── paths.py
│   ├── media_info.py
│   ├── output_builder.py
│   ├── formatter.py
│   └── size_estimator.py
├── workers/                # QThread workers
│   └── conversion_worker.py
├── controllers/            # Business logic
│   └── queue_controller.py
├── models/                 # Data classes
├── resources/              # Icons, translations, backgrounds
├── ffmpeg/                 # Bundled FFmpeg
└── logs/                   # Runtime logs
```

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| GUI | PySide6 (Qt) |
| Images | Pillow |
| Video/Audio | FFmpeg |
| Metadata | FFprobe |
| Concurrency | QThread |
| Settings | QSettings |
| i18n | JSON |
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

If Everything Converter saves you time and makes your life easier, consider supporting its ongoing development. Every contribution helps keep the project alive and improving!

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
- [PySide6](https://doc.qt.io/qtforpython-6/) – beautiful cross-platform GUIs
- [Xiph.Org](https://www.xiph.org/) – for open codecs like Vorbis, Opus, and FLAC

---

## Contact & Support

- **Issues**: [GitHub Issues](https://github.com/happyleibniz2/Everything-converter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/happyleibniz2/Everything-converter/discussions)

