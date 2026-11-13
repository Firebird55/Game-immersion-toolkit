import struct
from backend import starrail_events as ev
import pytest


def chunk(tag, body):
    return tag + struct.pack('<I', len(body)) + body


def hierarchy(kind, identity, body):
    return struct.pack('<BII', kind, 4 + len(body), identity) + body


def bank(identity, language, objects, data=b''):
    out = chunk(b'BKHD', struct.pack('<3I', 135, identity, ev.wwise_hash(language)))
    if data:
        out += chunk(b'DIDX', struct.pack('<III', 120, 0, len(data))) + chunk(b'DATA', data)
    return out + chunk(b'HIRC', struct.pack('<I', len(objects)) + b''.join(objects))


def test_cross_bank_play_binding_fetches_complete_embedded_or_streamed_source(tmp_path, monkeypatch):
    event, action, neutral_id, voice_bank, target, media = 50, 60, 70, 80, 90, 120
    action_body = b'\x03\x04' + struct.pack('<I', target) + b'\0\0\0\x04' + struct.pack('<I', voice_bank)
    neutral = bank(neutral_id, 'sfx', [hierarchy(4, event, b'\x01' + struct.pack('<I', action)),
                                       hierarchy(3, action, action_body)])
    objects, _ = ev._bank(neutral, neutral_id, 'sfx')
    assert ev._target(objects, event) == (voice_bank, target)
    with pytest.raises(ValueError):
        ev._bank(neutral, 1, 'sfx')
    with pytest.raises(ValueError):
        ev._bank(neutral, neutral_id, 'Japanese')
    asset = ev.hotfix.AudioFile('Japanese/VoBanks0.pck', 8000, 'a'*32, 'server')
    entry, streamed = ev.Entry(asset, 500, 1000), ev.Entry(asset, 2000, 48)
    for method in (0, 1, 2):
        source = struct.pack('<IBII', 0x40001, method, media, 29) + b'\x01'
        original = b'RIFF' + struct.pack('<I', 15) + b'WAVE' + bytes(11)
        raw = bank(voice_bank, 'Japanese', [hierarchy(2, target, source)], original)
        tree, embedded = ev._bank(raw, voice_bank, 'Japanese')
        key, resolved = ev._media(tree, embedded, entry, target, {media: streamed})
        assert key == media
        if method == 0:
            assert raw[resolved.offset - entry.offset:resolved.offset - entry.offset + resolved.size] == original
        else:
            assert resolved == streamed
            assert ev._media(tree, embedded, entry, target, {}) is None
    multi = dict(objects)
    multi[event] = (4, struct.pack('<IBII', event, 2, action, 99))
    assert ev._target(multi, event) is None


def test_event_directory_resolves_both_named_banks_in_either_order_and_checks_pointer_bounds():
    raw = bytearray(92)
    raw[:4] = b'DBDC'
    struct.pack_into('<7I', raw, 4, 1, len(raw), 256, 24, 0, 28, 1)
    struct.pack_into('<I', raw, 32, 1)
    struct.pack_into('<II', raw, 52, 411, 60)
    struct.pack_into('<III', raw, 60, 411, 72, 0)
    struct.pack_into('<III', raw, 72, 2, 333, 222)
    assert ev.bank_lookup(raw) == {411: (333, 222)}
    struct.pack_into('<I', raw, 56, 89)
    with pytest.raises(ValueError):
        ev.bank_lookup(raw)


def test_random_container_requires_one_authored_playlist_item_and_matching_parent():
    source = bytearray(32)
    struct.pack_into('<IIBII', source, 0, 7, 0x40001, 2, 55, 35)
    source[17] = 1
    struct.pack_into('<I', source, 25, 13)
    playlist = bytearray(76)
    struct.pack_into('<IIHII', playlist, 58, 1, 7, 1, 7, 50000)
    graph = {7: (2, source), 13: (5, playlist)}
    streamed = ev.Entry(None, 100, 35)
    assert ev._media(graph, {}, None, 13, {55: streamed}) == (55, streamed)
    playlist[66] = 2
    assert ev._media(graph, {}, None, 13, {55: streamed}) is None
    graph[13] = (6, bytes(111))
    assert ev._media(graph, {}, None, 13, {55: streamed}) is None


