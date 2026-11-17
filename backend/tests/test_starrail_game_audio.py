"""Real context byte fences and inert original PCK/RIFF format fixtures."""
import hashlib
import copy
import json
from pathlib import Path
import shutil
import struct
from types import MappingProxyType
import wave

import pytest
import zstandard

from backend import starrail_game_audio as audio
from backend.game_data import GameDataService, _Context
from backend.game_data_protocol import GameDataError, GameDataRequest
from backend.publisher_transport import PublisherTransport
from backend.voice_assets import voice_hash
from backend.tests.test_publisher_transport import Response


def package():
    original = b'RIFF' + struct.pack('<I', 12) + b'WAVE' + bytes(8)
    table = struct.pack('<IQ4I', 1, voice_hash('English/voice/Owned.wem'), 1, len(original), 80, 0)
    header = b'AKPK' + struct.pack('<6I', 60, 1, 4, 4, 4, len(table)) + bytes(12) + table
    return header + bytes(80 - len(header)) + original


def lookup_bytes():
    raw = bytearray(80)
    raw[:4] = b'DBDC'
    for offset, values in ((4, (1, 80)), (16, (24,)), (24, (28, 1, 1)),
                           (52, (123, 60)), (60, (123, 72, 0)), (72, (1, 55))):
        struct.pack_into('<' + 'I' * len(values), raw, offset, *values)
    return bytes(raw)


def test_lookup_quotes_compressed_chunks_reconstructs_offline_and_checks_whole_md5(fixture, tmp_path):
    from backend import sophon_assets as sophon, starrail_events as events
    ctx = fixture[0]; raw = lookup_bytes(); encoded = zstandard.ZstdCompressor().compress(raw)
    digest = hashlib.md5(raw).hexdigest(); url = 'https://autopatchos.starrails.com/lookup/chunk'
    asset = sophon.File(events.LOOKUP, len(raw), digest,
        ((0, len(raw), len(encoded), 'chunk', digest),), url.rsplit('/', 1)[0])
    calls = []
    def open_(request, **kwargs):
        calls.append(request)
        assert request.full_url == url and request.get_header('Range') is None
        return Response(encoded, url=url)
    transport = PublisherTransport(ctx, hosts={'autopatchos.starrails.com'}, opener=open_)
    lookup = audio.OriginalLookup(tmp_path / 'sophon', asset)
    first = lookup.quote()
    assert first.download_bytes == len(encoded) != len(raw) and first.spans == (asset,)
    assert first.disk_bytes >= len(raw) * 2
    lookup.acquire(asset, transport)
    assert len(calls) == 1 and lookup.read() == raw and lookup.quote().spans == ()
    assert events.bank_lookup(lookup.read()) == {123: (55,)}
    lookup.path.write_bytes(bytes(len(raw)))
    repaired = lookup.quote()
    assert repaired.download_bytes == 0 and repaired.spans == (asset,)
    lookup.acquire(asset, transport)
    assert len(calls) == 1 and lookup.read() == raw
    # The complete verified body can survive loss of its source chunk.
    (lookup.directory / 'chunks' / digest).unlink()
    assert lookup.quote().complete and lookup.read() == raw


def test_whole_verified_but_malformed_lookup_cannot_publish_a_stage(fixture, tmp_path):
    from backend import sophon_assets as sophon, starrail_events as events
    raw = bytes(80); digest = hashlib.md5(raw).hexdigest()
    asset = sophon.File(events.LOOKUP, len(raw), digest, ((0, len(raw), 12, 'chunk', digest),),
        'https://autopatchos.starrails.com/lookup')
    lookup = audio.OriginalLookup(tmp_path / 'sophon', asset)
    path = lookup.directory / 'chunks' / digest; path.parent.mkdir(parents=True); path.write_bytes(raw)
    class NoTransport:
        def fetch_bytes(self, *args, **kwargs):
            pytest.fail('A verified source chunk must be reused offline')
    with pytest.raises(ValueError):
        lookup.acquire(asset, NoTransport())
    assert not lookup.path.exists()


