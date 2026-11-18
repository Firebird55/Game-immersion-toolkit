import hashlib
import struct
import wave

import pytest

from backend.game_data_protocol import GameDataError
from backend.zzz_wav_codec import PCM_CHUNK, WemFormat, ZzzWavCodec, inspect_wem


def wem(channels=2, rate=44100, frames=8201):
    # A framing fixture only. The payload here uses authored tokens so the
    # stream tests can inject declared PCM independently of the native codec.
    data = struct.pack('<H', 12) + b'fixture set!' + b'fixture packet'
    fmt = bytearray(66)
    struct.pack_into('<HHIIHHH', fmt, 0, 0xffff, channels, rate, 1, 0, 0, 48)
    struct.pack_into('<I', fmt, 24, frames)
    struct.pack_into('<II', fmt, 40, 0, 14)
    fmt[64:66] = bytes((8, 11))
    chunks = b'WAVEfmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
    return b'RIFF' + struct.pack('<I', len(chunks)) + chunks


class AuthoredPcm:
    def __init__(self, expected):
        self.format = expected
        self.calls = []
        self.remaining = expected.frames
        self.closed = False

    def read_frames(self, count):
        self.calls.append(count)
        size = min(self.remaining, count)
        self.remaining -= size
        return struct.pack('<h', 1234) * size * self.format.channels

    def close(self):
        self.closed = True


@pytest.mark.parametrize('channels,rate,frames', [(1,48000,4357), (2,44100,1775343)])
def test_original_sentence_and_whole_context_keep_source_samples(tmp_path, channels, rate, frames):
    raw = wem(channels, rate, frames)
    expected = WemFormat(channels, rate, frames)
    assert inspect_wem(raw) == expected
    opened = []

    def opener(value, format_):
        assert value is raw and format_ == expected
        stream = AuthoredPcm(format_)
        opened.append(stream)
        return stream

    audio = {'audio_scope':'context'} if channels == 2 else {'source':'owned authored line'}
    path = ZzzWavCodec('fixture', opener).resolve(raw, audio, tmp_path/'original', cancelled=lambda: False)
    assert path == tmp_path/'original.wav'
    assert opened[0].closed and max(opened[0].calls) == PCM_CHUNK and opened[0].calls[-1] == 1
    assert path.stat().st_size == 44 + frames * channels * 2
    with wave.open(str(path), 'rb') as reader:
        assert (reader.getnchannels(), reader.getframerate(), reader.getnframes()) == (channels,rate,frames)
        actual = hashlib.sha256(reader.readframes(frames)).hexdigest()
        assert actual == hashlib.sha256(struct.pack('<h',1234) * frames * channels).hexdigest()


@pytest.mark.parametrize('offset, replacement', [
    (0, b'RIFX'), (16, b'\x01'), (20,b'\x40\x30'), (22,b'\x03'), (36,b'\x31'), (44,b'\xff'*4),
    (60,b'\xff'*4), (64,b'\xff'*4), (84,b'\x00'), (86,b'LIST'), (90,b'\x00'*4), (94,b'\x00'),
])
def test_unsupported_or_invalid_carriers_never_enter_decoder(tmp_path, offset, replacement):
    raw = bytearray(wem())
    raw[offset:offset + len(replacement)] = replacement
    codec = ZzzWavCodec('fixture', lambda *args: pytest.fail('Malformed input reached native code'))
    with pytest.raises(GameDataError) as error:
        codec.resolve(bytes(raw), {}, tmp_path/'original', cancelled=lambda: False)
    assert error.value.code == 'zzz_original_audio_bounds' and not list(tmp_path.iterdir())


@pytest.mark.parametrize('mode', ['cancel', 'short', 'wrong-format', 'extra'])
def test_failed_decode_preserves_retained_wav(tmp_path, mode):
    raw = wem(frames=8201)
    expected = inspect_wem(raw)
    output = tmp_path/'original.wav'
    output.write_bytes(b'previous recording')
    pcm = AuthoredPcm(expected)
    original_read = pcm.read_frames

    def read(count):
        data = original_read(count)
        if mode == 'short' and len(pcm.calls) == 2:
            return data[:-2]
        if mode == 'extra' and not data:
            return b'\x00\x00'
        return data

    pcm.read_frames = read
    if mode == 'wrong-format':
        pcm.format = WemFormat(expected.channels, expected.rate, expected.frames + 1)
    with pytest.raises(GameDataError) as error:
        ZzzWavCodec('fixture', lambda *_: pcm).resolve(raw, {}, output, cancelled=lambda: mode == 'cancel' and len(pcm.calls) >= 2)
    assert error.value.code == ('recording_cancelled' if mode == 'cancel' else 'zzz_original_audio_bounds')
    assert pcm.closed and list(tmp_path.iterdir()) == [output] and output.read_bytes() == b'previous recording'


@pytest.mark.parametrize('audio', [
    {'start_ms':0, 'end_ms':1000}, {'gain_db':1}, {'gain_db':float('nan')}, {'channel_mix':[[1,0],[0,1]]},
])
def test_unverified_transforms_cannot_be_replaced_with_raw_audio(tmp_path, audio):
    codec = ZzzWavCodec('fixture', lambda *args: pytest.fail('Unverified transform reached native code'))
    with pytest.raises(GameDataError) as error:
        codec.resolve(wem(), audio, tmp_path/'unverified', cancelled=lambda: False)
    assert error.value.code == 'zzz_audio_transform_unavailable' and not list(tmp_path.iterdir())
