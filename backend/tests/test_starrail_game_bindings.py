"""Inert source-owned player and sequence graphs; no locale-name fallback."""
import struct
import hashlib
from types import SimpleNamespace

import pytest

from backend import starrail_game_audio as audio, starrail_game_bindings as bindings
from backend import starrail_events as events
from backend.tests.test_starrail_events import bank, hierarchy


class Store:
    def __init__(self, payloads):
        self.payloads = payloads

    def available(self, wanted):
        return any(span.owner == wanted.owner and span.start <= wanted.start
            and wanted.length <= span.length-(wanted.start-span.start) for span in self.payloads)

    def missing(self, spans):
        return tuple(span for span in dict.fromkeys(spans) if not self.available(span))

    def read(self, wanted):
        for span, raw in self.payloads.items():
            if span.owner == wanted.owner and span.start <= wanted.start and wanted.length <= span.length-(wanted.start-span.start):
                start = wanted.start-span.start
                return raw[start:start+wanted.length]
        raise AssertionError('Unmaterialized source must not be read')


def state_fixture(*, copyright=False, locale='en'):
    name = 'Ev_any_new_character'; event = events.wwise_hash(name)
    owner = lambda path: audio.Owner(path, 100000, 'a' * 32,
        'https://autopatchos.starrails.com/test/' + path, 'b' * 64)
    language = 'Japanese' if locale == 'ja' else 'English'
    neutral, localized = owner('Banks7.pck'), owner(language + '/VoBanks8.pck')
    states = [events.wwise_hash(value) for value in
              (('none', 'actor_default', 'actor_japanese') if copyright else ('none', 'state_male', 'state_female'))]
    switch = bytearray(48)
    struct.pack_into('<I', switch, 0, 90)
    struct.pack_into('<BII', switch, 34, 1, 777, states[1])
    struct.pack_into('<I', switch, 44, 2)
    switch += struct.pack('<III', 91, 92, 3)
    for state, child in zip(states, (91, 91, 92)):
        switch += struct.pack('<III', state, 1, child)
    switch += struct.pack('<I', 2) + b''.join(struct.pack('<I', child) + bytes(10) for child in (91, 92))
    objects = [hierarchy(6, 90, switch[4:])]
    for child in (91, 92):
        sound = bytearray(32)
        struct.pack_into('<IIBII', sound, 0, child, 0x40001, 0, 120, 20)
        sound[17] = 1; struct.pack_into('<I', sound, 25, 90)
        objects.append(hierarchy(2, child, sound[4:]))
    action = b'\x03\x04' + struct.pack('<I', 90) + b'\0\0\0\x04' + struct.pack('<I', 80)
    neutral_raw = bank(70, 'sfx', [hierarchy(4, event, b'\x01' + struct.pack('<I', 60)), hierarchy(3, 60, action)])
    localized_raw = bank(80, language, objects)
    riff = b'RIFF' + struct.pack('<I', 12) + b'WAVE' + bytes(8)
    raw_banks = [neutral_raw, localized_raw, bank(81, language, [], riff), bank(82, language, [], riff)]
    spans = [audio.Span(own, start, len(raw)) for own, start, raw in
             zip((neutral, localized, localized, localized), (100, 100, 1000, 2000), raw_banks)]
    inventory = (audio.Directory(neutral, {}, {70: spans[0]}, {}),
                 audio.Directory(localized, {}, dict(zip((80, 81, 82), spans[1:])), {}))
    raw = bytearray(84)
    raw[:4] = b'DBDC'
    struct.pack_into('<II', raw, 4, 1, 0); struct.pack_into('<I', raw, 16, 24)
    struct.pack_into('<III', raw, 24, 28, 1, 1)
    struct.pack_into('<II', raw, 52, event, 60)
    struct.pack_into('<III', raw, 60, event, 72, 84)
    struct.pack_into('<III', raw, 72, 2, 70, 80)
    raw += struct.pack('<II', 1, 92) + struct.pack('<III', 777, 1, 104)
    raw += struct.pack('<I', 3) + bytes(24)
    for n, (state, bid) in enumerate(zip(states, (81, 81, 82))):
        pointer = len(raw); struct.pack_into('<II', raw, 108+8*n, state, pointer)
        raw += struct.pack('<III', state, pointer+12, 0) + struct.pack('<II', 1, bid)
    struct.pack_into('<I', raw, 8, len(raw))
    return name, bytes(raw), inventory, spans, raw_banks