@pytest.fixture
def fixture(tmp_path):
    service = GameDataService(tmp_path, {})
    ctx = _Context(service, tmp_path, 'local', 'starrail', GameDataRequest('global', 'en', (), 'text-audio'),
        tmp_path / 'stage', 'download', budget=1024 * 1024)
    body = package()
    owner = audio.Owner('English/External.pck', len(body), hashlib.md5(body).hexdigest(),
        'https://autopatchos.starrails.com/test/External.pck', 'a' * 64)
    tag = {'value': '"opaque-publisher-generation"'}; calls = []
    def open_(request, **kwargs):
        assert request.get_method() == 'GET' and request.data is None
        start, end = map(int, request.get_header('Range')[6:].split('-'))
        headers = {'Content-Range': f'bytes {start}-{end}/{len(body)}', 'Content-Length': str(end-start+1)}
        if tag['value'] is not None:
            headers['ETag'] = tag['value']
        calls.append(request)
        return Response(body[start:end+1], status=206, url=owner.url, headers=headers)
    transport = PublisherTransport(ctx, hosts={'autopatchos.starrails.com'}, opener=open_)
    store = audio.RangeStore(ctx.cache_directory / 'original-audio')
    yield ctx, body, owner, store, transport, calls, tag
    service.close()


def acquire_headers(fixture):
    _, body, owner, store, transport, calls, _ = fixture
    first = audio.header_quote((owner,), store)
    assert first.phase == 'audio-inventory-prefixes' and first.download_bytes == 28
    assert calls == []
    store.acquire(first.spans[0], transport)
    second = audio.header_quote((owner,), store)
    assert second.phase == 'audio-inventory-headers' and second.download_bytes == 40
    store.acquire(second.spans[0], transport)
    assert audio.header_quote((owner,), store).spans == ()
    return owner, store, transport


def test_actual_strong_response_tag_and_staged_sizes_never_assume_md5_etag(fixture):
    owner, store, _ = acquire_headers(fixture)
    ctx, _, _, _, _, calls, tag = fixture
    assert calls[0].get_header('If-match') is None
    assert calls[1].get_header('If-match') == tag['value'] != '"' + owner.md5 + '"'
    assert ctx.consumed == 68
    for span in (audio.Span(owner, 0, 28), audio.Span(owner, 28, 40)):
        value = store.receipt(span)
        assert value['verification'] == 'publisher-owned-https-range'
        assert value['response_etag'] == tag['value']
    before = len(calls)
    store.acquire(audio.Span(owner, 28, 40), fixture[4])
    assert len(calls) == before


@pytest.mark.parametrize('tag', [None, 'W/"weak"'])
def test_missing_or_weak_initial_tag_never_materializes_original(fixture, tag):
    _, _, owner, store, transport, _, tags = fixture
    tags['value'] = tag
    with pytest.raises(GameDataError, match='strong server identity'):
        store.acquire(audio.Span(owner, 0, 28), transport)
    assert store.receipt(audio.Span(owner, 0, 28)) is None
    assert not store._path(audio.Span(owner, 0, 28)).exists()


def test_changed_object_before_second_read_preserves_original_prefix(fixture):
    _, _, owner, store, transport, _, tags = fixture
    prefix = audio.Span(owner, 0, 28); store.acquire(prefix, transport)
    tags['value'] = '"different-generation"'
    with pytest.raises(GameDataError) as error:
        store.acquire(audio.Span(owner, 28, 40), transport)
    assert error.value.code == 'publisher_object_changed'
    assert store.receipt(prefix) is not None
    assert store.receipt(audio.Span(owner, 28, 40)) is None


def test_corrupt_ranges_and_changed_generation_are_quoted_again(fixture):
    owner, store, _ = acquire_headers(fixture)
    span = audio.Span(owner, 28, 40)
    store._path(span).write_bytes(bytes(40))
    assert audio.header_quote((owner,), store).spans == (span,)
    other = audio.Owner(owner.name, owner.size, owner.md5, owner.url, 'b' * 64)
    assert audio.header_quote((other,), store).download_bytes == 28


