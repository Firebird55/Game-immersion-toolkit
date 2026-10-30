"""Shared codec discovery for source installations and immutable desktop bundles."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import shutil
import sys

from .native_codecs import packaged_codec_executable


def vgmstream_executable(root: Path | None = None) -> Path | None:
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    if layout.mode == 'bundle':
        return packaged_codec_executable('vgmstream', layout=layout)
    from .runtime_paths import data_root as runtime_data_root
    base = Path(root) if root is not None else layout.application_root
    folder = runtime_data_root(base) / 'voice-assets/vgmstream'
    binary = folder / ('vgmstream-cli.exe' if sys.platform == 'win32' else 'vgmstream-cli')
    return binary if binary.is_file() else None


def experimental_flac_decoder(*, layout=None):
    """Explicit bounded codec experiment; never the general FFmpeg game adapter."""
    from .prebuilt_codecs import prebuilt_flac_decoder
    return prebuilt_flac_decoder(layout=layout)


@lru_cache(maxsize=1)
def ffmpeg_executable() -> str | None:
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    if layout.mode == 'bundle':
        binary = packaged_codec_executable('ffmpeg', layout=layout)
        return str(binary) if binary else None
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None
