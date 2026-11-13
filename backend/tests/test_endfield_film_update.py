import hashlib
import io
import struct
import wave

import pytest

from backend import endfield_assets, endfield_film_update as films, endfield_film_voice, endfield_online
from backend import endfield_unity_timeline as unity


def _serialized_object(*, width=4, length=4):
    # Independent, synthetic v22 file with one typed object and one external reference.
    def pack(fmt, *values):
        return struct.pack('<' + fmt, *values)

    strings = b'MonoBehaviour\0Base\0m_FileID\0'
    nodes = b''.join(unity.NODE.pack(1, level, 0, kind, key, size, index, 0, 0)
                     for index, (level, kind, key, size) in enumerate([
                         (0, 0, 14, -1), (1, 0x80000000 | 222, 19, width)]))
    meta = bytearray(b'2022.3\0' + pack('iBi', 19, 1, 1) + pack('iBh', 114, 0, 0) + bytes(32))
    meta += pack('ii', 2, len(strings)) + nodes + strings + pack('ii', 0, 1)
    meta += bytes(-len(meta) % 4) + pack('qqIi', 135, 0, length, 0)
    meta += pack('ii', 0, 1) + b'\0' + bytes(20) + b'archive:/fixture\0' + pack('i', 0) + b'\0'
    start = 48 + len(meta)
    return struct.pack('>4I4sIqqq', 0, 0, 22, 0, bytes(4), len(meta), start + 4, start, 0) + meta + pack('i', 7)


def test_serialized_object_rejects_a_truncated_or_mistyped_publisher_pointer():
    assert unity.timeline_objects(_serialized_object()) == ({135: {'m_FileID': 7}}, {}, ('archive:/fixture',))
    for raw in (_serialized_object(width=8), _serialized_object(length=3), _serialized_object()[:-1]):
        with pytest.raises(ValueError):
            unity.timeline_objects(raw)


def _ptr(path, file=0):
    return {'m_PathID': path, 'm_FileID': file}


def test_localized_config_requires_the_exact_external_file_and_root_object(monkeypatch):
    film = 'fixture'
    cfg = films.FMV + 'singleconfigs/fixture.asset'
    track = films.FMV + 'fixture_others_au_en.playable'
    cab = 'CAB-' + '1' * 32
    path = f'archive:/{cab}/{cab}'
    reference = _ptr(123, 1)
    config = {'fmvId': film, 'config': {'audioLangKey2SubtitleTrack': {'_keys': [1], '_values': [reference]}}}
    objects = {123: {'m_Tracks': [_ptr(5)]}, 5: {'m_Clips': [
        {'m_Asset': _ptr(6), 'm_Start': 0, 'm_Duration': 2},
        {'m_Asset': _ptr(7), 'm_Start': 0, 'm_Duration': 2}]},
        6: {'_textId': 'line'}, 7: {'_audioEventKey': 'au_vo_fixture'}}
    files = {cfg: ('unused', 42, {42: config}, [path]), track: (cab, 123, objects, [])}
    monkeypatch.setattr(films, '_asset', lambda _, value, __: value)
    assert [r[0] for r in films._tracks(None, files, 'english', set())] == [film]
    reference['m_PathID'] += 1
    assert not list(films._tracks(None, files, 'english', set()))
    reference['m_PathID'] -= 1
    files[cfg][3][0] = path.replace('1', '2')
    assert not list(films._tracks(None, files, 'english', set()))
    assert not list(films._tracks(None, files, 'korean', set()))


def test_changed_film_excludes_overlapping_open_voice_and_recovers_saved_original(tmp_path, monkeypatch):
    # Existing audited clips use fixed clocks. An ongoing earlier event must also
    # participate in attribution when its published timeline clip has already ended.
    raw = b'released fixture'
    recorded = {(3, 'english'): raw, (4, 'english'): b'other'}
    events = {'au_vo_first': 3, 'au_vo_second': 4}
    def clip(ref, start, duration):
        return {'m_Asset': _ptr(ref), 'm_Start': start, 'm_Duration': duration}
    root = {'m_Tracks': [_ptr(1)]}
    objects = {1: {'m_Clips': [clip(2, 0, .5), clip(3, 1, 3),
                               clip(4, .1, .2), clip(5, 1.2, .3), clip(6, 2.5, .25)]},
               2: {'_audioEventKey': 'au_vo_first', '_stopEventAtClipEnd': 0, '_exitAudioEvent': {'_id': 0}},
               3: {'_audioEventKey': 'au_vo_second'}, 4: {'_textId': 'first'},
               5: {'_textId': 'ambiguous'}, 6: {'_textId': 'last'}}
    monkeypatch.setattr(films, '_files', lambda *args: {})
    def tracks(*args):
        clips = films.director.track_clips(objects, root)
        yield 'film', objects, root, {}, None, clips
    monkeypatch.setattr(films, '_tracks', tracks)
    monkeypatch.setattr(films.release, 'verified_films', lambda *args: set())
    monkeypatch.setattr(endfield_film_voice, 'recording_ids', lambda *args: events)
    monkeypatch.setattr(films, 'vgmstream_executable', lambda *_: 'decoder')
    def media(_, stamp, dub, media_id, digest=None):
        data = recorded[media_id, dub]
        assert digest is None or hashlib.sha256(data).hexdigest() == digest
        return data
    monkeypatch.setattr(films.release, 'media', media)
    def decode(_, __, media_id, data):
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setparams((1, 2, 1000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\x01\x00' * (2000 if media_id == 3 else 3000))
        stream.seek(0)
        return wave.open(stream)
    monkeypatch.setattr(films, '_decode', decode)
    stamp = films.release._stamp(b'{}')
    source = tmp_path / 'endfield-releases' / stamp
    source.parent.mkdir()
    source.write_bytes(b'{}')
    class Catalog:
        revision = stamp
        def file(self, _):
            return {'first': {'id': 1}, 'last': {'id': 2}}
        def verified_films(self, _):
            return set()
        def updated_cues(self, dub):
            return films.cues(tmp_path, self.revision, dub)
    catalog = Catalog()
    assert list(catalog.updated_cues('english')) == [('film', 'first'), ('film', 'last')]
    first, last = endfield_online.film_records(catalog, {'en': {'1': 'First.', '2': 'Last.'}}, 'en')
    assert (last['audio']['start_ms'], last['audio']['end_ms']) == (1500, 1750)
    films.cues.cache_clear()
    monkeypatch.setattr(films, '_build', lambda *args: pytest.fail('Saved export rebuilt the release'))
    assert endfield_assets.extract_voice(None, first['audio'], tmp_path / 'reader', None) == raw
    with pytest.raises(ValueError):
        endfield_assets.extract_voice(None, {**first['audio'], 'end_ms': 499}, tmp_path / 'reader', None)
