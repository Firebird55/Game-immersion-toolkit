"""Original document source/cache/consumer behavior with bounded authored data."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import genshin_original_localization as localized
from backend import genshin_official_source as source
from backend.genshin_original_containers import DesignCatalog, asset_identity
from backend.genshin_original_excel import metadata_name, MANUAL_PATH
from backend.tests.test_genshin_original_containers import catalog
from backend.tests.test_genshin_official_text import Objects, generation
from backend.tests.test_genshin_download_plan import fixtures as quote_fixtures


def rows():
    def row(identity, stem, prefix='ART/UI/Readable/'):
        paths = {code: prefix + code + '/' + stem + ('' if code == 'CHS' else '_' + code) for code in localized.CODES}
        return {'id': identity, 'paths': paths, 'default': paths['CHS']}
    return [row(7, 'Book7'), row(8, 'Note7'), row(9, 'BookMissing'),
            row(10, 'Glyph', 'ART/UI/Atlas/SpriteText/')]


def fixture(tmp_path, monkeypatch):
    directory = tmp_path / 'original'; directory.mkdir()
    native = directory / 'native'; native.write_bytes(b'N' * 1024)
    metadata = directory / 'metadata'; metadata.write_bytes(b'M' * 1024)
    canonical = rows()
    table_payload = b'complete synthetic localized inventory'
    payloads = {asset_identity(localized.PATH): table_payload}
    for row in canonical[:2]:
        for code in ('JP', 'EN'):
            payloads[asset_identity(row['paths'][code])] = (
                ('確認する。\n\n記録を読む。' if code == 'JP' else 'Check this.\n\nRead the note.')
                if row['id'] == 7 else ('注意。' if code == 'JP' else 'A note.')).encode()
    text_tables, text_payloads, _ = generation()
    identities = tuple(payloads) + tuple(text_payloads) + (asset_identity(MANUAL_PATH),)
    owned = DesignCatalog(catalog(identities))
    build, native_asset, metadata_asset, _voice, designs, _ = quote_fixtures()
    native_asset.digest = hashlib.md5(native.read_bytes()).hexdigest()
    metadata_asset.digest = hashlib.md5(metadata.read_bytes()).hexdigest()
    calls, object_calls = [], []
    def official(_directory, selected, _publisher, name, *args):
        assert selected == build and name == metadata_name(build['channel'])
        return metadata, {'name': name, 'publisher_md5': hashlib.md5(metadata.read_bytes()).hexdigest(),
                          'sha256': hashlib.sha256(metadata.read_bytes()).hexdigest(), 'bytes': metadata.stat().st_size}
    monkeypatch.setattr(source, '_official_file', official)
    def parse(exe, meta, payload):
        assert exe == native.read_bytes() and meta == metadata.read_bytes() and payload == table_payload
        calls.append(True)
        data = copy.deepcopy(canonical)
        proof = {'schema': localized.SCHEMA, 'rows': len(data), 'payload_bytes': len(payload),
            'payload_sha256': hashlib.sha256(payload).hexdigest(), 'canonical_sha256': localized.canonical_digest(data),
            'contract_sha256': 'a' * 64, 'method_sha256s': [c * 64 for c in 'bcde'],
            'strict_eof': True, 'source_kind': 'original-publisher', 'all_locales': sorted(localized.CODES),
            'complete_native_storage': True}
        return data, proof
    monkeypatch.setattr(localized, 'read_localization', parse)
    def make():
        value = object.__new__(source.Source)
        value.directory, value.publisher, value.build = directory, directory / 'sophon', build
        value.stamp = 'sophon-' + source.identity(build)
        value.catalog, value.helper = owned, SimpleNamespace(identity='f' * 64)
        value.native_input = native, {'name': 'GenshinImpact.exe', 'bytes': 1024,
            'publisher_md5': native_asset.digest, 'sha256': hashlib.sha256(native.read_bytes()).hexdigest()}
        value.localization_rows, value.localization_receipt = None, None
        value.readable_inventories, value.readable_receipts, value.package_receipts = {}, {}, {}
        value.packages = {name: {'name': name, 'bytes': row['fileSize'], 'md5': row['md5']} for name, row in designs.items()}
        value.objects = lambda package: object_calls.append(package) or Objects(payloads)
        return value
    monkeypatch.setattr(source.sophon, 'manifest', lambda *_args: {'GenshinImpact.exe': native_asset,
        metadata_name(build['channel']): metadata_asset})
    return SimpleNamespace(make=make, rows=canonical, parse_calls=calls, object_calls=object_calls,
                           metadata=metadata, payloads=payloads, tables=text_tables)


def test_source_directory_feeds_the_existing_readable_consumer_and_keeps_unknowns(tmp_path, monkeypatch):
    from backend.genshin_assets import readable_records
    f = fixture(tmp_path, monkeypatch); owned = f.make()
    files = dict(owned.directory_text('Readable/JP'))
    assert set(files) == {'Book7_JP.txt', 'Note7_JP.txt'} and len(f.parse_calls) == 1
    assert owned.readable_receipts['JP']['source_missing'][0]['reason'] == 'not-in-current-design-catalog'
    assert len(owned.readable_receipts['JP']['sprite_text_images']) == 1
    warnings = []
    records = readable_records(owned, ('ja', 'en'), 'ja', [], warnings)
    assert len(records) == 3 and not warnings
    book = [r for r in records if ':Book7:' in r['text_id']]
    assert len(book) == 2 and all(r['voice_status'] == 'unvoiced' for r in book)
    assert book[0]['texts'] == {'ja': '確認する。', 'en': 'Check this.'}
    assert next(r for r in records if ':Note7:' in r['text_id'])['voice_status'] == 'unknown'
    guarded = readable_records(owned, ('ja',), 'ja', [{'source_text': '確認する。', 'voice_status': 'unavailable'}], [])
    assert next(r for r in guarded if r['source_text'] == '確認する。')['voice_status'] == 'unknown'


def test_cached_original_inventory_reopens_and_repairs_proof_without_mirror_rows(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    first = f.make(); expected = first.localization()
    assert f.make().localization() == expected and len(f.parse_calls) == 1
    cache, = first.directory.glob('localization-*.private-json')
    broken = json.loads(cache.read_bytes()); broken['proof']['complete_native_storage'] = False
    cache.write_text(json.dumps(broken))
    assert f.make().localization() == expected and len(f.parse_calls) == 2


def test_changed_native_metadata_failure_retains_previous_verified_localization(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); previous = f.make(); expected = previous.localization()
    cache, = previous.directory.glob('localization-*.private-json'); held = cache.read_bytes()
    f.metadata.write_bytes(b'changed original metadata')
    monkeypatch.setattr(localized, 'read_localization', lambda *args: (_ for _ in ()).throw(ValueError('unknown new shape')))
    current = f.make()
    with pytest.raises(ValueError, match='new shape'): current.localization()
    assert cache.read_bytes() == held and current.localization_receipt is None and previous.localization() == expected


def test_text_only_refined_plan_includes_source_containers_without_reading_document_payloads(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch); owned = f.make()
    # Table acquisition belongs to the already-budgeted native source stage.
    owned.localization(); f.object_calls.clear()
    plan = owned.readable_plan(content_mode='text', study_locales=('en',))
    assert plan['content_mode'] == 'text' and not f.object_calls
    assert plan['metadata_materialization_bytes_exact'] == 1024
    assert plan['staged_readables']['locales']['EN'] == {'files': 2, 'source_missing': 1, 'sprite_text_images': 1}
    assert plan['additional_design_packages'] == ['blocks/03/99.blk']
    assert all('voice' not in row['parts'] for row in plan['objects']) and not plan['complete_game_quote']
    assert plan['staged_readables']['replaces_legacy_readables'] is False


def test_only_explicit_original_catalog_routes_readables_and_never_falls_back(monkeypatch):
    from backend.genshin_publisher import ReleaseCatalog
    from backend.dialogue_catalog import DialogueCatalog
    calls = []
    monkeypatch.setattr(DialogueCatalog, 'directory_text', lambda self, relative, suffix='.txt':
                        calls.append(('legacy', relative)) or [('legacy', 'retained')])
    catalog = object.__new__(ReleaseCatalog)
    assert catalog.directory_text('Readable/JP') == [('legacy', 'retained')]
    original = SimpleNamespace(directory_text=lambda relative, suffix: calls.append(('original', relative))
                               or [('Book7_JP.txt', '確認する。')])
    catalog.official_source = original
    assert catalog.directory_text('Readable/JP') == [('Book7_JP.txt', '確認する。')]
    assert original.original_readables_active is True
    assert catalog.directory_text('Subtitle/JP', suffix='.srt') == [('legacy', 'retained')]
    original.directory_text = lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('new original shape failed'))
    before = len(calls)
    with pytest.raises(ValueError, match='original shape failed'): catalog.directory_text('Readable/JP')
    assert len(calls) == before


@pytest.mark.parametrize('change', ['duplicate', 'fallback', 'bad-utf8'])
def test_bad_or_missing_text_is_never_promoted_to_an_ordinary_translation(tmp_path, monkeypatch, change):
    f = fixture(tmp_path, monkeypatch)
    if change == 'duplicate':
        duplicate = copy.deepcopy(f.rows[0]); duplicate['id'] = 77; f.rows.append(duplicate)
    elif change == 'fallback':
        f.rows[0]['paths']['JP'] = ''
    else:
        f.payloads[asset_identity(f.rows[0]['paths']['JP'])] = b'\xff'
    owned = f.make()
    if change == 'fallback':
        files = dict(owned.directory_text('Readable/JP'))
        assert 'Book7_JP.txt' not in files and 'Book7.txt' not in files
        assert any(row['reason'] == 'publisher-language-fallback' for row in owned.readable_receipts['JP']['source_missing'])
    else:
        with pytest.raises((ValueError, UnicodeDecodeError)): owned.directory_text('Readable/JP')
        assert not owned.readable_receipts


@pytest.mark.parametrize('change', ['duplicate-id', 'partial-languages', 'traversal', 'nul', 'boolean-id'])
def test_current_native_rows_must_keep_complete_language_and_identity_ownership(change):
    data = rows()
    if change == 'duplicate-id': data[1]['id'] = data[0]['id']
    elif change == 'partial-languages': data[0]['paths'].pop('IT')
    elif change == 'traversal': data[0]['paths']['EN'] = 'ART/../elsewhere'
    elif change == 'nul': data[0]['paths']['EN'] = 'ART/\0elsewhere'
    else: data[0]['id'] = True
    with pytest.raises(ValueError): localized.validate_rows(data)