def test_contained_member_requires_complete_verified_same_owner_range(fixture):
    owner, store, transport = acquire_headers(fixture)
    parent, child = audio.Span(owner, 68, 32), audio.Span(owner, 80, 20)
    store.acquire(parent, transport)
    calls = len(fixture[5]); store.acquire(child, transport)
    assert len(fixture[5]) == calls and store.receipt(child) is None
    assert store.available(child) and store.read(child) == package()[80:]
    other = audio.Owner(owner.name, owner.size, owner.md5, owner.url, 'b' * 64)
    assert not store.available(audio.Span(other, 80, 20))
    store._path(parent).write_bytes(bytes(32))
    assert not store.available(child)
    with pytest.raises(GameDataError, match='not verified locally'):
        store.read(child)


def test_batch_inventory_hashes_each_cover_once_and_rechecks_after_mutation(fixture, monkeypatch):
    owner, store, transport = acquire_headers(fixture)
    parent = audio.Span(owner, 80, 20); store.acquire(parent, transport)
    children = (audio.Span(owner, 80, 10), audio.Span(owner, 90, 10))
    original_hash = audio._hash; calls = []
    def hash_(path):
        calls.append(path)
        return original_hash(path)
    monkeypatch.setattr(audio, '_hash', hash_)
    assert store.missing(children) == ()
    assert calls == [store._path(parent)]
    calls.clear()
    assert store.inspect((parent, parent)) == {parent: hashlib.sha256(package()[80:]).hexdigest()}
    assert calls == [store._path(parent)]
    store._path(parent).write_bytes(bytes(20))
    assert store.missing(children) == children
    with pytest.raises(GameDataError, match='not verified locally'):
        store.inspect((parent,))


def test_cache_receipt_boolean_cannot_alias_integer_owner_bounds(fixture):
    owner, store, _ = acquire_headers(fixture)
    span = audio.Span(owner, 0, 28); path = store._path(span).with_name('0-28.json')
    value = json.loads(path.read_bytes()); value['span']['start'] = False
    path.write_text(json.dumps(value))
    assert store.receipt(span) is None


def test_coalescing_never_crosses_owner_gap_or_explicit_range_limits(fixture):
    owner = fixture[2]
    first, second = audio.Span(owner, 80, 10), audio.Span(owner, 95, 5)
    assert audio.coalesce((second, first, first), gap=5) == (audio.Span(owner, 80, 20),)
    assert len(audio.coalesce((first, second), gap=4)) == 2
    assert len(audio.coalesce((first, second), gap=5, maximum=12)) == 2
    assert audio.coalesce((audio.Span(owner, 80, 20), audio.Span(owner, 85, 5)), maximum=12) == (audio.Span(owner, 80, 20),)
    other = audio.Owner(owner.name, owner.size, owner.md5, owner.url, 'b' * 64)
    assert len(audio.coalesce((first, audio.Span(other, 90, 10)))) == 2
    with pytest.raises(GameDataError):
        audio.coalesce((first,), gap=True)


def test_malformed_header_cannot_authorize_followup_ranges(fixture):
    _, _, owner, store, transport, _, _ = fixture
    span = audio.Span(owner, 0, 28); store.acquire(span, transport)
    path = store._path(span); raw = bytearray(path.read_bytes())
    struct.pack_into('<I', raw, 4, 2**32-1); path.write_bytes(raw)
    receipt = path.with_name(path.name + '.json'); value = json.loads(receipt.read_bytes())
    value['sha256'] = hashlib.sha256(raw).hexdigest(); receipt.write_text(json.dumps(value))
    with pytest.raises(GameDataError, match='header'):
        audio.header_quote((owner,), store)


