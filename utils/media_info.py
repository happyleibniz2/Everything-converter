import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from utils.paths import FFPROBE

def get_media_info(file_path: str) -> Dict[str, Any]:
    """
    Use ffprobe to extract stream info, duration, resolution, etc.
    Returns dict with keys: duration, width, height, bit_rate, codec_name, etc.
    """
    if not FFPROBE.exists():
        return {}

    try:
        cmd = [
            str(FFPROBE),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        info = {}

        # Format info
        fmt = data.get("format", {})
        info["duration"] = float(fmt.get("duration", 0))
        info["size"] = int(fmt.get("size", 0))
        info["bit_rate"] = int(fmt.get("bit_rate", 0))

        # Streams
        video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
        audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]

        if video_streams:
            v = video_streams[0]
            info["width"] = int(v.get("width", 0))
            info["height"] = int(v.get("height", 0))
            info["video_codec"] = v.get("codec_name", "")
            info["video_bitrate"] = int(v.get("bit_rate", 0))
        if audio_streams:
            a = audio_streams[0]
            info["audio_codec"] = a.get("codec_name", "")
            info["sample_rate"] = int(a.get("sample_rate", 0))
            info["channels"] = int(a.get("channels", 0))
            info["audio_bitrate"] = int(a.get("bit_rate", 0))

        return info
    except Exception:
        return {}