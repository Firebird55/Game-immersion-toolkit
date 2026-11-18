"""Attest the installed Android Wwise PCM capability before using original data."""

import json
import re

from .game_data_protocol import GameDataError
from .zzz_wav_codec import MAX_WEM, PCM_CHUNK, ZzzWavCodec

SCHEMA = 'toolkit-zzz-wem-pcm-v1'
SOURCES = {
    'vgmstream-r2168-source.tar.gz': 'e74334a13007655b5812af1f4b5880dbb11516dfc0a114d3cffe2dd09dc4fe1b',
    'libvorbis-1.3.7.tar.xz': 'b33cc4934322bcbf6efcbacf49e3ca01aadbea4114ec9589d1b1e9d20f72954b',
    'libogg-1.3.5.tar.xz': 'c4d91be36fc8e54deae7575241e03f4211eb102afb3fc0775fbbc1b740016705',
}


def _missing():
    return GameDataError('zzz_audio_runtime_missing', 'The verified Android ZZZ audio decoder is unavailable. Repair the app runtime.', 409)


def _failure():
    return GameDataError('zzz_audio_decode_failed', 'This original recording could not be decoded. Previous recordings are kept.', 409)


class _PcmTicket:
    def __init__(self, ticket, format_):
        self._ticket = ticket
        self.format = format_

    def read_frames(self, count):
        try:
            value = self._ticket.readFrames(count)
            if value is None or len(value) > count * self.format.channels * 2:
                raise ValueError('The PCM pull exceeded its expected extent')
            try:
                return bytes(value)
            except ValueError:
                return bytes(int(sample_byte) & 255 for sample_byte in value)
        except Exception:
            raise _failure() from None

    def close(self):
        self._ticket.close()


def create_android_zzz_codecs(native):
    """Use the installed app's concrete verified Java type. No codecs are fetched."""
    try:
        from java import jclass
        worker = native.zzzWemCodec()
        if not isinstance(worker, jclass('io.github.firebird55.gameimmersiontoolkit.ZzzWemCodec')):
            raise ValueError('Unverified ZZZ WEM decoder type')
        raw = str(worker.proof())
        if not 0 < len(raw) <= 16384:
            raise ValueError('Invalid ZZZ WEM decoder proof bounds')
        proof = json.loads(raw)
        if (proof.get('schema') != SCHEMA or proof.get('abi') not in ('arm64-v8a', 'x86_64')
                or proof.get('source_sha256') != SOURCES or proof.get('max_wem_bytes') != MAX_WEM
                or proof.get('max_frames_per_read') != PCM_CHUNK or proof.get('apk_entry_verified') is not True
                or proof.get('notices_verified') is not True or proof.get('system_fallback') is not False):
            raise ValueError('Unverified ZZZ WEM decoder proof')
        for name in ('library_sha256', 'manifest_sha256'):
            if not re.fullmatch('[0-9a-f]{64}', proof[name]):
                raise ValueError('Unverified ZZZ WEM decoder identity')
    except Exception:
        raise _missing() from None

    def open_stream(raw, format_):
        try:
            ticket = worker.begin(raw, format_.channels, format_.rate, format_.frames)
            if ticket is None:
                raise ValueError('No native PCM ticket')
            return _PcmTicket(ticket, format_)
        except Exception:
            raise _failure() from None

    return ZzzWavCodec(SCHEMA + ':' + proof['manifest_sha256'], open_stream)