def test_complete_directory_projection_reads_only_headers_and_preserves_exact_members(fixture, monkeypatch):
    owner, store, _ = acquire_headers(fixture)
    original_read = store.read
    def read(span):
        assert span.start in (0, 28) and span.start + span.length <= 68
        return original_read(span)
    monkeypatch.setattr(store, 'read', read)
    inventory = audio.directories((owner,), store, 'en')
    assert not inventory[0].banks and not inventory[0].sounds
    expected = audio.Span(owner, 80, 20)
    assert inventory[0].external == {voice_hash('English/voice/Owned.wem'): expected}
    assert audio.external_members(inventory, ('English/voice/Owned.wem',), 'en') == {'English/voice/Owned.wem': expected}
    with pytest.raises(GameDataError, match='another dub'):
        audio.external_members(inventory, ('Japanese/voice/Owned.wem',), 'en')
    assert audio.external_members(inventory + inventory, ('English/voice/Owned.wem',), 'en') == {}


def test_neutral_quote_selects_only_authored_event_owners_and_refuses_duplicate_banks(fixture):
    from backend.starrail_events import wwise_hash
    _, _, base, store, _, calls, _ = fixture
    owner = audio.Owner('Banks7.pck', base.size, base.md5, base.url, base.generation)
    selected, unrelated = audio.Span(owner, 80, 10), audio.Span(owner, 90, 10)
    directory = audio.Directory(owner, {}, {11: selected, 22: unrelated}, {})
    name = 'Ev_owned_fixture'
    quote, events = audio.neutral_bank_quote((directory,), {wwise_hash(name): (11,), 999: (22,)}, (name,), store)
    assert quote.phase == 'audio-neutral-banks' and quote.spans == (selected,) and quote.download_bytes == 10
    assert events == {wwise_hash(name): selected} and not calls
    conflicting = audio.Directory(owner, {}, {11: unrelated}, {})
    quote, events = audio.neutral_bank_quote((directory, conflicting), {wwise_hash(name): (11,)}, (name,), store)
    assert quote.spans == () and events == {}
    quote, events = audio.neutral_bank_quote((directory,), {wwise_hash(name): (11, 22)}, (name,), store)
    assert quote.spans == () and events == {}


def test_localized_bank_quote_requires_owned_play_target_and_matching_lookup(fixture):
    from backend.starrail_events import wwise_hash
    from backend.tests.test_starrail_events import bank, hierarchy
    base = fixture[2]; name = 'Ev_owned_fixture'; event = wwise_hash(name)
    neutral_owner = audio.Owner('Banks7.pck', 8000, base.md5, base.url, base.generation)
    voice_owner = audio.Owner('English/VoBanks8.pck', 8000, base.md5, base.url, base.generation)
    action = b'\x03\x04' + struct.pack('<I', 90) + b'\0\0\0\x04' + struct.pack('<I', 80)
    raw = bank(70, 'sfx', [hierarchy(4, event, b'\x01' + struct.pack('<I', 60)), hierarchy(3, 60, action)])
    neutral_span, voice_span = audio.Span(neutral_owner, 100, len(raw)), audio.Span(voice_owner, 400, 200)
    class Store:
        def available(self, span): return span == neutral_span
        def read(self, span):
            assert span == neutral_span
            return raw
    inventory = (audio.Directory(neutral_owner, {}, {70: neutral_span}, {}),
                 audio.Directory(voice_owner, {}, {80: voice_span}, {}))
    quote, targets = audio.localized_bank_quote(inventory, {event: (70, 80)}, (name,), Store(), 'en')
    assert quote.phase == 'audio-localized-banks' and quote.spans == (voice_span,)
    assert targets == {event: (80, 90, voice_span)}
    quote, targets = audio.localized_bank_quote(inventory, {event: (70,)}, (name,), Store(), 'en')
    assert not quote.spans and not targets


