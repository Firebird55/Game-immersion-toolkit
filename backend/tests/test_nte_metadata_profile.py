"""Immutable hybrid approval must bind the actual original and prepared rows."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import nte_metadata_profile as profiles, nte_community_metadata as community
from backend import nte_native_provider as provider, nte_native_metadata as metadata, nte_release as release
from backend.preparation_errors import PreparationFailure


def fixture(tmp_path, monkeypatch, *, text='Owned caption'):
    tools = tmp_path/'tools'; cache = tools/'nte-publisher'
    # Use the actual manifest File shape, including original section names.
    from dataclasses import asdict
    native_file = asdict(release.File(123, 'a'*32, 123, 'a'*32, 0))
    archive = asdict(release.File(234, 'b'*32, 234, 'b'*32, 0))
    signature = asdict(release.File(56, 'c'*32, 56, 'c'*32, 0))
    files = {'Client/WindowsNoEditor/HT/Content/Paks/owned.pak': archive,
             'Client/WindowsNoEditor/HT/Content/Paks/owned.sig': signature}
    recipe = {'schema': 1, 'region': 'nte-global', 'branch': 'PC_150', 'version': '1.5.4',
              'sections': {}, 'files': files, 'publisher_files': {**files, 'Client/Owned.exe': native_file},
              'reader': 'd'*64, 'metadata_policy': profiles.policy()}
    source = b'owned frozen localization description'
    recipe['localization'] = ['a'*40, hashlib.sha256(source).hexdigest()]
    path = cache/'format'/('-'.join(recipe['localization'])+'.txt')
    path.parent.mkdir(parents=True); path.write_bytes(source)
    inventory = hashlib.sha256(metadata._json(provider.discovery(recipe))).hexdigest()
    original = {key: recipe[key] for key in ('region', 'branch', 'version')} | {'sha256': inventory}
    candidate = community.retain('archive', 'b'*40, hashlib.sha256(b'owned keys').hexdigest(),
                                 b'owned keys', cache/'format/community')
    plain = b'complete checked original index'
    proof = community.remember(candidate, original, 'archive-index', plain, cache/'format/community')
    binding = {'archive': archive, 'signature': signature, 'guid': '0'*32,
               'index_sha256': hashlib.sha256(plain).hexdigest(), 'metadata': proof, 'key_sha256': 'e'*64}
    text_candidate = community.retain('localization', recipe['localization'][0], recipe['localization'][1],
                                     source, cache/'format/community')
    text_proof = community.remember(text_candidate, original, 'localization', b'original text member', cache/'format/community')
    materials = {'archive': {archive['digest']: binding}, 'localization': {
                     'HT/Content/Localization/Game/ja/Game.locres': {
                         'archive': next(iter(files)), 'member_sha256': hashlib.sha256(b'original text member').hexdigest(),
                         'metadata': text_proof, 'key_required': True}},
                 'updater': {'global': list(release.GLOBAL_FORMAT)}}
    schema = {'native_generator': 'owned-native-v1', 'generation': 'f'*64, 'sha256': '9'*64}
    candidate_receipt = {'native_sha256': '8'*64, 'source_manifest_sha256': inventory,
                         'dependencies': {'reader': recipe['reader']}, 'native_path': 'Client/Owned.exe',
                         'native_file': native_file}
    monkeypatch.setattr(metadata, 'load', lambda actual, _cache: (
        SimpleNamespace(receipt=candidate_receipt) if actual == schema else
        (_ for _ in ()).throw(ValueError('Wrong candidate'))))
    report = {'required_schema_eligible': True, 'schema': schema, 'reader_sha256': recipe['reader'],
              'report': {'client_sha256': candidate_receipt['native_sha256'], 'schema_sha256': schema['sha256']}}
    raw = profiles._json(report); validation = hashlib.sha256(raw).hexdigest()
    path = cache/'native-candidates/validations'/(validation+'.json')
    path.parent.mkdir(parents=True); path.write_bytes(raw)
    native = profiles.native_evidence(recipe, (schema, validation), cache)
    recipe_id = 'nte-'+hashlib.sha256(profiles._json(recipe)).hexdigest()
    payload = {'format': 2, 'game': 'nte', 'install': None, 'source_mode': 'publisher', 'source_region': 'global',
               'source_locale': 'ja', 'fingerprint': recipe_id,
               'records': [{'text_id': 'owned:1', 'source_locale': 'ja', 'source_text': text,
                            'texts': {'ja': text, 'en': 'Owned'}, 'audio_locale': 'ja',
                            'english': 'Owned', 'chinese': '',
                            'audio': {'publisher': recipe_id, 'locale': 'ja',
                                      'depot': 'HT/Content/WwiseAudio/Media/Japanese/1.wem',
                                      'archive': next(iter(files))}}]}
    return tools, recipe_id, recipe, payload, native, materials


def materialize(args):
    tools, recipe_id, recipe, payload, native, materials = args
    stamp = profiles.publish(tools, recipe_id, recipe, payload, native, materials)
    payload = copy.deepcopy(payload); payload['publisher_snapshot'] = stamp
    for row in payload['records']:
        if row.get('audio'): row['audio']['publisher'] = stamp
    header = json.loads((tools/'nte-publisher'/stamp/'release.json').read_bytes())
    profile = profiles.load(tools, stamp, header, recipe)
    profiles.validate_payload(payload, profile, header, stamp)
    return stamp, header, profile, payload


def test_materialization_and_derived_index_fields_preserve_opaque_identity_offline(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    stamp, header, profile, payload = materialize(args)
    monkeypatch.setattr(community, 'download', lambda *_: pytest.fail('Historical latest lookup'))
    row = payload['records'][0]
    row.update(voice_status='voiced', audio_scope='line', channels=['tip', 'gameplay', 'dialogue', 'cinematic'])
    profiles.validate_payload(payload, profile, header, stamp)
    assert profiles.portable_snapshot(payload)['fingerprint'] == stamp
    assert stamp != args[1]
    assert profiles.load(args[0], stamp, header, args[2]) == profile


@pytest.mark.parametrize('mutation', ['text', 'translation', 'source', 'audio', 'provisional', 'locale'])
def test_wrong_dataset_or_provisional_audio_cannot_use_approval(tmp_path, monkeypatch, mutation):
    args = fixture(tmp_path, monkeypatch)
    stamp, header, profile, payload = materialize(args)
    row = payload['records'][0]
    if mutation == 'text': row['source_text'] += ' changed'
    if mutation == 'translation': row['texts']['en'] = 'Changed'
    if mutation == 'source': row['audio']['depot'] = 'HT/Content/other.wem'
    if mutation == 'audio': row['audio']['publisher'] = 'nte-'+'1'*64
    if mutation == 'provisional': row['audio']['publisher'] = args[1]
    if mutation == 'locale': payload['source_locale'] = 'en'
    with pytest.raises(PreparationFailure): profiles.validate_payload(payload, profile, header, stamp)


@pytest.mark.parametrize('part', ['profile', 'receipt', 'source', 'validation'])
def test_missing_or_swapped_desktop_evidence_fails_without_latest(tmp_path, monkeypatch, part):
    args = fixture(tmp_path, monkeypatch)
    stamp, header, _, _ = materialize(args)
    tools, _, recipe, _, native, materials = args
    root = tools/'nte-publisher'
    paths = {'profile': root/'metadata-profiles'/(header['profile_sha256']+'.json'),
             'receipt': root/'metadata-profiles/receipts'/(header['receipt_sha256']+'.json'),
             'source': root/'format/community/sources/archive'/
                       (next(iter(materials['archive'].values()))['metadata']['source']['sha256']+'.data'),
             'validation': root/'native-candidates/validations'/(native['validation_sha256']+'.json')}
    monkeypatch.setattr(community, 'download', lambda *_: pytest.fail('Missing historical proof queried latest'))
    path = paths[part]; original = path.read_bytes(); path.write_bytes(b'{}')
    with pytest.raises((ValueError, OSError)): profiles.load(tools, stamp, header, recipe)
    path.unlink()
    with pytest.raises((ValueError, OSError)): profiles.load(tools, stamp, header, recipe)
    path.write_bytes(original)
    profiles.load(tools, stamp, header, recipe)


@pytest.mark.parametrize('part', ['recipe', 'reader', 'native', 'inventory'])
def test_swapped_original_ownership_cannot_publish(tmp_path, monkeypatch, part):
    args = list(fixture(tmp_path, monkeypatch)); native = args[4]
    if part == 'recipe': args[2]['version'] = '1.5.5'
    if part == 'reader': native['reader_sha256'] = '1'*64
    if part == 'native': native['native_sha256'] = '1'*64
    if part == 'inventory': native['inventory_sha256'] = '1'*64
    with pytest.raises((ValueError, OSError)): profiles.publish(*args)
    assert not list((args[0]/'nte-publisher').glob('nte-*/release.json'))


def test_interrupted_marker_publication_retains_old_and_retry_is_identical(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    old, header, old_profile, _ = materialize(args)
    args[3]['records'][0]['texts']['en'] = 'New original revision translation'
    original_publish = profiles._publish
    def interrupted(path, raw):
        if path.name == 'release.json': raise OSError('Interrupted before completed marker')
        original_publish(path, raw)
    monkeypatch.setattr(profiles, '_publish', interrupted)
    with pytest.raises(OSError): profiles.publish(*args)
    assert profiles.load(args[0], old, header, args[2]) == old_profile
    assert len(list((args[0]/'nte-publisher').glob('nte-*/release.json'))) == 1
    monkeypatch.setattr(profiles, '_publish', original_publish)
    new = profiles.publish(*args)
    assert new != old and profiles.publish(*args) == new
    assert profiles.load(args[0], old, header, args[2]) == old_profile


def test_existing_voice_service_never_degrades_missing_approval_to_recipe_playback(tmp_path, monkeypatch):
    from backend import local_voice, nte_publisher as publisher
    args = fixture(tmp_path, monkeypatch)
    stamp, header, _, payload = materialize(args)
    tools, recipe_id, recipe, *_ = args
    path = tools/'nte-publisher'/recipe_id/'release.json'
    path.parent.mkdir(parents=True); path.write_bytes(profiles._json(recipe))
    data = tmp_path/'language'; data.mkdir()
    (data/'textmap.json').write_text(json.dumps(payload), encoding='utf-8')
    adapter = SimpleNamespace(publisher_snapshot_available=publisher.snapshot_available,
                              extract_voice=lambda *_: pytest.fail('Unapproved voice extraction'))
    monkeypatch.setattr(local_voice, 'asset_adapter', lambda _: (adapter, ''))
    monkeypatch.setattr(local_voice, 'ffmpeg_executable', lambda: 'unused encoder')
    monkeypatch.setattr(local_voice.LocalVoiceAssetService, 'decoder_available', lambda _: True)
    service = local_voice.LocalVoiceAssetService('nte', data, None, tmp_path/'clips', tools_dir=tools)
    try:
        assert service.ready and service._fingerprint == stamp
        assert publisher.snapshot_available(tools, recipe_id) is False
        receipt = tools/'nte-publisher/metadata-profiles/receipts'/(header['receipt_sha256']+'.json')
        before = receipt.read_bytes(); receipt.unlink()
        assert not service.reload() and not service.ready
        with pytest.raises(ValueError, match='Compatible NTE information'):
            service.extract('owned:1', 1)
        receipt.write_bytes(before)
        assert service.reload() and service._fingerprint == stamp
    finally:
        service.close()


def test_cached_catalog_cannot_bypass_missing_materialized_approval(tmp_path, monkeypatch):
    from backend import nte_publisher as publisher
    args = fixture(tmp_path, monkeypatch)
    stamp, header, _, payload = materialize(args)
    tools, recipe_id, recipe, *_ = args
    path = tools/'nte-publisher'/recipe_id/'release.json'
    path.parent.mkdir(parents=True); path.write_bytes(profiles._json(recipe))
    audio = payload['records'][0]['audio']
    data = b'RIFF'+(28).to_bytes(4, 'little')+b'WAVE'+bytes(24)
    calls = []
    catalog = SimpleNamespace(location=lambda _: (audio['archive'], None, audio['depot']),
                              read=lambda _: calls.append('read') or data)
    monkeypatch.setattr(publisher, '_voices', lambda *_: catalog)
    assert publisher.extract(tools, audio) == data and calls == ['read']
    (tools/'nte-publisher/metadata-profiles/receipts'/(header['receipt_sha256']+'.json')).unlink()
    with pytest.raises(PreparationFailure): publisher.extract(tools, audio)
    assert calls == ['read']


def test_real_index_normalization_preserves_the_desktop_activation_approval(tmp_path, monkeypatch):
    from backend.multilingual_index import MultilingualTextIndex
    from backend import nte_publisher as publisher
    args = fixture(tmp_path, monkeypatch)
    stamp, _, _, payload = materialize(args)
    tools, recipe_id, recipe, *_ = args
    path = tools/'nte-publisher'/recipe_id/'release.json'
    path.parent.mkdir(parents=True); path.write_bytes(profiles._json(recipe))
    directory = tmp_path/'language'; directory.mkdir()
    (directory/'textmap.json').write_text(json.dumps(payload), encoding='utf-8')
    index = MultilingualTextIndex('nte', directory)
    assert index.ready, index.message
    candidate = {**index.snapshot_metadata, 'records': index._records}
    publisher.validate_prepared(tools, candidate)
    assert candidate['publisher_snapshot'] == stamp and candidate['fingerprint'] == recipe_id
    index._records[0]['audio']['publisher'] = recipe_id
    with pytest.raises(PreparationFailure): publisher.validate_prepared(tools, candidate)


def test_text_mode_approval_binds_omission_and_nonplayable_authored_source(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    payload = args[3]
    payload['content_mode'] = 'text'
    row = payload['records'][0]
    row.update(audio=None, voice_status='voiced', audio_omitted_by_request=True,
               source_voice_binding={'event': 'Play_Vo_Owned', 'locale': 'ja'},
               text_capture_verified=True)
    stamp, header, profile, materialized = materialize(args)
    assert materialized['records'][0]['audio'] is None
    assert materialized['records'][0]['voice_status'] == 'voiced'
    changed = copy.deepcopy(materialized)
    changed['content_mode'] = 'text-audio'
    with pytest.raises(PreparationFailure): profiles.validate_payload(changed, profile, header, stamp)
    changed = copy.deepcopy(materialized)
    changed['records'][0]['source_voice_binding']['locale'] = 'en'
    with pytest.raises(PreparationFailure): profiles.validate_payload(changed, profile, header, stamp)


def test_new_consumer_defaults_do_not_mutate_an_existing_audio_approval(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    stamp, header, profile, payload = materialize(args)
    payload['content_mode'] = 'text-audio'
    payload['records'][0].update(audio_omitted_by_request=False, source_voice_binding=None)
    profiles.validate_payload(payload, profile, header, stamp)


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_profile_publication_rejects_mode_and_playback_disagreement(tmp_path, monkeypatch, mode):
    args = fixture(tmp_path, monkeypatch)
    args[3]['content_mode'] = mode
    if mode == 'text-audio':
        args[3]['records'][0].update(audio=None, voice_status='voiced', audio_omitted_by_request=True,
                                     source_voice_binding={'event': 'Play_Vo_Owned'})
    with pytest.raises(PreparationFailure): profiles.publish(*args)
    assert not list((args[0]/'nte-publisher').glob('nte-*/release.json'))
