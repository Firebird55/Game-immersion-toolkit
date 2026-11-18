"""Bounded PCM handoff for verified original ZZZ Wwise Vorbis recordings."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import struct
import tempfile
import time
from typing import Protocol
import wave

from .game_data_protocol import GameDataError
from .private_data_paths import MAX_AUDIO, _no_links

MAX_WEM = 64 * 1024 * 1024
PCM_CHUNK = 4096
DECODE_SECONDS = 120


@dataclass(frozen=True)
class WemFormat:
    channels: int
    rate: int
    frames: int


class PcmStream(Protocol):
    """A scoped native decoder which returns interleaved PCM16 little endian."""

    format: WemFormat

    def read_frames(self, count: int) -> bytes: ...
    def close(self) -> None: ...


def _invalid():
    return GameDataError('zzz_original_audio_bounds', 'The complete original recording has an unsupported Wwise format.', 409)


def inspect_wem(raw: bytes) -> WemFormat:
    # The admitted layout is the observed Wwise >= v56 little-endian format:
    # complete RIFF, one 66-byte WAVEFORMATEX, then one original data chunk.
    # Wwise RIFF chunks here have no trailing alignment byte.
    if (not isinstance(raw, bytes) or not 99 <= len(raw) <= MAX_WEM
            or raw[:4] != b'RIFF' or raw[8:16] != b'WAVEfmt ' or raw[86:90] != b'data'
            or struct.unpack_from('<I', raw, 4)[0] + 8 != len(raw)
            or struct.unpack_from('<I', raw, 16)[0] != 66):
        raise _invalid()
    tag, channels, rate, _, alignment, bits, extra = struct.unpack_from('<HHIIHHH', raw, 20)
    if (tag != 0xffff or channels not in (1, 2) or not 8000 <= rate <= 96000
            or alignment != 0 or bits != 0 or extra != 0x30):
        raise _invalid()
    frames = struct.unpack_from('<I', raw, 44)[0]
    seek_bytes, audio_at = struct.unpack_from('<II', raw, 60)
    short_block, long_block = raw[84:86]
    data_bytes = struct.unpack_from('<I', raw, 90)[0]
    if (data_bytes != len(raw) - 94 or not 0 <= seek_bytes <= audio_at - 2 <= data_bytes - 5
            or seek_bytes % 4 or not 6 <= short_block <= long_block <= 13
            or not 0 < frames <= (MAX_AUDIO - 44) // (channels * 2)):
        raise _invalid()
    setup_bytes = struct.unpack_from('<H', raw, 94 + seek_bytes)[0]
    if not setup_bytes or seek_bytes + 2 + setup_bytes != audio_at:
        raise _invalid()
    return WemFormat(channels, rate, frames)


def _unsupported_transform(audio):
    return ('start_ms' in audio or 'end_ms' in audio or audio.get('channel_mix') is not None
            or type(audio.get('gain_db', 0)) not in (int, float) or audio.get('gain_db', 0) != 0)


class ZzzWavCodec:
    """The verified engine supplies PCM; the app owns local publication."""

    def __init__(self, identity: str, open_stream: Callable[[bytes, WemFormat], PcmStream]):
        self.identity = identity
        self._open_stream = open_stream

    def resolve(self, raw: bytes, audio: Mapping, destination: Path, *, cancelled: Callable[[], bool]) -> Path:
        deadline = time.monotonic() + DECODE_SECONDS

        def check():
            if cancelled():
                raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
            if time.monotonic() > deadline:
                raise GameDataError('zzz_audio_decode_timeout', 'This original recording took too long to decode. Retry.', 409)

        check()
        original = inspect_wem(raw)
        # The current sentence and whole-context sources both have unchanged
        # samples. Timed, gained or remixed bindings need their own verified path.
        if not isinstance(audio, Mapping) or _unsupported_transform(audio):
            raise GameDataError('zzz_audio_transform_unavailable', 'This original recording needs an unavailable audio transform.', 409)
        destination = Path(destination).absolute().with_suffix('.wav')
        _no_links(destination)
        if not destination.parent.is_dir():
            raise ValueError('A private staging directory is required')
        with tempfile.TemporaryDirectory(prefix='zzz-wav-', dir=destination.parent) as temporary:
            pending = Path(temporary) / 'audio.wav'
            check()
            pcm = self._open_stream(raw, original)
            try:
                check()
                if pcm.format != original:
                    raise _invalid()
                with wave.open(str(pending), 'wb') as wav:
                    wav.setparams((original.channels, 2, original.rate, original.frames, 'NONE', 'not compressed'))
                    remaining = original.frames
                    while remaining:
                        check()
                        count = min(PCM_CHUNK, remaining)
                        chunk = pcm.read_frames(count)
                        check()
                        if not isinstance(chunk, bytes) or len(chunk) != count * original.channels * 2:
                            raise _invalid()
                        wav.writeframesraw(chunk)
                        remaining -= count
                    if pcm.read_frames(1) != b'':
                        raise _invalid()
                    check()
            finally:
                pcm.close()
            if pending.stat().st_size != 44 + original.frames * original.channels * 2:
                raise _invalid()
            check()
            _no_links(destination)
            os.replace(pending, destination)
        return destination
