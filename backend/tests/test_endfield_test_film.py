import hashlib
import io
import json
from pathlib import Path
import subprocess

import pytest

from backend import endfield_test_film as film


def test_test_film_validates_download_and_cache_before_reusing_the_recording(tmp_path, monkeypatch):
    source = b'original film'
    monkeypatch.setattr(film, 'SIZE', len(source))
    monkeypatch.setattr(film, 'SHA256', hashlib.sha256(source).hexdigest())
    fetched = []
    def download(url, timeout):
        fetched.append(url)
        return io.BytesIO(source)
    monkeypatch.setattr(film.urllib.request, 'urlopen', download)
    path = film._movie(tmp_path)
    assert path.read_bytes() == source
    assert film._movie(tmp_path) == path
    assert fetched == [film.VIDEO]
    path.write_bytes(b'?' * len(source))
    for changed in (b'!' * len(source), source[:-2], source + b'!'):
        monkeypatch.setattr(film.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(changed))
        with pytest.raises(ValueError):
            film._movie(tmp_path)
        assert path.read_bytes() == b'?' * len(source)


def test_test_film_transcript_only_includes_the_verified_performance(tmp_path, monkeypatch):
    original = {f'{film.FILM}_{suffix}': {'subtitleText': {'text': 'Test line'}} for suffix in film.CUTS}
    original.update({key: {'subtitleText': {'text': 'Archive line'}} for key in film.ARCHIVE_CUTS})
    original[film.FILM + '_12'] = {'subtitleText': {'text': 'Omitted in the video'}}
    original['timeline_e1m1_1_02'] = {'subtitleText': {'text': 'Unverified spoken boundary'}}
    data = json.dumps(original).encode()
    monkeypatch.setattr(film, 'TEXT_SHA256', hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(film, 'TEXT_SIZE', len(data))
    monkeypatch.setattr(film, 'download', lambda *a, **kw: data)
    rows = film.lines(tmp_path)
    monkeypatch.setattr(film, 'download', lambda *a, **kw: pytest.fail('Re-fetched the same transcript'))
    assert film.lines(tmp_path) == rows
    assert len(rows) == 47 and film.FILM + '_12' not in rows
    assert rows['fmv_e0m1_3_01'] == {'text': 'Archive line', 'start_ms': 55400, 'end_ms': 58200}
    assert rows['fmv_e0m1_3_02'] == {'text': 'Archive line', 'start_ms': 61700, 'end_ms': 62550}
    assert rows['fmv_e0m1_1_04']['end_ms'] == rows['fmv_e0m1_1_05']['start_ms']
    assert 'fmv_e0m1_3_20' not in rows
    assert 'timeline_e1m1_1_02' not in rows
    assert rows['fmv_e0m1_3_05-1']['end_ms'] == rows['fmv_e0m1_3_05-2']['start_ms']
    assert rows[film.FILM + '_09-2']['end_ms'] == rows[film.FILM + '_09-3']['start_ms']
    with pytest.raises(ValueError, match='Unknown'):
        film.export(tmp_path, film.FILM + '_12', tmp_path / 'unused.mp3')
    with pytest.raises(ValueError, match='Unknown'):
        film.export(tmp_path, 'fmv_e0m1_3_20', tmp_path / 'unused.mp3')
    with pytest.raises(ValueError, match='Unknown'):
        film.export(tmp_path, 'timeline_e1m1_1_02', tmp_path / 'unused.mp3')


@pytest.mark.parametrize('caption,expected_film,start,end', [
    ('fmv_e0m1_3_02', 'fmv_e0m1_3', 61700, 62550),
    ('fmv_e0m1_1_02', 'fmv_e0m1_1', 5250, 11900),
    ('timeline_e1m1_1_03', 'timeline_e1m1_1', 18700, 22400),
])
def test_archive_export_uses_its_own_recording_and_retains_destination_on_decode_failure(
        tmp_path, monkeypatch, caption, expected_film, start, end):
    row = {'text': 'Original caption', 'start_ms': start, 'end_ms': end}
    monkeypatch.setattr(film, 'lines', lambda cache: {caption: row})
    monkeypatch.setattr(film, 'ffmpeg_executable', lambda: 'ffmpeg')
    monkeypatch.setattr(film, 'vgmstream_executable', lambda: Path('vgmstream'))
    monkeypatch.setattr(film, '_movie', lambda cache: pytest.fail('Used the briefing soundtrack'))
    requests = []
    def recording(cache, movie, locale):
        requests.append((movie, locale))
        return {}, b'RIFForiginal scene recording'
    monkeypatch.setattr(film.endfield_alpha_archive, 'recording', recording)
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        if command[0] == 'vgmstream':
            assert '-i' in command  # The WEM's loop marker must not repeat the scene.
            assert Path(command[-1]).read_bytes() == b'RIFForiginal scene recording'
            Path(command[2]).write_bytes(b'decoded original')
        else:
            assert command[command.index('-ss') + 1] == str(start / 1000)
            assert command[command.index('-t') + 1] == str((end - start) / 1000)
            Path(command[-1]).write_bytes(b'encoded clip' * 20)
    monkeypatch.setattr(film.subprocess, 'run', run)
    destination = tmp_path / 'caption.mp3'
    assert film.export(tmp_path, caption, destination) == row
    assert requests == [(expected_film, 'zh-Hans')]
    assert len(commands) == 2
    original = destination.read_bytes()
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'vgmstream')
    monkeypatch.setattr(film.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        film.export(tmp_path, caption, destination)
    assert destination.read_bytes() == original