def test_retained_bank_stage_checks_original_id_language_and_cover_geometry(fixture):
    from backend.tests.test_starrail_events import bank
    base = fixture[2]
    owner = audio.Owner('English/VoBanks8.pck', 8000, base.md5, base.url, base.generation)
    raw = bank(80, 'English', [])
    span = audio.Span(owner, 400, len(raw)); cover = audio.Span(owner, 390, len(raw)+20)
    inventory = (audio.Directory(owner, {}, {80: span}, {}),)
    class Store:
        def read(self, chosen):
            assert chosen == span
            return self.raw
    store = Store(); store.raw = raw
    audio.validate_banks(inventory, (cover,), store, 'en')
    store.raw = bank(81, 'English', [])
    with pytest.raises(ValueError):
        audio.validate_banks(inventory, (cover,), store, 'en')
    store.raw = bank(80, 'Japanese', [])
    with pytest.raises(ValueError):
        audio.validate_banks(inventory, (cover,), store, 'en')
    with pytest.raises(GameDataError, match='no complete declared bank'):
        audio.validate_banks(inventory, (audio.Span(owner, 400, len(raw)-1),), store, 'en')


@pytest.mark.parametrize('offset,value', [(0, 2), (12, 1000001)])
def test_internal_directory_counts_cannot_leave_sections_or_allocate_unbounded_rows(fixture, offset, value):
    owner, store, _ = acquire_headers(fixture)
    span = audio.Span(owner, 28, 40); path = store._path(span)
    raw = bytearray(path.read_bytes()); struct.pack_into('<I', raw, offset, value); path.write_bytes(raw)
    receipt = path.with_name(path.name + '.json'); record = json.loads(receipt.read_bytes())
    record['sha256'] = hashlib.sha256(raw).hexdigest(); receipt.write_text(json.dumps(record))
    with pytest.raises(GameDataError):
        audio.directories((owner,), store, 'en')


@pytest.mark.parametrize('start,length', [(-1, 1), (0, 0), (True, 28), (2**60, 1), (0, 2**60)])
def test_span_bounds_reject_negative_boolean_and_overflow_shapes(fixture, start, length):
    with pytest.raises(GameDataError):
        audio.Span(fixture[2], start, length)


def test_audio_index_selects_all_selected_dub_and_neutral_owners_not_other_dubs():
    rows = [{'Path': path, 'Md5': str(i) * 32, 'Size': 1000, 'Patch': True}
            for i, path in enumerate(('English/External_renamed.pck', 'English/VoBanks7.pck',
                                      'Banks81.pck', 'Japanese/External.pck', 'Korean/VoBanks1.pck'), 1)]
    raw = b'\n'.join(json.dumps(row).encode() for row in rows)
    routes = {key: folder + '/V4.7Live/output_123_ab_cd' for key, folder in
              [('design', 'design_data'), ('asb', 'asb'), ('base', 'asb'), ('lua', 'lua')]}
    build = {'channel': 'starrail-global', 'version': '4.7.0', 'hotfix': {
        'routes': routes, 'indexes': {'audio': [123, hashlib.md5(raw).hexdigest(), len(raw)]}}}
    found = audio.owners(build, raw, 'en')
    assert {owner.name for owner in found} == {'English/External_renamed.pck', 'English/VoBanks7.pck', 'Banks81.pck'}
    assert all(owner.url.startswith('https://autopatchos.starrails.com/') for owner in found)
    enriched = copy.deepcopy(build)
    enriched.update(manifests={'game': ['new metadata receipt']}, native_file_md5='a' * 32,
                    toolkit_reader='changed helper receipt')
    enriched['hotfix']['indexes']['design'] = [456, 'b' * 32, 100]
    enriched['hotfix']['routes']['design'] = 'design_data/V4.7Live/output_456_cd_ef'
    assert audio.owners(enriched, raw, 'en') == found
    moved = copy.deepcopy(enriched)
    moved['hotfix']['routes']['asb'] = 'asb/V4.7Live/output_456_cd_ef'
    assert {owner.generation for owner in audio.owners(moved, raw, 'en')}.isdisjoint(
        owner.generation for owner in found)
    changed = copy.deepcopy(enriched)
    changed['hotfix']['indexes']['audio'][0] += 1
    assert audio.owners(changed, raw, 'en')[0].generation != found[0].generation
    with pytest.raises(GameDataError):
        audio.owners(build, raw + b' ', 'en')


