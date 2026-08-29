def format_size(size: float) -> str:
    size = float(size or 0)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_short_duration(seconds: float) -> str:
    seconds = float(seconds or 0)
    if seconds <= 0:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        minutes, secs = divmod(seconds, 60)
        return f"{int(minutes):02d}:{int(secs):02d}"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"


def format_clock(seconds: float) -> str:
    """Always-HH:MM:SS rendering for elapsed/remaining readouts."""
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_speed(bytes_per_second: float) -> str:
    value = float(bytes_per_second or 0)
    if value <= 0:
        return "—"
    for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
        if value < 1024.0 or unit == "GB/s":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB/s"


def format_eta(seconds: float) -> str:
    """Compact 'about 3m 20s' style estimate for the progress dock."""
    seconds = float(seconds or 0)
    if seconds <= 0:
        return "—"
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
