import hashlib
import io
import struct
import zlib

import pytest

from backend import endfield_alpha_archive as archive


def test_archive_acquisition_checks_ranges_package_and_recording_before_cache_reuse(tmp_path, monkeypatch):
    voice = b'RIFForiginal scene'
    media = 123
    package = (b'AKPK' + struct.pack('<6I', 56, 1, 4, 4, 24, 4) + bytes(8)
               + struct.pack('<6I', 1, media, 1, len(voice), 64, 1) + bytes(4) + voice)
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(package) + compressor.flush()
    digest = hashlib.sha256(package).hexdigest()
    descriptor = {'offset': 100, 'compressed': len(compressed), 'size': len(package), 'sha256': digest}
    monkeypatch.setattr(archive, 'PACKAGES', {'zh-Hans': descriptor})
    monkeypatch.setattr(archive, 'RECORDINGS', {
        'zh-Hans': {'film': (media, hashlib.sha256(voice).hexdigest())}})
    fetched = []

    class Response(io.BytesIO):
        status = 206
        headers = {'Content-Range': f'bytes 100-{99 + len(compressed)}/{archive.ARCHIVE_SIZE}'}

    def fetch(request, timeout):
        assert request.get_header('Range') == f'bytes=100-{99 + len(compressed)}'
        fetched.append(request.full_url)
        return Response(compressed)

    monkeypatch.setattr(archive.urllib.request, 'urlopen', fetch)
    record, actual = archive.recording(tmp_path, 'film', 'zh-Hant')
    assert actual == voice and record['locale'] == 'zh-Hans'
    assert archive.recording(tmp_path, 'film', 'zh-Hans')[1] == voice
    assert fetched == [archive.URL]
    destination = tmp_path / 'endfield-history' / (digest + '.pck')
    destination.write_bytes(b'?' * len(package))
    for changed in (compressed[:-1], compressed + b'!', zlib.compress(b'changed')):
        monkeypatch.setattr(archive.urllib.request, 'urlopen', lambda *a, **kw: Response(changed))
        with pytest.raises((ValueError, zlib.error)):
            archive.recording(tmp_path, 'film', 'zh-Hans')
        assert destination.read_bytes() == b'?' * len(package)
    monkeypatch.setattr(archive.urllib.request, 'urlopen', fetch)
    monkeypatch.setattr(Response, 'status', 200)
    with pytest.raises(ValueError, match='byte range'):
        archive.recording(tmp_path, 'film', 'zh-Hans')
    assert destination.read_bytes() == b'?' * len(package)
    monkeypatch.setattr(Response, 'status', 206)
    monkeypatch.setitem(archive.RECORDINGS['zh-Hans'], 'film', (media, '0' * 64))
    with pytest.raises(ValueError, match='performance'):
        archive.recording(tmp_path, 'film', 'zh-Hans')


def test_unknown_archive_language_or_film_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(archive.urllib.request, 'urlopen', lambda *a, **kw: pytest.fail('Downloaded unknown media'))
    assert archive.inventory('zh-Hant') == archive.inventory('zh-Hans')
    # Unverified archive languages must not borrow a verified scene's media.
    for locale, film in [('ja', 'fmv_e0m1_1'), ('en', '../other'), ('ko', 'timeline_e1m1_1')]:
        with pytest.raises(ValueError):
            archive.recording(tmp_path, film, locale)
