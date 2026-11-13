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
