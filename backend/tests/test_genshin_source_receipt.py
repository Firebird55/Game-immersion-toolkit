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


def test_worker_failed_receipt_retains_prior_file_then_successful_retry_reopens_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(language_worker, 'asset_adapter', lambda _: (SimpleNamespace(LANGUAGE_INDEX_VERSION=19), None))
    path = tmp_path / 'textmap.json'
    old = snapshot()
    language_worker.write_payload('genshin', old, 'en', (), path)
    before = path.read_bytes()
    current = copy.deepcopy(old)
    current['source_receipt']['bindings']['title'] = 'wrong title'
    rehash(current['source_receipt'])
    with pytest.raises(ValueError):
        language_worker.write_payload('genshin', current, 'en', (), path)
    assert path.read_bytes() == before
    language_worker.write_payload('genshin', snapshot(), 'en', (), path)
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
