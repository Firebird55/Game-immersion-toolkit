"""Staged original Readable evidence never relabels the accepted legacy route."""
import copy
import importlib.util
from pathlib import Path

import pytest

from backend import genshin_source_receipt as receipt
from backend.genshin_original_containers import asset_identity
from backend.genshin_original_localization import CODES, PATH
from backend.tests.test_genshin_source_receipt import manual_snapshot, rehash, validate


def staged():
    payload = manual_snapshot(); source = payload['source_receipt']['original_text']
    table = copy.deepcopy(source['original_tables']['ManualTextMapConfigData'])
    table['owner']['asset_index'] = asset_identity(PATH)
    table['owner']['software_sha256'].update({name: '1' * 64 for name in
        ('genshin_native_slots.py', 'genshin_native_locale_slots.py', 'genshin_native_fields.py',
         'genshin_original_localization.py', 'genshin_official_source.py')})
    table['proof'].update(schema='genshin-original-localization-table-v1', method_sha256s=[c * 64 for c in 'abcd'],
                          complete_native_storage=True, all_locales=sorted(CODES))
    source['staged_original_readables'] = {'schema': 'genshin-original-readable-source-v1',
        'scope': 'localization-owned-readable-text', 'replaces_legacy_readables': False,
        'table': table, 'locales': {'EN': {'locale': 'EN', 'total_utf8_bytes': 12,
            'files': [['Book7_EN.txt', 7, asset_identity('ART/UI/Readable/EN/Book7_EN'), 7, 12, '2' * 64]],
            'source_missing': [{'id': 8, 'path': 'ART/UI/Readable/EN/Book8_EN', 'reason': 'not-in-current-design-catalog'}],
            'sprite_text_images': [{'id': 9, 'path': 'ART/UI/Atlas/SpriteText/EN/Glyph_EN'}]}}}
    rehash(payload['source_receipt'])
    return payload


@pytest.mark.parametrize('change', [None, 'activation', 'coverage', 'edition', 'manifest', 'software', 'schema',
    'boolean-count', 'wrong-path', 'duplicate-file', 'totals', 'invented-unvoiced', 'image-as-text'])
def test_staged_readable_receipt_reopens_only_its_exact_source_and_scope(change):
    payload = staged(); source = payload['source_receipt']['original_text']; value = source['staged_original_readables']
    owner, proof = value['table']['owner'], value['table']['proof']; english = value['locales']['EN']
    if change == 'activation': value['replaces_legacy_readables'] = True
    elif change == 'coverage': payload['source_receipt']['coverage']['Readable'] = 'original-publisher'
    elif change == 'edition': owner['metadata']['name'] = owner['metadata']['name'].replace('GenshinImpact', 'YuanShen')
    elif change == 'manifest': owner['manifest_sha256'] = '0' * 64
    elif change == 'software': owner['software_sha256'].pop('genshin_native_slots.py')
    elif change == 'schema': proof['complete_native_storage'] = False
    elif change == 'boolean-count': proof['rows'] = True
    elif change == 'wrong-path': english['files'][0][2] = asset_identity('ART/UI/Readable/JP/Book7_JP')
    elif change == 'duplicate-file': english['files'].append(english['files'][0])
    elif change == 'totals': english['total_utf8_bytes'] += 1
    elif change == 'invented-unvoiced': english['source_missing'][0]['reason'] = 'unvoiced'
    elif change == 'image-as-text': english['files'][0][2] = asset_identity(english['sprite_text_images'][0]['path'])
    rehash(payload['source_receipt'])
    if change is None:
        result = validate(payload)
        assert result['coverage']['Readable'] == 'community-not-converted'
        assert result['original_text']['staged_original_readables']['replaces_legacy_readables'] is False
    else:
        with pytest.raises(ValueError): validate(payload)


def test_new_receipt_validation_remains_standalone_stdlib_and_old_receipts_stay_unchanged(monkeypatch):
    import builtins
    new, old = staged(), manual_snapshot()
    normal = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith('backend'):
            pytest.fail('A portable receipt imported a publisher/native/desktop module')
        return normal(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    path = Path(receipt.__file__)
    spec = importlib.util.spec_from_file_location('standalone_readable_receipt', path)
    standalone = importlib.util.module_from_spec(spec); spec.loader.exec_module(standalone)
    for payload in (new, old):
        result = standalone.validate(payload['source_receipt'], publisher=payload['fingerprint'],
            region=payload['publisher_region'], metadata_revision=payload['metadata_revision'])
        assert result['coverage']['Readable'] == 'community-not-converted'
    assert 'staged_original_readables' not in old['source_receipt']['original_text']


@pytest.mark.parametrize('change', [None, 'staged-schema', 'not-consumed', 'missing-locale', 'mixed-fields', 'false-origin'])
def test_consumed_original_route_requires_its_own_schema_and_every_selected_locale(change):
    payload = staged(); source = payload['source_receipt']['original_text']
    value = source.pop('staged_original_readables')
    source['original_readables'] = value
    value['schema'] = 'genshin-original-readable-source-v2'
    value['legacy_directory_replaced'] = True
    value.pop('replaces_legacy_readables')
    payload['source_receipt']['coverage']['Readable'] = 'original-publisher'
    assert set(source['locales']) == {'EN'}
    if change == 'staged-schema': value['schema'] = 'genshin-original-readable-source-v1'
    elif change == 'not-consumed': value['legacy_directory_replaced'] = False
    elif change == 'missing-locale': value['locales'].clear()
    elif change == 'mixed-fields': source['staged_original_readables'] = copy.deepcopy(value)
    elif change == 'false-origin': payload['source_receipt']['coverage']['Readable'] = 'community-not-converted'
    rehash(payload['source_receipt'])
    if change is None:
        assert validate(payload)['coverage']['Readable'] == 'original-publisher'
    else:
        with pytest.raises(ValueError): validate(payload)