def test_new_shared_owner_names_are_inventory_only_and_preserve_primary_generation():
    rows = [{'Path': name, 'Md5': str(n)*32, 'Size': 1000, 'Patch': n > 2}
            for n, name in enumerate(('English/Primary.pck', 'Banks9.pck',
                'unseen_shared_after_update.pck', 'new_layout/novel_bundle.pck', 'Japanese/Foreign.pck'), 1)]
    def build_(items):
        raw = b'\n'.join(json.dumps(row).encode() for row in items)
        routes = {key: folder + '/V4.7Live/output_123_ab_cd' for key, folder in
                  [('design', 'design_data'), ('asb', 'asb'), ('base', 'asb'), ('lua', 'lua')]}
        return {'channel': 'starrail-global', 'version': '4.7.0', 'hotfix': {
            'routes': routes, 'indexes': {'audio': [123, hashlib.md5(raw).hexdigest(), len(raw)]}}}, raw
    build, raw = build_(rows)
    primary = audio.owners(build, raw, 'en'); selected = audio.inventory_owners(build, raw, 'en')
    assert selected[:len(primary)] == primary
    assert {o.name for o in selected} == {row['Path'] for row in rows[:-1]}
    assert {o.generation for o in selected} == {primary[0].generation}
    changed = copy.deepcopy(build); changed['hotfix']['routes']['asb'] = 'asb/V4.7Live/output_456_cd_ef'
    moved = audio.inventory_owners(changed, raw, 'en')
    assert moved[:len(primary)] == primary
    assert moved[-1].url != selected[-1].url and moved[-1].json() != selected[-1].json()
    new_rows = copy.deepcopy(rows); new_rows[2]['Md5'] = 'a' * 32
    new_build, new_raw = build_(new_rows)
    assert audio.inventory_owners(new_build, new_raw, 'en')[0].generation != primary[0].generation
    with pytest.raises(GameDataError):
        audio.inventory_owners(build, new_raw, 'en')


def test_shared_container_requires_exact_requested_namespace_directory_and_unique_owner(fixture, tmp_path):
    old_source, _, old_row = voices(fixture, tmp_path)
    original = fixture[2]; store, transport = fixture[3:5]
    shared = audio.Owner('unseen_name/new_common_bundle.pck', original.size, original.md5,
                         original.url, original.generation)
    for span in (audio.Span(shared, 0, 28), audio.Span(shared, 28, 40), audio.Span(shared, 80, 20)):
        store.acquire(span, transport)
    inventory = audio.directories((shared,), store, 'en'); path = 'English/voice/Owned.wem'
    span = audio.Span(shared, 80, 20)
    assert audio.external_members(inventory, (path,), 'en') == {path: span}
    binding = {'publisher': 'sophon-'+'1'*64, 'locale': 'en', 'source': path, 'file_id': f'{voice_hash(path):016x}'}
    source = audio.OriginalVoices(store, (audio.OriginalMember('starrail:shared', binding, span),))
    row = {'text_id': 'starrail:shared', 'voice_status': 'voiced', 'audio_locale': 'en', 'audio': binding}
    assert source.has(row) and old_source.has(old_row)
    assert audio.external_members(inventory + inventory, (path,), 'en') == {}
    with pytest.raises(GameDataError, match='another dub'):
        audio.external_members(inventory, ('Japanese/voice/Owned.wem',), 'en')
    foreign = audio.Owner('Japanese/another_bundle.pck', shared.size, shared.md5, shared.url, shared.generation)
    foreign_span = audio.Span(foreign, 80, 20)
    assert audio.external_members((audio.Directory(foreign, {voice_hash(path): foreign_span}, {}, {}),), (path,), 'en') == {}
    with pytest.raises(GameDataError, match='another dub'):
        audio.OriginalVoices(store, (audio.OriginalMember('starrail:foreign', binding, foreign_span),))
    # No arbitrary span in a shared owner can replace the authored directory entry.
    with pytest.raises(GameDataError, match='original directory'):
        audio.OriginalVoices(store, (audio.OriginalMember('starrail:wrong', binding, audio.Span(shared, 79, 20)),))


