"""Whole-film standard speaker evidence and complete six-channel presentation."""
import copy
import json
import struct
import subprocess
from types import SimpleNamespace
import wave

import numpy as np
import pytest

from backend import wuthering_assets as assets, wuthering_cinematics as films
from backend.local_voice import _audio_options
from backend.media_tools import ffmpeg_executable
from backend.tests.test_wuthering_context import assign, record, reference, scene_db


def source(*, channels=6, mask=0x60f, kind=1, codec=0x3041, version=1, mapping=1, frames=4096):
    fmt = bytearray(36)
    struct.pack_into('<HHI', fmt, 0, codec, channels, 48000)
    struct.pack_into('<H', fmt, 16, 18)
    struct.pack_into('<H', fmt, 18, 960)
    struct.pack_into('<IIIHBB', fmt, 20, mask << 12 | kind << 8 | channels, frames, 1, 312, version, mapping)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt
    body += b'seek' + struct.pack('<I', 2) + b'\x01\0'
    body += b'data' + struct.pack('<I', 1) + b'\0'
    return b'RIFF' + struct.pack('<I', len(body)) + body


def metadata(**changes):
    return {'sampleRate': 48000, 'channels': 6, 'numberOfSamples': 4096, 'playSamples': 4096,
        'channelLayout': 0x60f, 'mixingInfo': {'inputChannels': 6, 'outputChannels': 6},
        'streamInfo': {'total': 1, 'index': 0}, **changes}


def surround_reference():
    return {**reference(), 'source_frames': 4096, 'source_channels': 6,
        'source_channel_mask': 0x60f, 'channel_mix': films.standard_surround_mix()}


def test_only_explicit_standard_native_surround_and_preserved_decoder_mask_enable_whole_film(tmp_path, monkeypatch):
    monkeypatch.setattr(films.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=json.dumps(metadata()).encode()))
    assert films.source_info(source(), 'decoder', tmp_path) is None
    assert films.source_info(source(), 'decoder', tmp_path, film_context=True) == (6, 4096, 0x60f)
    scene_db(tmp_path)
    rows = [record()]
    assign(tmp_path, rows, shapes={101: (6, 4096, 0x60f)})
    assert rows[0]['audio_scope'] == 'context'
    assert rows[0]['audio']['channel_mix'] == films.standard_surround_mix()
    assets._validate_voice({**rows[0]['audio'], 'publisher': 'wuwa-' + 'a' * 64})


@pytest.mark.parametrize('changes', [{'channels': 2}, {'mask': 0}, {'mask': 0x3f}, {'mask': 0x800},
    {'kind': 0}, {'kind': 2}, {'kind': 3}, {'codec': 0xffff}, {'version': 2}, {'mapping': 0}, {'frames': 0}])
def test_ambisonic_unknown_haptic_or_unmapped_six_channel_sources_never_gain_speaker_ownership(changes):
    assert films._standard_surround_source(source(**changes)) is None


@pytest.mark.parametrize('changes', [{'channelLayout': 0}, {'channelLayout': 0x3f}, {'channelLayout': True},
    {'channelLayout': None}, {'numberOfSamples': 4095}, {'playSamples': 4095},
    {'channels': 2, 'channelLayout': 3, 'mixingInfo': {'inputChannels': 2, 'outputChannels': 2}},
    {'mixingInfo': {'inputChannels': 6, 'outputChannels': 2}}, {'streamInfo': {'total': 2, 'index': 0}}])
def test_native_layout_cannot_override_mismatching_decoded_channels_frames_or_subsongs(changes, tmp_path, monkeypatch):
    monkeypatch.setattr(films.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=json.dumps(metadata(**changes)).encode()))
    assert films.source_info(source(), 'decoder', tmp_path, film_context=True) is None


@pytest.mark.parametrize('damage', ['truncated', 'extra', 'duplicate', 'seek', 'config_count', 'size', 'rate'])
def test_complete_container_and_exact_declared_channel_configuration_are_required(damage):
    data = bytearray(source())
    if damage == 'truncated':
        data = data[:-1]
    elif damage == 'extra':
        data += b'junk'
    elif damage == 'duplicate':
        data += data[12:56]
        struct.pack_into('<I', data, 4, len(data) - 8)
    elif damage == 'seek':
        struct.pack_into('<I', data, 20 + 28, 2)
    elif damage == 'config_count':
        data[20 + 20] = 5
    elif damage == 'size':
        struct.pack_into('<I', data, 16, 35)
    elif damage == 'rate':
        struct.pack_into('<I', data, 24, 44100)
    assert films._standard_surround_source(data) is None


