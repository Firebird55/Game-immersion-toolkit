"""Owned decoding never falls back to ambient tools or publishes cancelled audio."""
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace

import pytest

from backend import zzz_owned_audio as audio
from backend.game_data_protocol import GameDataError


def layout():return SimpleNamespace(mode='bundle', resources={}, child_environment=lambda: {})


def test_source_or_missing_packaged_codecs_never_try_path_or_a_process(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):raise AssertionError('Unowned audio process was started')
    monkeypatch.setattr(audio.subprocess, 'Popen', forbidden)
    assert audio.available_codecs(layout=SimpleNamespace(mode='source')) is None
    monkeypatch.setattr(audio, 'packaged_codec_executable', lambda *args, **kwargs: None)
    assert audio.available_codecs(layout=layout()) is None
    with pytest.raises(GameDataError) as failure:
        audio.OwnedCodecs(layout())._run('vgmstream', [], tmp_path, lambda: False)
    assert failure.value.code == 'zzz_audio_runtime_missing'


def test_cancelled_or_incomplete_source_cannot_replace_an_existing_recording(tmp_path, monkeypatch):
    codecs = audio.OwnedCodecs(layout());destination = tmp_path / 'retained.mp3';destination.write_bytes(b'previous recording')
    def forbidden(*args, **kwargs):raise AssertionError('Cancelled source reached a decoder')
    monkeypatch.setattr(codecs, '_run', forbidden)
    with pytest.raises(GameDataError):codecs.resolve(b'RIFF' + struct.pack('<I', 4) + b'WAVE', {}, destination, cancelled=lambda: True)
    with pytest.raises(GameDataError):codecs.resolve(b'RIFF' + struct.pack('<I', 40) + b'WAVE', {}, destination, cancelled=lambda: False)
    assert destination.read_bytes() == b'previous recording'


def test_cancellation_terminates_only_the_owned_child_and_keeps_output_unpublished(tmp_path, monkeypatch):
    stopped = [];cancel = [False]
    class Process:
        returncode = None
        def poll(self):return self.returncode
        def communicate(self, timeout):
            if self.returncode is not None:return b'', b''
            cancel[0] = True
            raise subprocess.TimeoutExpired('owned-tool', timeout)
        def terminate(self):stopped.append(True);self.returncode = -1
    monkeypatch.setattr(audio, 'packaged_codec_executable', lambda *args, **kwargs: tmp_path / 'owned-tool.exe')
    monkeypatch.setattr(audio.subprocess, 'Popen', lambda *args, **kwargs: Process())
    with pytest.raises(GameDataError) as failure:
        audio.OwnedCodecs(layout())._run('vgmstream', [], tmp_path, lambda: cancel[0])
    assert failure.value.code == 'recording_cancelled' and stopped == [True]
