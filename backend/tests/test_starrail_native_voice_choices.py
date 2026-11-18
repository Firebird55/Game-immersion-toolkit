"""Metadata-owned auxiliary readers and atomic bounded cache lifecycle."""
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from backend import starrail_native_voice_choices as extra
from backend.starrail_native_preparation import Generation


def metadata_index(*, size=40, missing=False, ambiguous=False):
    blocks, all_blocks, addresses, bounds = {}, [], {}, {}
    for number, (name, fields) in enumerate(sorted(extra.FIELDS.items())):
        row, table = 'RelocatedRow' + str(number) + 'Row', 'RenamedOriginalContainer' + str(number)
        row_address, ctor, loader = 1000 + number*300, 1100 + number*300, 1200 + number*300
        blocks[row] = '\n'.join('    public uint ' + field + ' // Offset: 0x10, Token: 0x1' for field in fields)
        blocks[row] += '\n    public static void FromBinary(Reader, Row&) {}'
        block = (f'    private static string[] resources // Offset: 0x10, Token: 0x1\n'
                 f'    private static Dictionary<uint, {row}> entries // Offset: 0x20, Token: 0x2\n'
                 '    private static void .cctor() {}\n'
                 f'    private static void Load(string) {{}} // VA: 0x180000001, RVA: {hex(loader)}, Token: 0x3\n')
        all_blocks.append((table, table + '#1', block)); blocks[table] = block
        addresses[table, r'private static void \.cctor\(\)'] = ctor
        addresses[row, r'public static void FromBinary\([^\n]*\)'] = row_address
        for address in (row_address, ctor, loader): bounds[address] = (address, address+size)
    if missing: all_blocks.pop()
    if ambiguous: blocks['OtherAmbiguousRow'] = blocks['RelocatedRow0Row']
    def forbidden(*a): pytest.fail('Owner discovery must not read constructor bytes')
    return SimpleNamespace(blocks=blocks, all_blocks=all_blocks,
        method=lambda owner, signature: addresses[owner, signature], native_bounds=lambda address: bounds[address],
        body=forbidden, bodies=forbidden, read=forbidden)


def test_owner_discovery_uses_relocated_metadata_and_measures_every_region_before_reads():
    blocks, permitted, loaders = extra._owners(metadata_index())
    assert len(blocks) == 2 and len(permitted) == 6 and len(loaders) == 2
    assert sum(end-start for start, end in permitted.items()) == 240


@pytest.mark.parametrize('change', [{'missing': True}, {'ambiguous': True}, {'size': 8193}])
def test_missing_ambiguous_or_oversized_owners_stop_before_disassembly(change):
    with pytest.raises(ValueError): extra._owners(metadata_index(**change))


@pytest.mark.parametrize('failure', [None, 'clobber', 'incoming-branch', 'indirect-branch', 'unknown-reader', 'zero-flag'])
def test_loader_requires_owned_reader_and_unclobbered_positive_flag(failure):
    base = 0x180000000
    rows = [('mov', 'rcx, rsi'), ('mov', 'r8b, 0x0' if failure == 'zero-flag' else 'r8b, 0x1'),
            ('mov', 'r9b, 0x1')]
    if failure == 'clobber': rows.append(('xor', 'r8d, r8d'))
    call = len(rows)
    rows.append(('call', hex(base+9000)))
    if failure == 'incoming-branch': rows[0] = ('je', hex(base+100+call))
    if failure == 'indirect-branch': rows[0] = ('jmp', 'rax')
    index = SimpleNamespace(base=base, methods={9000: [{'signature':
        'public static byte Load(string, System.Action<' + ('Other' if failure == 'unknown-reader' else 'Reader') + '>, bool, bool)'}]},
        body=lambda address: ([(100+i, op, args) for i, (op, args) in enumerate(rows)], 'a'*64))
    binding = {'row_block': 'public static void FromBinary(Reader, Row&) {}'}
    if failure:
        with pytest.raises(ValueError): extra._loader(index, binding, 100)
    else: extra._loader(index, binding, 100)


