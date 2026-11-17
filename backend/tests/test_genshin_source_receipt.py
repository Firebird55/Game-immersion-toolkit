"""A helper commit cannot silently accept another official title or generation."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import genshin_source_receipt as receipt, language_worker
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_genshin_official_text import generation


def rehash(value):
    value['sha256'] = hashlib.sha256(receipt.canonical({k: v for k, v in value.items() if k != 'sha256'})).hexdigest()


def snapshot():
    tables, _, _ = generation()
    tables.read('EN')
    build = {'channel': 'genshin-global', 'version': '9.4.0', 'manifests': {'game': ['authored-fixture']},
             'hotfix': {'revisions': {'res': [1, 'a'], 'silence': [2, 'b'], 'design': [3, 'c']},
                        'indexes': {'design': ['a' * 32, 123]}}}
    publisher = 'sophon-' + hashlib.sha256(json.dumps(build, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    revision = 'b' * 40
    bindings = {'schema': 'genshin-binding-selection-v1', 'game': 'genshin', 'publisher': publisher,
        'region': 'global', 'version': '9.4.0', 'markers': {'res': '1', 'silence': '2', 'design': '3'},
        'narrative_sha256': 'd' * 64, 'repository': 'Dimbreath/animegamedata2', 'revision': revision,
        'title': 'OSRELWin9.4.0_R1_S2_D3', 'source_region': 'global', 'reference_narrative_sha256': None}
    bootstrap = {'game': 'genshin', 'region': 'global', 'policy': 'immutable-community-hybrid',
        'repository': 'CollapseLauncher/CollapseLauncher-ReleaseRepo', 'revision': 'e' * 40,
        'files': {name: {'sha256': 'f' * 64, 'bytes': 123} for name in ('config_master.json', 'config_GIGlb.json')}}
    original = {'schema': 'genshin-original-text-source-v1', 'publisher': publisher, 'publisher_descriptor': build,
        'official_design_index_md5': 'a' * 32, 'official_design_index_sha256': 'a' * 64,
        'catalog_sha256': tables.catalog.sha256, 'helper_identity': 'c' * 64,
        'format_software': {name: 'd' * 64 for name in ('genshin_original_containers', 'genshin_official_text', 'genshin_official_source')},
        'codec_description': {'policy': 'controlled-community-codec-description-v1',
            'repository': 'Escartem/AnimeStudio', 'path': 'AnimeStudio/Crypto/CryptoHelper.cs',
            'revision': 'd' * 40, 'sha256': 'e' * 64, 'parameters_sha256': 'f' * 64, 'bytes': 123},
        'native': {'name': 'GenshinImpact.exe', 'bytes': 1024, 'publisher_md5': 'a' * 32, 'sha256': 'b' * 64,
            'template_reader_sha256': 'c' * 64, 'parameters_sha256': tables.descriptions[0].fingerprint(),
            'method_sha256s': tables.receipts['EN']['method_sha256s'], 'semantic_owner_claim': False},
        'locales': tables.receipts, 'packages': {'blocks/00/123.blk': {'publisher_md5': 'a' * 32,
            'publisher_bytes': 1000, 'decoded_sha256': 'b' * 64, 'decoded_bytes': 3000}}}
    catalog = SimpleNamespace(revision=revision, selection_receipt=bindings, bootstrap_receipt=bootstrap,
                              official_source=SimpleNamespace(receipt=lambda: original))
    acceptance = receipt.make(catalog, publisher, 'global')
    text = 'Generation 0, row 2.'
    return {'format': 2, 'game': 'genshin', 'source_locale': 'en', 'fingerprint': publisher,
        'metadata_revision': revision, 'publisher_region': 'global', 'source_receipt': acceptance,
        'records': [{'text_id': 'genshin:authored:2', 'source_locale': 'en', 'source_text': text,
            'texts': {'en': text}, 'english': text, 'chinese': '', 'audio_locale': 'en',
            'audio': None, 'voice_status': 'unvoiced', 'dialogue_kind': 'conversation'}]}


def validate(payload):
    return receipt.validate(payload['source_receipt'], publisher=payload['fingerprint'],
                            region=payload['publisher_region'], metadata_revision=payload['metadata_revision'])


def manual_snapshot():
    from backend.genshin_original_excel import MANUAL_PATH, metadata_name
    from backend.genshin_original_containers import asset_identity
    payload = snapshot()
    source = payload['source_receipt']['original_text']; native = source['native']
    source['codec_description'] = {'policy': 'official-native-blb-parameters-v1',
        'native_sha256': native['sha256'], 'publisher_md5': native['publisher_md5'], 'bytes': native['bytes'],
        'reader_sha256': '1' * 64, 'method_sha256s': ['2' * 64], 'parameters_sha256': '3' * 64,
        'semantic_owner_claim': False}
    owner = {'publisher': payload['fingerprint'], 'native_sha256': native['sha256'],
        'metadata': {'name': metadata_name('genshin-global'), 'publisher_md5': '4' * 32, 'sha256': '5' * 64, 'bytes': 2048},
        'manifest_sha256': hashlib.sha256(json.dumps(source['publisher_descriptor']['manifests']['game'],
            sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'software_sha256': {name: '6' * 64 for name in ('genshin_original_excel.py', 'genshin_original_dialogue.py',
            'genshin_native_words.py', 'genshin_native_contracts.py')},
        'asset_index': asset_identity(MANUAL_PATH), 'bundle': 7,
        'payload_sha256': '7' * 64, 'catalog_sha256': source['catalog_sha256']}
    proof = {'schema': 'genshin-original-manual-table-v1', 'strict_eof': True, 'source_kind': 'original-publisher',
        'rows': 2, 'payload_sha256': '7' * 64, 'payload_bytes': 100, 'canonical_sha256': '8' * 64,
        'contract_sha256': '9' * 64, 'method_sha256s': ['a' * 64, 'b' * 64, 'c' * 64]}
    source['original_tables'] = {'ManualTextMapConfigData': {'owner': owner, 'proof': proof}}
    payload['source_receipt']['coverage']['ManualTextMap'] = 'original-publisher'
    rehash(payload['source_receipt'])
    return payload


@pytest.mark.parametrize('change', [None, 'metadata-edition', 'metadata-size', 'metadata-digest', 'manifest',
    'native-input', 'asset', 'duplicate-method', 'software-path', 'boolean-count', 'eof', 'coverage'])
def test_original_manual_receipt_binds_metadata_native_catalog_and_complete_table(change):
    payload = manual_snapshot()
    table = payload['source_receipt']['original_text']['original_tables']['ManualTextMapConfigData']
    owner, proof = table['owner'], table['proof']
    if change == 'metadata-edition': owner['metadata']['name'] = owner['metadata']['name'].replace('GenshinImpact', 'YuanShen')
    elif change == 'metadata-size': owner['metadata']['bytes'] = 0
    elif change == 'metadata-digest': owner['metadata']['publisher_md5'] = 'unknown'
    elif change == 'manifest': owner['manifest_sha256'] = '0' * 64
    elif change == 'native-input': owner['native_sha256'] = '0' * 64
    elif change == 'asset': owner['asset_index'] += 1
    elif change == 'duplicate-method': proof['method_sha256s'].append(proof['method_sha256s'][0])
    elif change == 'software-path': owner['software_sha256']['../unowned.py'] = '1' * 64
    elif change == 'boolean-count': proof['rows'] = True
    elif change == 'eof': proof['strict_eof'] = False
    elif change == 'coverage': payload['source_receipt']['coverage'].pop('ManualTextMap')
    rehash(payload['source_receipt'])
    if change is None:
        assert validate(payload)['coverage']['ManualTextMap'] == 'original-publisher'
    else:
        with pytest.raises(ValueError): validate(payload)


@pytest.mark.parametrize('change', [None, 'native-input', 'publisher-md5', 'bytes', 'methods', 'reader', 'policy'])
def test_original_native_codec_receipt_reopens_and_rejects_cross_input_changes(change):
    payload = snapshot()
    source = payload['source_receipt']['original_text']
    owner = source['native']
    source['codec_description'] = {'policy': 'official-native-blb-parameters-v1',
        'native_sha256': owner['sha256'], 'publisher_md5': owner['publisher_md5'], 'bytes': owner['bytes'],
        'reader_sha256': '1' * 64, 'method_sha256s': ['2' * 64, '3' * 64],
        'parameters_sha256': '4' * 64, 'semantic_owner_claim': False}
    codec = source['codec_description']
    if change == 'native-input': codec['native_sha256'] = '9' * 64
    elif change == 'publisher-md5': codec['publisher_md5'] = '9' * 32
    elif change == 'bytes': codec['bytes'] += 1
    elif change == 'methods': codec['method_sha256s'].append(codec['method_sha256s'][0])
    elif change == 'reader': codec['reader_sha256'] = 'moving-branch'
    elif change == 'policy': codec['policy'] = 'community-data-relabeled-official'
    rehash(payload['source_receipt'])
    if change is None:
        assert validate(payload)['original_text']['codec_description'] == codec
    else:
        with pytest.raises(ValueError): validate(payload)


@pytest.mark.parametrize('change', ['title', 'edition', 'stale-hotfix', 'wrong-game', 'helper-region',
    'helper-revision', 'unapproved-source', 'codec-source', 'native-contract', 'missing-shard', 'source-label'])
def test_rehashed_wrong_source_and_generation_receipts_cannot_be_accepted(change):
    payload = snapshot()
    source = payload['source_receipt']
    if change == 'title': source['bindings']['title'] = 'OSRELWin9.4.0_R1_S2_D4'
    elif change == 'edition': source['bindings']['region'] = 'cn'
    elif change == 'stale-hotfix':
        source['bindings']['markers']['design'] = '4'; source['bindings']['title'] = 'OSRELWin9.4.0_R1_S2_D4'
    elif change == 'wrong-game': source['bootstrap']['game'] = 'zzz'
    elif change == 'helper-region': source['bootstrap']['region'] = 'cn'
    elif change == 'helper-revision': source['bootstrap']['revision'] = 'master'
    elif change == 'unapproved-source': source['bindings']['repository'] = 'unapproved/metadata'
    elif change == 'codec-source': source['original_text']['codec_description']['repository'] = 'unapproved/code'
    elif change == 'native-contract': source['original_text']['native']['parameters_sha256'] = '9' * 64
    elif change == 'missing-shard': source['original_text']['locales']['EN']['shards'].pop()
    else: source['coverage']['Readable'] = 'original-publisher'
    rehash(source)
    with pytest.raises(ValueError):
        validate(payload)


@pytest.mark.parametrize('original_table', [False, True])
def test_worker_failed_receipt_retains_prior_file_then_successful_retry_reopens_offline(tmp_path, monkeypatch, original_table):
    monkeypatch.setattr(language_worker, 'asset_adapter', lambda _: (SimpleNamespace(LANGUAGE_INDEX_VERSION=19), None))
    path = tmp_path / 'textmap.json'
    factory = manual_snapshot if original_table else snapshot
    old = factory()
    language_worker.write_payload('genshin', old, 'en', (), path)
    before = path.read_bytes()
    current = copy.deepcopy(old)
    current['source_receipt']['bindings']['title'] = 'wrong title'
    rehash(current['source_receipt'])
    with pytest.raises(ValueError):
        language_worker.write_payload('genshin', current, 'en', (), path)
    assert path.read_bytes() == before
    language_worker.write_payload('genshin', factory(), 'en', (), path)
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Offline reopen contacted a publisher'))
    index = MultilingualTextIndex('genshin', tmp_path)
    assert index.ready and index.snapshot_metadata['source_receipt']['sha256'] == old['source_receipt']['sha256']
    broken = snapshot(); broken['source_receipt']['sha256'] = '0' * 64
    path.write_text(json.dumps(broken), encoding='utf-8')
    assert not index.load() and index.ready
    assert index.snapshot_metadata['source_receipt']['sha256'] == old['source_receipt']['sha256']


def test_legacy_offline_snapshot_is_preserved_without_new_official_provenance(tmp_path):
    payload = snapshot(); del payload['source_receipt']
    (tmp_path / 'textmap.json').write_text(json.dumps(payload), encoding='utf-8')
    index = MultilingualTextIndex('genshin', tmp_path)
    assert index.ready and 'source_receipt' not in index.snapshot_metadata
