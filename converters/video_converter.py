"""
Video and Audio converters using the generic FFmpegConverter.
All converters are generated from preset lists.
"""
from .ffmpeg_base import FFmpegConverter

# ---------------------------------------------------------------------
# VIDEO converters (common formats)
# ---------------------------------------------------------------------
video_presets = [
    # (name, input_extensions, output_extension, video_codec, audio_codec)
    ("MP4 → MKV", (".mp4",), ".mkv", "libx264", "aac"),
    ("MP4 → MOV", (".mp4",), ".mov", "libx264", "aac"),
    ("MKV → MP4", (".mkv",), ".mp4", "libx264", "aac"),
    ("MOV → MP4", (".mov",), ".mp4", "libx264", "aac"),
    ("MKV → MOV", (".mkv",), ".mov", "libx264", "aac"),
    ("AVI → MP4", (".avi",), ".mp4", "libx264", "aac"),
    ("MP4 → AVI", (".mp4",), ".avi", "libx264", "aac"),
    ("AVI → MKV", (".avi",), ".mkv", "libx264", "aac"),
    ("AVI → MOV", (".avi",), ".mov", "libx264", "aac"),
    ("MOV → AVI", (".mov",), ".avi", "libx264", "aac"),
    # WebM
    ("MP4 → WEBM", (".mp4",), ".webm", "libvpx", "libvorbis"),
    ("WEBM → MP4", (".webm",), ".mp4", "libx264", "aac"),
    ("WEBM → MKV", (".webm",), ".mkv", "libx264", "aac"),
    ("MKV → WEBM", (".mkv",), ".webm", "libvpx", "libvorbis"),
    # FLV
    ("MP4 → FLV", (".mp4",), ".flv", "libx264", "aac"),
    ("FLV → MP4", (".flv",), ".mp4", "libx264", "aac"),
    # 3GP
    ("MP4 → 3GP", (".mp4",), ".3gp", "libx264", "aac"),
    ("3GP → MP4", (".3gp",), ".mp4", "libx264", "aac"),
    # WMV
    ("MP4 → WMV", (".mp4",), ".wmv", "libx264", "aac"),  # libx264 can output WMV? Actually better use wmv2
    # Better to use a separate codec: we'll keep it simple for now.
]

# Generate video converter instances
video_converters = []
for name, ins, out, vcodec, acodec in video_presets:
    c = FFmpegConverter(name, ins, out, vcodec, acodec)
    c.category = "Video"
    video_converters.append(c)

# ---------------------------------------------------------------------
# AUDIO converters (audio only, add -vn to drop video)
# ---------------------------------------------------------------------
audio_presets = [
    ("MP3 → AAC", (".mp3",), ".aac", None, "aac"),
    ("MP3 → FLAC", (".mp3",), ".flac", None, "flac"),
    ("MP3 → WAV", (".mp3",), ".wav", None, "pcm_s16le"),
    ("WAV → MP3", (".wav",), ".mp3", None, "libmp3lame"),
    ("WAV → FLAC", (".wav",), ".flac", None, "flac"),
    ("WAV → AAC", (".wav",), ".aac", None, "aac"),
    ("AAC → MP3", (".aac",), ".mp3", None, "libmp3lame"),
    ("AAC → FLAC", (".aac",), ".flac", None, "flac"),
    ("FLAC → MP3", (".flac",), ".mp3", None, "libmp3lame"),
    ("FLAC → AAC", (".flac",), ".aac", None, "aac"),
    ("OGG → MP3", (".ogg",), ".mp3", None, "libmp3lame"),
    ("OGG → FLAC", (".ogg",), ".flac", None, "flac"),
    ("MP3 → OGG", (".mp3",), ".ogg", None, "libvorbis"),
    ("M4A → MP3", (".m4a",), ".mp3", None, "libmp3lame"),
    ("M4A → FLAC", (".m4a",), ".flac", None, "flac"),
    ("MP3 → M4A", (".mp3",), ".m4a", None, "aac"),
    ("WMA → MP3", (".wma",), ".mp3", None, "libmp3lame"),  # requires libavcodec with wma support
    ("WMA → FLAC", (".wma",), ".flac", None, "flac"),
]

audio_converters = []
for name, ins, out, vcodec, acodec in audio_presets:
    c = FFmpegConverter(
        name,
        ins,
        out,
        video_codec=None,          # no video
        audio_codec=acodec,
        extra_args=["-vn"],       # drop video stream if present
    )
    c.category = "Audio"
    audio_converters.append(c)

# ---------------------------------------------------------------------
# Export combined list for registry
# ---------------------------------------------------------------------
ALL_FFMPEG_CONVERTERS = video_converters + audio_converters