def generation(identity='a'*64):
    return Generation(SimpleNamespace(receipt={'original_native': 'f'*32}, helper=SimpleNamespace(identity='e'*64)),
        {'routes': 'original'}, {'VoiceAtlas': {'base': 'unchanged'}}, identity)


def descriptors():
    return {name: {'fields': [[field, 'u32'] for field in sorted(fields)], 'identity': [],
                   'hash_byte_prefix': True, 'enums': {}} for name, fields in extra.FIELDS.items()}


def test_auxiliary_cache_is_separate_source_bound_and_reused_without_native_io(tmp_path, monkeypatch):
    base = generation(); basefile = tmp_path/'native-descriptions.json'; basefile.write_bytes(b'preserved base21')
    calls = []
    monkeypatch.setattr(extra, '_logic', lambda: 'b'*64)
    monkeypatch.setattr(extra, 'NativeIndex', lambda value: calls.append(value) or object())
    monkeypatch.setattr(extra, 'derive', lambda index: descriptors())
    first = extra.augment(tmp_path, base)
    assert first.native is base.native and first.routes == base.routes and len(first.tables) == 3
    assert base.tables == {'VoiceAtlas': {'base': 'unchanged'}} and basefile.read_bytes() == b'preserved base21'
    monkeypatch.setattr(extra, 'NativeIndex', lambda value: pytest.fail('A verified auxiliary cache must not disassemble'))
    assert extra.augment(tmp_path, base) == first
    assert len(calls) == 1


def test_failed_changed_generation_preserves_old_cache_and_retry_has_a_new_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(extra, '_logic', lambda: 'b'*64)
    monkeypatch.setattr(extra, 'NativeIndex', lambda value: object())
    monkeypatch.setattr(extra, 'derive', lambda index: descriptors())
    first = extra.augment(tmp_path, generation()); path = tmp_path/'voice-choice-native-descriptions.json'
    previous = path.read_bytes()
    def fail(index): raise ValueError('Changed native reader shape')
    monkeypatch.setattr(extra, 'derive', fail)
    with pytest.raises(ValueError): extra.augment(tmp_path, generation('c'*64))
    assert path.read_bytes() == previous
    monkeypatch.setattr(extra, 'derive', lambda index: descriptors())
    updated = extra.augment(tmp_path, generation('c'*64))
    assert updated.identity != first.identity and path.read_bytes() != previous


def test_unproven_cached_prefix_cannot_be_accepted_as_an_eof_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(extra, '_logic', lambda: 'b'*64)
    monkeypatch.setattr(extra, 'NativeIndex', lambda value: object())
    monkeypatch.setattr(extra, 'derive', lambda index: descriptors())
    extra.augment(tmp_path, generation()); path = tmp_path/'voice-choice-native-descriptions.json'
    value = json.loads(path.read_bytes()); value['tables']['AvatarCobrand']['hash_byte_prefix'] = False
    path.write_text(json.dumps(value))
    def fail(index): raise ValueError('New source evidence required')
    monkeypatch.setattr(extra, 'derive', fail)
    with pytest.raises(ValueError): extra.augment(tmp_path, generation())


