"""Locate the FFmpeg binary installed with the local Python environment."""

from __future__ import annotations

from functools import lru_cache
import shutil


@lru_cache(maxsize=1)
def ffmpeg_executable() -> str | None:
    from .runtime_bundle import discover_layout
    if discover_layout().mode == 'bundle':
        # No PATH/developer-wheel binary can mask the unresolved F1 gate.
        return None
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None
