"""Real context byte fences and inert original PCK/RIFF format fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
from types import MappingProxyType
import wave

import pytest

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
    with pytest.raises(GameDataError):
        audio.owners(build, raw + b' ', 'en')


def voices(fixture, tmp_path):
    owner, store, transport = acquire_headers(fixture)
    span = audio.Span(owner, 80, 20); store.acquire(span, transport)
    binding = {'publisher': 'sophon-' + '1' * 64, 'locale': 'en', 'source': 'English/voice/Owned.wem',
               'file_id': f'{voice_hash("English/voice/Owned.wem"):016x}'}
    member = audio.OriginalMember('starrail:owned', binding, span)
    decoder, encoder = tmp_path / 'decoder', tmp_path / 'encoder'
    decoder.write_bytes(b'inert executable path fixture'); encoder.write_bytes(b'inert executable path fixture')
    source = audio.OriginalVoices(store, (member,), decoder=decoder, encoder=encoder)
    return source, member, {'text_id': member.text_id, 'voice_status': 'voiced', 'audio': binding.copy()}


def test_has_never_reads_decodes_or_fetches_and_requires_exact_binding(fixture, tmp_path, monkeypatch):
    source, member, row = voices(fixture, tmp_path)
    monkeypatch.setattr(source.store, 'read', lambda *a: pytest.fail('has must not read'))
    monkeypatch.setattr(Path, 'is_file', lambda *a: pytest.fail('has must not stat'))
    monkeypatch.setattr(source, '_run', lambda *a: pytest.fail('has must not decode'))
    assert source.has(MappingProxyType(row))
    assert not source.has(row | {'audio': row['audio'] | {'locale': 'ja'}})
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
    member = audio.OriginalMember('starrail:missing', {'locale': 'en'}, audio.Span(owner, 80, 20))
    with pytest.raises(GameDataError, match='not verified locally'):
        audio.OriginalVoices(store, (member,))
    movie = audio.OriginalMember('starrail:movie', {'movie': 'Original.usm'}, member.span)
    with pytest.raises(GameDataError):
        audio.OriginalVoices(store, (movie,))


def test_orphaned_member_without_original_header_cannot_start_server_generation(fixture):
    _, _, owner, store, transport, calls, _ = fixture
    with pytest.raises(GameDataError, match='strong server identity'):
        store.acquire(audio.Span(owner, 80, 20), transport)
    assert store.receipt(audio.Span(owner, 80, 20)) is None
    assert not calls
