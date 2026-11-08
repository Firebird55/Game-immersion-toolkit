import hashlib
import io
import struct

import pytest

from backend import endfield_online as online
from backend.endfield_vfs import Parameters
from backend.voice_assets import voice_hash
from scripts.import_endfield_timelines import DUBS, import_clocks, track_clips


def test_verified_publisher_ranges_and_cached_cinematic(tmp_path, monkeypatch):
    source = 'voice/english/dialogue/owned.wem'
    identity = voice_hash(source)
    wem = b'RIFF' + struct.pack('<I', 8) + b'WAVEtest'
    sector = struct.pack('<IQIIII', 1, identity, 1, len(wem), 56, 0)
    header = b'AKPK' + struct.pack('<6I', 48, 1, 0, 0, 0, len(sector)) + sector
    assert len(header) == 56
    chunk = b'prefix' + header + wem
    sha = lambda data: hashlib.sha256(data).hexdigest()
    spec = ('VFS/owned.chk', len(chunk), 6, len(header + wem), len(header), sha(header))
    monkeypatch.setattr(online.profile, 'PACKAGES', {'english': [spec]})
    monkeypatch.setattr(online.profile, 'FILMS', {'owned': ((0, ''), (identity, sha(wem)))})
    monkeypatch.setattr(online.profile, 'CUES', {('owned', 'subtitle'): (0, 1, 15, 42)})
    monkeypatch.setattr(online.endfield_metadata, 'parameters', lambda _: Parameters(
        bytes(32), {k: f'{k:08X}' for k in (1, 21, 101, 102, 103, 104)}, 5, 7))
    calls = []
    def ranges(path, total, offset, length):
        assert path == spec[0] and total == len(chunk)
        calls.append((offset, length))
        return chunk[offset:offset + length]
    monkeypatch.setattr(online, '_read_range', ranges)
    refs = online.voice_entries(tmp_path, 'en')
    assert calls == [(6, len(header))]
    ref = {**refs[f'{identity:016x}'], 'source': source, 'locale': 'en'}
    assert online.extract(ref, tmp_path) == wem
    film = online._film_audio('owned', 'subtitle', 'en')
    assert online.extract(film, tmp_path) == wem
    assert calls[1:] == [(62, len(wem))] * 2
    with pytest.raises(ValueError):
        online.extract({**film, 'end_ms': 99}, tmp_path)
    with pytest.raises(ValueError):
        online.extract({**ref, 'locale': 'ja'}, tmp_path)
    online._inventory.cache_clear()
    monkeypatch.setattr(online, '_read_range', lambda *args: pytest.fail('Offline replay requested the network'))
    assert online.extract(film, tmp_path) == wem
    (tmp_path / 'endfield-publisher' / 'speech' / sha(wem)).write_bytes(b'corrupt')
    monkeypatch.setattr(online, '_read_range', lambda *args: b'X' * args[-1])
    with pytest.raises(ValueError):
        online.extract(film, tmp_path)


@pytest.mark.parametrize('status,content_range,body', [
    (200, 'bytes 3-6/20', b'abcd'), (206, 'bytes 2-5/20', b'abcd'),
    (206, 'bytes 3-6/21', b'abcd'), (206, 'bytes 3-6/20', b'abc'),
    (206, 'bytes 3-6/20', b'abcde')])
def test_ranges_refuse_full_shifted_or_truncated_body(monkeypatch, status, content_range, body):
    response = io.BytesIO(body)
    response.status = status
    response.geturl = lambda: online.CDN + 'file'
    response.headers = {'Content-Range': content_range}
    monkeypatch.setattr(online.urllib.request, 'urlopen', lambda *_args, **_kwargs: response)
    with pytest.raises(ValueError):
        online._read_range('file', 20, 3, 4)


def test_unity_tracks_preserve_source_clock_and_skip_muted_or_foreign_objects():
    def pointer(key):
        return {'m_FileID': 0, 'm_PathID': key}
    def clip(key, start, duration):
        return {'m_Asset': pointer(key), 'm_Start': start, 'm_Duration': duration}
    root = {'m_Tracks': [pointer(1), pointer(2), {'m_FileID': 1, 'm_PathID': 2}]}
    track = {'m_Clips': [clip(3, 12.5, 2), clip(4, .25, 30)]}
    objects = {1: track, 2: {**track, 'm_Muted': True}, 3: {'_textId': 'owned'},
               4: {'_audioEventKey': 'au_vo_owned'}}
    assert track_clips(objects, root) == ([('owned', 12.5, 14.5)], [('au_vo_owned', .25, 30.25)])
    track['m_Clips'][1]['m_TimeScale'] = 2
    assert track_clips(objects, root) is None


def test_only_the_dub_with_verified_speech_can_prepare_a_cue(monkeypatch):
    key = ('opening', 'caption')
    row = {'film': key[0], 'caption': key[1], 'locales': {
        'jp': (1.5, 2, 'au_vo_opening', .25, True)}}
    pcm = {dub: [[key] if dub == 'jp' else []] for dub in DUBS}
    packages = {dub: ([], {}) for dub in DUBS}
    packages['jp'][1]['opening'] = (123, 'digest', 'au_vo_opening', 1743 * 48, 48000)
    _, films, cues = import_clocks([row], packages, pcm)
    monkeypatch.setattr(online.profile, 'FILMS', films)
    monkeypatch.setattr(online.profile, 'CUES', cues)

    class Catalog:
        revision = online.TEXT_REVISION

        def file(self, _):
            return {'caption': {'id': 7}}

    tables = {'en': {'7': 'English fixture'}, 'ja': {'7': 'Japanese fixture'}}
    assert online.film_records(Catalog(), tables, 'en') == []
    [record] = online.film_records(Catalog(), tables, 'ja')
    assert record['audio']['start_ms'] == 1250 and record['audio']['end_ms'] == 1743
    with pytest.raises(ValueError):
        online.extract({**record['audio'], 'locale': 'en'}, None)
    packages['jp'][1]['opening'] = (123, 'digest', 'au_vo_unrelated', 48000, 48000)
    with pytest.raises(ValueError, match='event'):
        import_clocks([row], packages, pcm)
    packages['jp'][1]['opening'] = (123, 'digest', 'au_vo_opening', 48000, 48000)
    with pytest.raises(ValueError, match='no interval'):
        import_clocks([row], packages, pcm)
