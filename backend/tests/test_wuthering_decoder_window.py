"""Window/source confusion and incomplete decoder output must never yield PCM.

Existing film matching tests do not exercise the decoder subprocess boundary.
Real owned long-source and publisher-source checks complement these fault cases.
"""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import wave

import pytest

from backend import wuthering_cinematics as films


def decoder(monkeypatch, *, metadata=None, output=None, fail=None):
    info = {'sampleRate': 48000, 'channels': 2, 'numberOfSamples': 301 * 48000,
            'playSamples': 301 * 48000, 'mixingInfo': {'inputChannels': 2, 'outputChannels': 2},
            'streamInfo': {'index': 0, 'total': 1}}
    info.update(metadata or {})
    calls = []

    def run(command, **options):
        calls.append(command)
        assert options['check'] and options['capture_output'] and 0 < options['timeout'] <= 45
        assert Path(command[-1]).parent.name.startswith('wuwa-window-')
        if fail == len(calls):
            raise subprocess.TimeoutExpired(command, options['timeout'])
        if '-m' in command:
            assert command[1:4] == ['-m', '-I', '-i']
            assert Path(command[-1]).name == 'source.wem'
            assert Path(command[-1]).read_bytes() == b'owned-source'
            return SimpleNamespace(stdout=json.dumps(info).encode())
        assert command[1:4] == ['-W', '1', '-o']
        assert Path(command[-1]).name == 'window.txtp'
        assert Path(command[-1]).read_text() == 'source.wem #i #t 14400144 #r 14400048\n'
        path = Path(command[-2])
        if output:
            output(path)
        else:
            write_pcm(path)
        return SimpleNamespace(stdout=b'')

    monkeypatch.setattr(films.subprocess, 'run', run)
    return calls


def write_pcm(path, *, rate=48000, channels=2, width=2, frames=96):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((channels, width, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\x01\x00' * (frames * channels * width // 2))


@pytest.mark.parametrize('streams', [0, 1])
def test_long_source_can_yield_short_pcm_at_an_explicit_late_origin(tmp_path, monkeypatch, streams):
    calls = decoder(monkeypatch, metadata={'streamInfo': {'index': 0, 'total': streams}})
    result = films.decode_window(b'owned-source', 'decoder', tmp_path, 300001, 300003)
    assert result == films.PcmWindow(300001, 2, b'\x01\x00' * 192)
    assert len(calls) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('start,end', [(-1, 1), (2, 1), (1, 1), (0, 300001),
                                       (False, 1), (0, True), (0., 1), (0, 1.),
                                       ('0', 1), (0, None)])
def test_invalid_or_oversized_window_never_starts_a_decoder(tmp_path, monkeypatch, start, end):
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid window reached the decoder')
    monkeypatch.setattr(films.subprocess, 'run', unexpected)
    assert films.decode_window(b'owned-source', 'decoder', tmp_path, start, end) is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('metadata', [
    {'numberOfSamples': 300 * 48000}, {'numberOfSamples': True}, {'numberOfSamples': 2**63},
    {'numberOfSamples': 0}, {'sampleRate': 44100}, {'channels': True},
    {'playSamples': 301 * 48000 + 1}, {'playSamples': float(301 * 48000)},
    {'mixingInfo': {'inputChannels': 2, 'outputChannels': 1}},
    {'mixingInfo': {'inputChannels': 2., 'outputChannels': 2}},
    {'streamInfo': {'index': 0, 'total': 2}}, {'streamInfo': {'index': 1, 'total': 1}},
])
def test_source_overrun_or_ambiguous_metadata_never_starts_decode(tmp_path, monkeypatch, metadata):
    calls = decoder(monkeypatch, metadata=metadata)
    assert films.decode_window(b'owned-source', 'decoder', tmp_path, 300001, 300003) is None
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('change', [{'frames': 95}, {'frames': 97}, {'rate': 44100},
                                    {'channels': 1}, {'width': 1}, {'width': 4}])
def test_wrong_output_duration_or_format_does_not_return_pcm(tmp_path, monkeypatch, change):
    decoder(monkeypatch, output=lambda path: write_pcm(path, **change))
    assert films.decode_window(b'owned-source', 'decoder', tmp_path, 300001, 300003) is None
    assert list(tmp_path.iterdir()) == []


def test_truncated_output_is_rejected_even_with_the_expected_wav_frame_header(tmp_path, monkeypatch):
    def truncated(path):
        write_pcm(path)
        path.write_bytes(path.read_bytes()[:-2])
    decoder(monkeypatch, output=truncated)
    assert films.decode_window(b'owned-source', 'decoder', tmp_path, 300001, 300003) is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('payload', [b'not JSON', b'[]', b'null'])
def test_unreadable_source_metadata_does_not_authorize_a_window(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(films.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=payload))
    assert films.decode_window(b'owned-source', 'decoder', tmp_path, 300001, 300003) is None
    assert list(tmp_path.iterdir()) == []


def test_metadata_and_decode_share_one_deadline(tmp_path, monkeypatch):
    calls = decoder(monkeypatch)
    clock = iter([0, 1, 46])
    monkeypatch.setattr(films.time, 'monotonic', lambda: next(clock))
    assert films.decode_window(b'owned-source', 'decoder', tmp_path, 300001, 300003) is None
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('stage', [1, 2])
def test_metadata_or_decode_timeout_removes_owned_partial_files(tmp_path, monkeypatch, stage):
    calls = decoder(monkeypatch, fail=stage)
    assert films.decode_window(b'owned-source', 'decoder', tmp_path, 300001, 300003) is None
    assert len(calls) == stage
    assert list(tmp_path.iterdir()) == []