def test_player_state_plan_requires_original_group_join_and_complete_dependencies():
    name, raw, inventory, spans, raw_banks = state_fixture()
    store = Store(dict(zip(spans[:2], raw_banks[:2])))
    first = bindings.event_inventory(inventory, raw, (name,), store, 'en')
    assert first.quote.phase == 'audio-state-banks' and first.quote.spans
    assert first.bindings == {} and not first.choices
    store.payloads.update(zip(spans[2:], raw_banks[2:]))
    ready = bindings.event_inventory(inventory, raw, (name,), store, 'en')
    assert not ready.quote.spans and not ready.unresolved
    assert set(ready.bindings[name]) == {'male', 'female'}
    for _, span in ready.bindings[name].values():
        audio._riff(store.read(span))
    assert not bindings.recording_quote(ready.bindings, store).spans
    changed = bytearray(raw); struct.pack_into('<I', changed, 92, 778)
    assert bindings.event_inventory(inventory, changed, (name,), store, 'en').unresolved[name] == 'state-owner-unresolved'


@pytest.mark.parametrize('locale', ['en', 'ja'])
def test_copyright_state_requires_explicit_choice_never_event_name_or_locale(locale):
    name, raw, inventory, spans, raw_banks = state_fixture(copyright=True, locale=locale)
    # Neither the matching owner locale nor a JP token in the event name can
    # select a copyright state without the authored policy and user choice.
    name = name if locale == 'en' else name + '_japanese'
    original = events.wwise_hash('Ev_any_new_character'); changed = events.wwise_hash(name)
    raw = raw.replace(struct.pack('<I', original), struct.pack('<I', changed))
    raw_banks[0] = raw_banks[0].replace(struct.pack('<I', original), struct.pack('<I', changed))
    result = bindings.event_inventory(inventory, raw, (name,), Store(dict(zip(spans, raw_banks))), locale)
    assert not result.bindings and not result.quote.spans
    assert result.unresolved == {name: 'state-choice-required'}
    assert len(result.choices[name]['states']) == 3
    assert result.choices[name]['default'] in {row['id'] for row in result.choices[name]['states']}


def test_complete_forward_sequence_preserves_playlist_order_and_member_identity():
    objects = {}
    for child, mid in ((41, 141), (42, 142)):
        raw = bytearray(32)
        struct.pack_into('<IIBII', raw, 0, child, 0x40001, 2, mid, 20)
        raw[17] = 1; struct.pack_into('<I', raw, 25, 8)
        objects[child] = (2, raw)
    playlist = bytearray(88)
    struct.pack_into('<I', playlist, 0, 8); playlist[56:58] = b'\x01\x1a'
    struct.pack_into('<IIIHIIII', playlist, 58, 2, 41, 42, 2, 42, 1, 41, 1)
    objects[8] = (5, playlist)
    owner = state_fixture()[2][1].owner
    entries = {mid: events.Entry(owner, offset, 20) for mid, offset in ((141, 1000), (142, 2000))}
    result = events._recordings(objects, {}, None, 8, entries)
    assert [(key, value[0]) for key, value in result.items()] == [('part-1', 142), ('part-2', 141)]
    # The new member plan is driven by all sequence sources, not only part 1.
    rows = {'new_event': {key: (mid, audio.Span(entry.asset, entry.offset, entry.size)) for key, (mid, entry) in result.items()}}
    quote = bindings.recording_quote(rows, Store({}))
    assert quote.download_bytes == 40 and len(quote.spans) == 2