def test_switch_state_joins_the_selected_media_bank_across_indexing_and_playback(tmp_path, monkeypatch):
    name = 'Ev_archive_voice_actor01'
    event, neutral, voice, switch = ev.wwise_hash(name), 10, 20, 30
    none, default, japanese = (ev.wwise_hash(n) for n in ('none', 'actor_default', 'actor_japanese'))
    track = b'RIFF' + struct.pack('<I', 8) + b'WAVEtest'
    asset = ev.hotfix.AudioFile('Japanese/VoBanks1.pck', 600, 'a'*32, 'server')
    entries = {key: ev.Entry(asset, key * 5, 100) for key in (neutral, voice, 70, 80)}
    header = bytearray(48)
    struct.pack_into('<I', header, 0, switch)
    struct.pack_into('<BII', header, 34, 1, 123, default)
    struct.pack_into('<I', header, 44, 2)
    header += struct.pack('<III', 40, 50, 3)
    for state, child in ((none, 40), (default, 40), (japanese, 50)):
        header += struct.pack('<III', state, 1, child)
    header += struct.pack('<I', 2) + b''.join(struct.pack('<I', child) + bytes(10) for child in (50, 40))
    objects = {switch: (6, header)}
    for child, mid in ((40, 41), (50, 51)):
        obj = bytearray(32)
        struct.pack_into('<IIBII', obj, 0, child, 0x40001, 0, mid, len(track))
        obj[17] = 1
        struct.pack_into('<I', obj, 25, switch)
        objects[child] = (2, obj)
    # The lookup's state map includes the neutral alias and two separate
    # localized media-only banks. The Play bank contains neither recording.
    raw = bytearray(140)
    struct.pack_into('<II', raw, 4, 1, 16)
    struct.pack_into('<III', raw, 16, 123, 1, 32)
    struct.pack_into('<7I', raw, 32, 3, none, 60, default, 72, japanese, 84)
    for i, (state, bid) in enumerate(((none, 70), (default, 70), (japanese, 80))):
        struct.pack_into('<III', raw, 60 + i * 12, state, 100 + i * 8, 0)
        struct.pack_into('<II', raw, 100 + i * 8, 1, bid)
    monkeypatch.setattr(ev, '_lookup', lambda *_: ({event: (neutral, voice)}, {event: 4}, raw))
    monkeypatch.setattr(ev, '_tables', lambda *_: ({neutral: entries[neutral]}, entries, {}))
    monkeypatch.setattr(ev, '_target', lambda *_: (voice, switch))
    banks = {neutral: ({}, {}), voice: (objects, {}), 70: ({}, {41: (2, len(track))}),
             80: ({}, {51: (3, len(track))})}
    monkeypatch.setattr(ev, '_bundle', lambda _, chosen, lang: {k: banks[k] for k in chosen})
    monkeypatch.setattr(ev.hotfix.AudioFile, 'read', lambda a, d, offset, length: track if offset == 403 else b'')
    ja = ev.bindings(tmp_path, 'current', 'ja', [name])[name]['localized']
    ko = ev.bindings(tmp_path, 'current', 'ko', [name])[name]['localized']
    assert (ja['event_media'], ja['bank_offset'], ko['event_media']) == (51, 403, 41)
    assert ev.extract(ja, tmp_path) == track
    with pytest.raises(ValueError):
        ev.extract(ja | {'event_variant': 'male'}, tmp_path)
    struct.pack_into('<I', raw, 16, 999)
    assert not ev.bindings(tmp_path, 'next', 'ja', [name])


def test_archive_player_text_and_collaboration_dub_credit():
    from backend.starrail_assets import _archive_rows
    row = {'text_id': 'id', 'texts': {'en': '{F#Miss}{M#Mr.} Stellaron', 'zh-Hans': '星核{F#小姐}{M#先生}'}}
    links = {'id': {'avatar_id': 1, 'audio_event': 'event'}}
    recording = {'event_media': 123}
    options = {'event': {'female': recording, 'male': recording | {'event_media': 321}}}
    female, male = _archive_rows([row], links, options, {}, 'en')
    assert (female['player_voice'], female['text_id'], female['source_text']) == ('female', 'id_f', 'Miss Stellaron')
    assert (male['text_id'], male['source_text'], male['chinese']) == ('id_m', 'Mr. Stellaron', '星核先生')
    options = {'event': {'localized': recording}}
    assert _archive_rows([row], links, options, {1: {'CV_JP': {'Hash': 1}}}, 'en') == [row]
    assert _archive_rows([row], links, options, {1: {'CV_EN': {'Hash': 2}}}, 'en')[0]['audio'] == recording
