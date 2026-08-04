import json
import subprocess
from typing import Dict, Any
from utils.paths import FFPROBE

def get_media_info(file_path: str) -> Dict[str, Any]:
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
        fmt = data.get("format", {})
        info["duration"] = float(fmt.get("duration", 0))
        info["size"] = int(fmt.get("size", 0))
        info["bit_rate"] = int(fmt.get("bit_rate", 0))

        video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
        audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]

        if video_streams:
            v = video_streams[0]
            info["width"] = int(v.get("width", 0))
            info["height"] = int(v.get("height", 0))
            info["video_codec"] = v.get("codec_name", "")
            info["video_bitrate"] = int(v.get("bit_rate", 0))

            fps = v.get("r_frame_rate") or v.get("avg_frame_rate") or ""
            try:
                if fps and "/" in fps:
                    num, den = fps.split("/", 1)
                    num = float(num)
                    den = float(den)
                    info["fps"] = round(num / den, 2) if den else 0.0
                elif fps:
                    info["fps"] = float(fps)
                else:
                    info["fps"] = 0.0
            except Exception:
                info["fps"] = 0.0

        if audio_streams:
            a = audio_streams[0]
            info["audio_codec"] = a.get("codec_name", "")
            info["sample_rate"] = int(a.get("sample_rate", 0))
            info["channels"] = int(a.get("channels", 0))
            info["audio_bitrate"] = int(a.get("bit_rate", 0))
            info["sample_format"] = a.get("sample_fmt", "")
            info["bits_per_sample"] = int(a.get("bits_per_sample", 0))
        return info
    except Exception:
        return {}