def test_external_plan_preserves_missing_paths_and_wrong_dub_is_not_a_fallback():
    from backend.voice_assets import voice_hash
    owner = state_fixture()[2][1].owner
    span = audio.Span(owner, 5000, 20)
    source = 'English/voice/new_authored.wem'
    inventory = (audio.Directory(owner, {voice_hash(source): span}, {}, {}),)
    quote, found, missing = bindings.external_quote(inventory,
        (source, 'English/voice/missing_authored.wem'), Store({}), 'en')
    assert quote.spans == (span,) and found == {source: span}
    assert missing == ('English/voice/missing_authored.wem',)
    with pytest.raises(audio.GameDataError, match='another dub'):
        bindings.external_quote(inventory, ('Japanese/voice/new_authored.wem',), Store({}), 'en')


def test_normal_factory_advances_state_and_full_external_quotes_without_network(tmp_path, monkeypatch):
    from backend import starrail_game_data as game, starrail_hotfix, starrail_assets, sophon_assets
    from backend.game_data_protocol import GameDataRequest
    from backend.voice_assets import voice_hash
    name, raw, inventory, spans, raw_banks = state_fixture()
    source = 'English/voice/new_authored.wem'
    inventory[1].external[voice_hash(source)] = audio.Span(inventory[1].owner, 5000, 20)
    store = Store(dict(zip(spans[:2], raw_banks[:2])))
    monkeypatch.setattr(audio, 'inventory_owners', lambda *a: tuple(row.owner for row in inventory))
    monkeypatch.setattr(audio, 'RangeStore', lambda *a: store)
    monkeypatch.setattr(audio, 'header_quote', lambda *a: audio.Quote('audio-inventory-headers', ()))
    monkeypatch.setattr(audio, 'directories', lambda *a: inventory)
    monkeypatch.setattr(starrail_hotfix, 'index', lambda *a, **k: b'cached AudioV')
    asset = sophon_assets.File(events.LOOKUP, len(raw), hashlib.md5(raw).hexdigest(), (), 'https://autopatchos.starrails.com/test')
    monkeypatch.setattr(sophon_assets, 'manifest', lambda *a, **k: {events.LOOKUP: asset})
    class Lookup:
        def __init__(self, *a): self.asset = asset
        def quote(self): return SimpleNamespace(spans=())
        def read(self): return raw
    monkeypatch.setattr(audio, 'OriginalLookup', Lookup)
    monkeypatch.setattr(starrail_assets, 'authored_links', lambda *a: [
        {'audio_event': name}, {'source': source}, {'source': 'English/voice/unbound.wem'}])
    provider = game.create_provider(platform='windows')
    monkeypatch.setattr(provider, '_transport', lambda *a: object())
    def forbidden(*a, **k): raise AssertionError('Source planning cannot download audio')
    monkeypatch.setattr(provider, '_metadata_fetch', lambda *a: forbidden)
    ctx = SimpleNamespace(request=GameDataRequest('global', 'en', (), 'text-audio'), cache_directory=tmp_path)
    catalog = SimpleNamespace(build={'channel': 'starrail-global', 'manifests': {'game': []},
        'hotfix': {'indexes': {'audio': [123, 'a'*32, 100]}}}, tables=SimpleNamespace(directory=tmp_path))
    quote, _, receipt, members = provider._audio_inventory(ctx, catalog)
    assert quote.phase == 'audio-state-banks' and quote.spans and not members
    store.payloads.update(zip(spans[2:], raw_banks[2:]))
    quote, _, receipt, members = provider._audio_inventory(ctx, catalog)
    assert quote.phase == 'audio-external-members' and quote.download_bytes == 20
    assert receipt['external_sources'] == 2 and receipt['external_unbound'] == 1
    assert receipt['event_unresolved'] == 0 and len(members) == 1