@pytest.mark.parametrize('changes', [{'music_context': True}, {'source_channel_mask': 0x3f},
    {'source_channel_mask': True}, {'source_channels': 2}, {'start_ms': 0, 'end_ms': 40},
    {'channel_mix': [[1, 0]] * 6}, {'scene_context': False}])
def test_surround_cannot_authorize_song_interval_unknown_layout_or_arbitrary_mix(changes):
    with pytest.raises(ValueError):
        assets._validate_voice({**surround_reference(), **changes})


def test_boolean_coefficients_and_unproven_shape_tuples_do_not_pass_exact_mix_contract(tmp_path):
    invalid = surround_reference()
    invalid['channel_mix'][0][1] = False
    with pytest.raises(ValueError):
        assets._validate_voice(invalid)
    scene_db(tmp_path)
    for shape in [(6, 4096), (6, 4096, 0), (6, 4096, True), (2, 4096, 0x60f), (6, 4096, 0x60f, 0)]:
        rows = [record()]
        assign(tmp_path, rows, shapes={101: shape})
        assert rows[0]['audio'] is None


def test_extraction_rechecks_original_mask_and_decoder_then_preserves_every_frame(tmp_path, monkeypatch):
    calls = []
    def decode(command, **options):
        calls.append(command)
        if '-m' in command:
            return SimpleNamespace(stdout=json.dumps(metadata()).encode())
        with wave.open(str(command[3]), 'wb') as output:
            output.setparams((6, 2, 48000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\x10\0' * 4096 * 6)
    monkeypatch.setattr(assets.subprocess, 'run', decode)
    wav = tmp_path / 'full.wav'
    assert assets.decode_voice_source(source(), surround_reference(), wav, 'decoder', tmp_path) is None
    assert len(calls) == 2
    with wave.open(str(wav)) as output:
        assert (output.getnframes(), output.getnchannels()) == (4096, 6)
        assert len(output.readframes(4096)) == 4096 * 6 * 2
    calls.clear()
    with pytest.raises(ValueError, match='verified source'):
        assets.decode_voice_source(source(mask=0x3f), surround_reference(), wav, 'decoder', tmp_path)
    assert len(calls) == 1  # A mismatching original never reaches full decoding.


@pytest.mark.parametrize('signal', ['impulses', 'frequencies', 'peak'])
def test_actual_shared_export_filter_retains_speaker_order_frames_and_headroom(signal, tmp_path):
    executable = ffmpeg_executable()
    if not executable:
        pytest.skip('The original export codec is unavailable in this runtime')
    count = 4096
    original = np.zeros((count, 6), dtype='<i2')
    bins = [31, 59, 83, 113, 149, 181]
    if signal == 'impulses':
        for channel in range(6):
            original[100 * (channel + 1), channel] = 12000
    elif signal == 'frequencies':
        original[:] = np.rint(1000 * np.sin(2 * np.pi * np.arange(count)[:, None] * np.array(bins) / count))
    else:
        original[:] = 32767
    source_wav, output_wav = tmp_path / 'six.wav', tmp_path / 'stereo.wav'
    with wave.open(str(source_wav), 'wb') as output:
        output.setparams((6, 2, 48000, 0, 'NONE', 'not compressed'))
        output.writeframes(original.tobytes())
    audio = surround_reference()
    untouched = copy.deepcopy(audio)
    options = _audio_options(audio, source_wav)
    assert '-ss' not in options and '-t' not in options and '-ac' not in options
    subprocess.run([executable, '-v', 'error', '-y', '-i', str(source_wav), *options,
        '-c:a', 'pcm_s16le', str(output_wav)], check=True, capture_output=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    with wave.open(str(output_wav)) as output:
        assert (output.getnframes(), output.getnchannels(), output.getframerate()) == (count, 2, 48000)
        result = np.frombuffer(output.readframes(count), dtype='<i2').reshape(count, 2)
    assert audio == untouched
    matrix = np.asarray(films.standard_surround_mix())
    # Integer swresample builds can quantize each of four nonzero coefficients
    # per output to Q15, plus PCM rounding: at full scale this is at most five
    # PCM units. Quiet impulses/tones retain the tighter sample-level bound.
    tolerance = 5 if signal == 'peak' else 1.1
    assert np.max(np.abs(result.astype(float) - original.astype(float) @ matrix)) <= tolerance
    assert all(pair.any() for pair in matrix) and all(matrix[:, side].sum() < 1 for side in (0, 1))
    if signal == 'frequencies':
        amplitudes = np.abs(np.fft.rfft(result, axis=0))[bins] * 2 / count
        assert np.max(np.abs(amplitudes - matrix * 1000)) < 1
    if signal == 'peak':
        assert 0 < result.max() < 32767
