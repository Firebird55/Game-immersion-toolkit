"""Authored movie-event graph, two simultaneous takes and their scoped clipping."""
import sqlite3
import struct

import numpy as np
import pytest

from backend import wuthering_assets as assets, wuthering_cinematics as films, wuthering_release as release
from backend.nte_assets import wwise_hash
from backend.tests.test_wuthering_narrative import flat_blob


def bank(event, *, version=172, target=12, sound_type=2, action_count=1):
    def section(kind, data):
        return struct.pack('<4sI', kind, len(data)) + data
    def node(kind, key, body):
        return struct.pack('<BII', kind, 4 + len(body), key) + body
    event_data = bytes(7) + bytes([action_count]) + struct.pack('<I', 11)
    action = bytes([3, 4]) + struct.pack('<I', target)
    sound = struct.pack('<IBI', 0x140001, sound_type, 987654) + bytes(9)
    objects = node(4, wwise_hash(event), event_data) + node(3, 11, action) + node(2, 12, sound)
    return section(b'BKHD', struct.pack('<II', version, 55)) + section(b'HIRC', struct.pack('<I', 3) + objects)


def test_only_exact_single_streamed_sound_is_returned():
    event = 'play_vo_scene'
    data = bank(event)
    assert films.media_id(data, event) == 987654
    for invalid in (bank(event, version=160), bank(event, sound_type=0), bank(event, action_count=2),
                    bank(event, target=13), data[:-1], data + data):
        assert films.media_id(invalid, event) is None
    assert films.media_id(data, 'play_vo_other') is None


def test_numbered_performances_require_one_scene_event_and_current_localized_sources(tmp_path):
    event = 'play_vo_scene'
    row = {'text_id': 'wuwa:line', 'audio': None, 'dialogue_kind': 'cinematic'}
    with sqlite3.connect(tmp_path / 'db_plot_audio.db') as db:
        db.execute('CREATE TABLE plotaudio (Id TEXT, BinData BLOB)')
        for take in ('002', '001'):
            key = 'line_' + take
            db.execute('INSERT INTO plotaudio VALUES (?,?)', (key, flat_blob({0: key, 2: 'take_' + take})))
    table = tmp_path / 'db_cgVedio.db'
    with sqlite3.connect(table) as db:
        db.execute('CREATE TABLE videocaption (CgName TEXT, BinData BLOB)')
        db.execute('CREATE TABLE videosound (CgName TEXT, GirlOrBoy INTEGER, BinData BLOB)')
        db.execute('INSERT INTO videocaption VALUES (?,?)', ('movie', flat_blob({2: 75, 4: 'line'})))
        path = '/Game/Aki/WwiseAudio/Events/' + event + '.' + event
        scene = flat_blob({3: path})
        db.execute('INSERT INTO videosound VALUES (?,?,?)', ('movie', 2, scene))
    sources = [assets.EXTERNAL_ROOT + 'ja_take_' + n + '.wem' for n in ('001', '002')]
    assert films.candidates(tmp_path, [row], sources, 'ja') == [(row, event, sources, 2500)]
    assert films.candidates(tmp_path, [row], sources, 'en') == []
    assert films.candidates(tmp_path, [row], sources[:1], 'ja') == []
    with sqlite3.connect(table) as db:
        db.execute('UPDATE videosound SET BinData=?', (flat_blob({3: path, 4: 15}),))
    assert films.candidates(tmp_path, [row], sources, 'ja') == []
    with sqlite3.connect(table) as db:
        db.execute('UPDATE videosound SET GirlOrBoy=1, BinData=?', (scene,))
    assert films.candidates(tmp_path, [row], sources, 'ja') == []


def test_mix_requires_unique_overlapping_performances_and_stops_at_quiet():
    rng = np.random.default_rng(42)
    first = rng.normal(0, 5000, 14400)
    second = rng.normal(0, 5000, 13200)
    track = np.zeros(144000)
    track[24000:38400] += first
    track[25200:38400] += second
    track[38400:39000] += rng.normal(0, 300, 600)  # room tail in the mix
    begin, end = films.interval(track, [first, second], 2000)
    assert 1800 < begin < 2000 and 3250 < end < 3500
    assert films.interval(track, [first, rng.normal(0, 5000, 14400)], 2000) is None
    track[72000:86400] += first
    track[73200:86400] += second
    assert films.interval(track, [first, second], 2000) is None
    assert films.interval(np.r_[first, np.zeros(3600), second], [first, second], 0) is None


def test_retimed_take_requires_ordered_independent_waveform_matches():
    rng = np.random.default_rng(24)
    blocks = rng.normal(0, 5000, (6, 9000))
    source = np.concatenate([np.r_[part, np.zeros(3000)] for part in blocks])
    mixed = np.concatenate([np.r_[part, np.zeros(800)] for part in blocks])
    track = np.r_[np.zeros(12000), mixed, np.zeros(12000)]
    energy = np.r_[0., np.cumsum(track * track)]
    span = films._performance_span(track, energy, source)
    assert span == (12000, 12000 + 5 * 9800 + 12000)
    track[12000 + 2 * 9800:12000 + 3 * 9800] = 0
    assert films._performance_span(track, np.r_[0., np.cumsum(track * track)], source) is None


def test_publisher_media_references_need_locale_and_bounded_timing():
    ref = {'publisher': 'wuwa-' + 'a' * 64, 'locale': 'en', 'depot': films.MEDIA_ROOT + 'en/123.wem',
           'start_ms': 500, 'end_ms': 6100}
    assert assets._validate_voice(ref) == ref['depot']
    for changed in ({'locale': 'ja'}, {'end_ms': 5}, {'start_ms': False}, {'end_ms': 310000},
                    {'publisher': None}, {'depot': films.MEDIA_ROOT + 'en/4294967296.wem'}):
        with pytest.raises(ValueError):
            assets._validate_voice({**ref, **changed})


def test_patch_tombstone_removes_film_bank(monkeypatch):
    monkeypatch.setattr(release, '_packages', lambda snapshot, channel, layer: layer)
    def locations(tools, layer, params, wanted):
        assert wanted == {'bank'}
        return {'bank': ('pak', 22 if layer == 'BaseFiles' else -2147483648)}
    monkeypatch.setattr(release, '_locations', locations)
    assert release._movie_locations(None, {}, None, 'ko', {'bank'}) == {}