def test_distinct_authored_paths_with_same_hash_remain_unbound(fixture, monkeypatch):
    from backend import voice_assets
    owner = fixture[2]; span = audio.Span(owner, 80, 20)
    directory = audio.Directory(owner, {7: span}, {}, {})
    monkeypatch.setattr(voice_assets, 'voice_hash', lambda source: 7)
    first, second = 'English/voice/First.wem', 'English/voice/Second.wem'
    assert audio.external_members((directory,), (first,), 'en') == {first: span}
    assert audio.external_members((directory,), (first, second), 'en') == {}


def voices(fixture, tmp_path):
    owner, store, transport = acquire_headers(fixture)
    span = audio.Span(owner, 80, 20); store.acquire(span, transport)
    binding = {'publisher': 'sophon-' + '1' * 64, 'locale': 'en', 'source': 'English/voice/Owned.wem',
               'file_id': f'{voice_hash("English/voice/Owned.wem"):016x}'}
    member = audio.OriginalMember('starrail:owned', binding, span)
    decoder, encoder = tmp_path / 'decoder', tmp_path / 'encoder'
    decoder.write_bytes(b'inert executable path fixture'); encoder.write_bytes(b'inert executable path fixture')
    source = audio.OriginalVoices(store, (member,), decoder=decoder, encoder=encoder)
    return source, member, {'text_id': member.text_id, 'voice_status': 'voiced', 'audio_locale': 'en', 'audio': binding.copy()}


def test_has_never_reads_decodes_or_fetches_and_requires_exact_binding(fixture, tmp_path, monkeypatch):
    source, member, row = voices(fixture, tmp_path)
    monkeypatch.setattr(source.store, 'read', lambda *a: pytest.fail('has must not read'))
    monkeypatch.setattr(Path, 'is_file', lambda *a: pytest.fail('has must not stat'))
    monkeypatch.setattr(source, '_run', lambda *a: pytest.fail('has must not decode'))
    assert source.has(MappingProxyType(row))
    assert not source.has(row | {'audio': row['audio'] | {'locale': 'ja'}})
    assert not source.has(row | {'audio_locale': 'ja'})
    assert not source.has(row | {'player_voice': 'female'})
    assert not source.has(row | {'text_id': 'starrail:other'})
    assert not source.has(row | {'voice_status': 'unvoiced'})
    assert not source.has(row | {'text_id': []})


def test_resolve_decodes_only_checked_original_into_owned_destination(fixture, tmp_path, monkeypatch):
    source, member, row = voices(fixture, tmp_path)
    calls = []
    def run(command, cancelled):
        assert not cancelled(); calls.append(command)
        if command[0] == str(source.decoder):
            with wave.open(command[3], 'wb') as stream:
                stream.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); stream.writeframes(b'\x01\x00' * 240)
        else:
            shutil.copyfile(command[command.index('-i') + 1], command[-1])
    monkeypatch.setattr(source, '_run', run)
    output = tmp_path / 'owned-stage' / 'original.wav'
    assert source.resolve(row, output, cancelled=lambda: False) == output
    with wave.open(str(output)) as stream:
        assert stream.getnframes() == 240
    assert len(calls) == 2
    assert not list(output.parent.glob('starrail-original-*'))
    with pytest.raises(GameDataError, match='cancelled'):
        source.resolve(row, tmp_path / 'cancelled.wav', cancelled=lambda: True)
    assert not (tmp_path / 'cancelled.wav').exists()


