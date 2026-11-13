import hashlib
import io
import json

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
    original[film.FILM + '_12'] = {'subtitleText': {'text': 'Omitted in the video'}}
    data = json.dumps(original).encode()
    monkeypatch.setattr(film, 'TEXT_SHA256', hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(film, 'TEXT_SIZE', len(data))
    monkeypatch.setattr(film, 'download', lambda *a, **kw: data)
    rows = film.lines(tmp_path)
    monkeypatch.setattr(film, 'download', lambda *a, **kw: pytest.fail('Re-fetched the same transcript'))
    assert film.lines(tmp_path) == rows
    assert len(rows) == 21 and film.FILM + '_12' not in rows
    assert rows[film.FILM + '_09-2']['end_ms'] == rows[film.FILM + '_09-3']['start_ms']
    with pytest.raises(ValueError, match='Unknown'):
        film.export(tmp_path, film.FILM + '_12', tmp_path / 'unused.mp3')
