import hashlib
import io
import struct
import wave

import pytest

from backend import endfield_assets, endfield_film_update as films, endfield_film_voice, endfield_online
from backend import endfield_unity_timeline as unity
from backend import endfield_scene_update as scenes


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
        yield 'film', clips, lambda **kwargs: films.director.track_clips(objects, root, **kwargs)
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


def test_scene_requires_both_active_directors_and_their_own_playable_clocks():
    # An FMV can be drawn inside a different scene which supplies all of its
    # dialogue. A sibling prefab with the same names must not supply that audio.
    cab = lambda char: 'CAB-' + char * 32
    externals = [f'archive:/{cab(c)}/{cab(c)}' for c in 'abc']
    objs = {}
    def game(key, parent, children):
        objs[key] = {'m_IsActive': True, 'm_Component': [{'component': _ptr(key+1)}, {'component': _ptr(key+2)}]}
        objs[key+1] = {'m_GameObject': _ptr(key), 'm_Father': _ptr(parent+1 if parent else 0),
                       'm_Children': [_ptr(c+1) for c in children]}
    game(10, None, [20, 30])
    game(20, 10, [])
    game(30, 10, [])
    for object_id, file in [(10, 1), (20, 2), (30, 3)]:
        objs[object_id+2] = {'m_GameObject': _ptr(object_id), 'm_Enabled': True, 'm_InitialTime': 0,
                             'm_PlayableAsset': _ptr(90, file)}
    objs[12]['m_ExposedReferences'] = {'m_References': [{'first': str(k), 'second': _ptr(k)} for k in (20, 30)]}
    control = {90: {'m_Tracks': [_ptr(20), _ptr(30)]}}
    for key, name, time in [(20, 'Audio', 1.25), (30, 'Others', 2.5)]:
        control[key] = {'m_Name': name, 'm_Parent': _ptr(90),
                        'm_Clips': [{'m_Asset': _ptr(key+1), 'm_Start': time, 'm_Duration': 4,
                                     'm_ClipIn': 0, 'm_TimeScale': 1}]}
        control[key+1] = {'m_Name': 'ControlPlayableAsset', 'updateDirector': True, 'active': True,
                          'sourceGameObject': {'exposedName': str(key)}}
    master = (cab('a'), 90, control, ())
    prefab = ('prefab', 10, objs, externals)
    expected = {'Audio': (cab('b'), 90), 'Others': (cab('c'), 90)}
    windows = scenes._control_windows(master, prefab, expected)
    assert windows == {'Audio': (1.25, 5.25), 'Others': (2.5, 6.5)}
    def local_track(asset):
        tree = {1: {'m_Tracks': [_ptr(2)]},
                2: {'m_Clips': [{'m_Asset': _ptr(3), 'm_Start': .1, 'm_Duration': 1}]}, 3: asset}
        return ('unused', 1, tree, ())
    assert scenes._scene_clips(local_track({'_textId': 'caption'}), local_track({'_audioEventKey': 'au_vo_test'}),
                              windows) == ([('caption', 2.6, 3.6)], [('au_vo_test', 1.35, 2.35)])
    assert scenes._scene_clips(local_track({'_textId': 'caption'}), local_track({'_audioEventKey': 'au_vo_test'}),
                              {**windows, 'Others': (2.5, 3.1)}) is None
    assert scenes._control_windows(master, prefab, {**expected, 'Audio': (cab('c'), 90)}) is None
    objs[20]['m_IsActive'] = False
    assert scenes._control_windows(master, prefab, expected) is None
    objs[20]['m_IsActive'] = True
    control[30]['m_Clips'][0]['m_TimeScale'] = 2
    assert scenes._control_windows(master, prefab, expected) is None