def test_mutating_materialized_member_and_its_receipt_cannot_rebind_original(fixture, tmp_path):
    source, member, row = voices(fixture, tmp_path)
    path = source.store._path(member.span)
    raw = path.read_bytes()[:-1] + b'\x01'; path.write_bytes(raw)
    receipt = path.with_name(path.name + '.json'); value = json.loads(receipt.read_bytes())
    value['sha256'] = hashlib.sha256(raw).hexdigest(); receipt.write_text(json.dumps(value))
    assert source.has(row)  # No-I/O certification belongs to the frozen source.
    with pytest.raises(GameDataError, match='recording changed'):
        source.resolve(row, tmp_path / 'must-not-publish.wav', cancelled=lambda: False)
    assert not (tmp_path / 'must-not-publish.wav').exists()


def test_missing_original_or_movie_parameter_input_never_certifies_member(fixture, tmp_path):
    _, _, owner, store, _, _, _ = fixture
    member = audio.OriginalMember('starrail:missing', {'locale': 'en', 'source': 'English/voice/Owned.wem',
        'file_id': f'{voice_hash("English/voice/Owned.wem"):016x}'}, audio.Span(owner, 80, 20))
    with pytest.raises(GameDataError):
        audio.OriginalVoices(store, (member,))
    movie = audio.OriginalMember('starrail:movie', {'movie': 'Original.usm'}, member.span)
    with pytest.raises(GameDataError):
        audio.OriginalVoices(store, (movie,))


def test_original_decoder_defaults_use_only_packaged_runtime_contract(fixture, tmp_path, monkeypatch):
    from backend import native_codecs, media_tools
    source, member, row = voices(fixture, tmp_path)
    layout = object(); calls = []
    def packaged(tool, *, layout):
        calls.append((tool, layout))
        return source.decoder if tool == 'vgmstream' else source.encoder
    monkeypatch.setattr(native_codecs, 'packaged_codec_executable', packaged)
    monkeypatch.setattr(media_tools, 'vgmstream_executable', lambda *a, **k: pytest.fail('No source/PATH decoder discovery'))
    monkeypatch.setattr(media_tools, 'ffmpeg_executable', lambda *a, **k: pytest.fail('No PATH/imageio encoder discovery'))
    actual = audio.OriginalVoices(source.store, (member,), layout=layout)
    assert actual.has(row) and calls == [('vgmstream', layout), ('ffmpeg', layout)]
    monkeypatch.setattr(native_codecs, 'packaged_codec_executable', lambda *a, **k: None)
    with pytest.raises(GameDataError, match='codecs are unavailable'):
        actual.resolve(row, tmp_path / 'never.wav', cancelled=lambda: False)
    assert not (tmp_path / 'never.wav').exists()


def test_wrong_dub_reference_or_authored_player_cannot_certify_an_original(fixture, tmp_path):
    source, member, row = voices(fixture, tmp_path)
    wrong = audio.OriginalMember(member.text_id, member.audio | {'locale': 'ja'}, member.span)
    with pytest.raises(GameDataError, match='another dub'):
        audio.OriginalVoices(source.store, (wrong,), decoder=source.decoder, encoder=source.encoder)
    wrong = audio.OriginalMember(member.text_id, member.audio | {'file_id': '0' * 16}, member.span)
    with pytest.raises(GameDataError, match='reference changed'):
        audio.OriginalVoices(source.store, (wrong,), decoder=source.decoder, encoder=source.encoder)
    assert not source.has(row | {'audio_locale': 'ja'})
    assert not source.has(row | {'player_voice': 'female'})


def test_orphaned_member_without_original_header_cannot_start_server_generation(fixture):
    _, _, owner, store, transport, calls, _ = fixture
    with pytest.raises(GameDataError, match='strong server identity'):
        store.acquire(audio.Span(owner, 80, 20), transport)
    assert store.receipt(audio.Span(owner, 80, 20)) is None
    assert not calls