@pytest.mark.parametrize('malformation', ['unknown-field', 'duplicate-field', 'unsupported-kind', 'unproven-prefix'])
def test_malformed_new_description_cannot_replace_previous_auxiliary_cache(tmp_path, monkeypatch, malformation):
    monkeypatch.setattr(extra, '_logic', lambda: 'b'*64)
    monkeypatch.setattr(extra, 'NativeIndex', lambda value: object())
    monkeypatch.setattr(extra, 'derive', lambda index: descriptors())
    extra.augment(tmp_path, generation()); path = tmp_path/'voice-choice-native-descriptions.json'
    previous = path.read_bytes(); changed = descriptors(); row = changed['AvatarCobrand']
    if malformation == 'unknown-field': row['unexpected'] = 'must not publish'
    elif malformation == 'duplicate-field': row['fields'].append(row['fields'][0])
    elif malformation == 'unsupported-kind': row['fields'][0][1] = 'unknown-scalar'
    else: row['hash_byte_prefix'] = False
    monkeypatch.setattr(extra, 'derive', lambda index: changed)
    with pytest.raises(ValueError): extra.augment(tmp_path, generation('c'*64))
    assert path.read_bytes() == previous


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_canonical_context_adds_owned_descriptions_only_for_audio(tmp_path, monkeypatch, mode):
    from backend import starrail_game_data as game, starrail_native_preparation as native, starrail_original_provider as original
    from backend.game_data_protocol import GameDataRequest
    base = generation(); composed = replace(base, tables=base.tables | descriptors(), identity='c'*64)
    calls = []
    def prepare(directory, build, names, **kwargs):
        assert names == original.TABLES and kwargs['allow_generate'] is False
        return base
    def augment(directory, value):
        assert value is base
        calls.append(value)
        return composed
    monkeypatch.setattr(native, 'prepare', prepare)
    monkeypatch.setattr(extra, 'augment', augment)
    provider = game.create_provider(platform='windows')
    monkeypatch.setattr(provider, '_transport', lambda *a: object())
    monkeypatch.setattr(provider, '_metadata_fetch', lambda *a: pytest.fail('Offline context cannot request transport'))
    ctx = SimpleNamespace(cache_directory=tmp_path, request=GameDataRequest('global', 'en', (), mode), check=lambda: None)
    expected = composed if mode == 'text-audio' else base
    directory = provider._directory(ctx, 'global')
    descriptions = object(); provider._descriptions = (directory.absolute(), expected.identity), descriptions
    def catalog(directory, build, value, **kwargs):
        assert value is expected and kwargs['content_mode'] == 'text'
        assert kwargs['config_descriptions'] is descriptions
        return 'stamp', 'catalog'
    monkeypatch.setattr(original, 'catalog_source', catalog)
    assert provider._text_context(ctx, {}, object(), discover=False, offline=True) == ('stamp', 'catalog', expected)
    assert len(calls) == (1 if mode == 'text-audio' else 0)


def test_canonical_auxiliary_failure_has_an_actionable_gate_without_catalog_or_audio(tmp_path, monkeypatch):
    from backend import starrail_game_data as game, starrail_native_preparation as native, starrail_original_provider as original
    from backend.game_data_protocol import GameDataRequest, GameDataError
    provider = game.create_provider(platform='windows')
    monkeypatch.setattr(provider, '_transport', lambda *a: object())
    monkeypatch.setattr(native, 'prepare', lambda *a, **k: generation())
    def fail(*a): raise ValueError('unrecognized original loader shape')
    monkeypatch.setattr(extra, 'augment', fail)
    monkeypatch.setattr(original, 'catalog_source', lambda *a, **k: pytest.fail('Incomplete descriptions cannot construct a catalog'))
    ctx = SimpleNamespace(cache_directory=tmp_path, request=GameDataRequest('global', 'en', (), 'text-audio'))
    with pytest.raises(GameDataError) as error:
        provider._text_context(ctx, {}, object(), discover=False, offline=True)
    assert error.value.code == 'starrail_voice_choice_metadata_unavailable'


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_required_resource_quote_has_no_hidden_audio_tables_in_text_mode(monkeypatch, mode):
    from backend import starrail_game_data as game, starrail_original_provider as original
    from backend.game_data_protocol import GameDataRequest
    observed = []
    monkeypatch.setattr(game, '_packages_for', lambda catalog, paths: observed.append(paths) or {'missing': object()})
    monkeypatch.setattr(game, '_missing_packages', lambda catalog, packages: packages)
    catalog = SimpleNamespace(text_locales={'en': ('EN',)}, file=lambda *a: pytest.fail('Quote cannot read unavailable tables'))
    phase, _, _ = game._required_text(catalog, GameDataRequest('global', 'en', (), mode))
    expected = original.TABLES | (extra.EXTRA_TABLES if mode == 'text-audio' else set())
    assert phase == 'text-core'
    assert observed == [{'BakedConfig/ExcelOutput/'+name+'.bytes' for name in expected}
                        | {'BakedConfig/ExcelOutput/Textmap_en.bytes'}]
