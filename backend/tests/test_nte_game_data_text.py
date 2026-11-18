"""Actual service/transport/text writer with authored original-format fixtures.

Native acceptance uses a model seam here; complete original-client acceptance
is independently exercised by retained-source ordinary worker trials.
"""
import hashlib
import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest

from backend import nte_assets as assets, nte_native_metadata as native, nte_native_provider as provider
from backend import nte_game_data_runtime as runtime, nte_game_data_text as text
from backend.game_data_protocol import GameDataRequest
from backend.tests.test_nte_game_data_content import Originals
from backend.tests.test_nte_game_data import REQUEST, finish
from backend.tests.test_nte_dialogue_graph import fixture as graphs, NAMESPACES
from backend.tests.test_nte_seeded_schema import seed
from backend import nte_updater_source as updater


def setup(tmp_path, monkeypatch, locale='ja'):
    original = Originals(tmp_path, monkeypatch, selected_metadata=True, processing=True, study_locale=locale)
    mapping = seed([]); digest = hashlib.sha256(mapping).hexdigest()
    monkeypatch.setattr(assets, 'TABLE_SCHEMA_SHA256', digest)
    monkeypatch.setattr(native, 'SEED_SHA256', digest)
    cache = original.root/'nte/cache/tools/nte-publisher'
    (cache/'native-seed').mkdir(); (cache/'native-seed'/(digest+'.usmap')).write_bytes(mapping)
    def inventory(self, source, destination, operation, request, **kwargs):
        assert operation == 'publisher-dialogue-inventory'
        raw = (destination/'dialogue-registry.bin').read_bytes()
        value = {'schema': 'nte-original-dialogue-inventory-v2', 'complete': True, 'nonce': request['inventory_nonce'],
            'registry_sha256': hashlib.sha256(raw).hexdigest(), 'registry_bytes': len(raw), 'registry_eof_verified': True,
            'package_count': 1, 'packages': {'HT/Content/a.uasset': 80}}
        (destination/'dialogue-inventory.json').write_text(json.dumps(value))
        return CompletedProcess(['owned-model'], 0)
    monkeypatch.setattr(runtime.NteGameDataReader, 'execute', inventory)
    reference = {'native_generator': native.CLASS_GENERATOR, 'generation': 'a'*64, 'sha256': digest}
    candidates = {}
    def authoring(catalog, executable, staging, progress, *, game_data_reader):
        outputs = {'dialogue-events.json': {'owned': ['play_vo_owned']}, 'voice-events.json': ['Play_Vo_owned'],
            'sequence-cues.json': {'events': {}, 'groups': {}},
            'movie-tables.json': {'OriginalMovieTables.json': ['Movie.json'],
                'StringTableNamespaces.json': {'Movie': 'Other_Movie_Namespace'},
                'Movie.json': [{'Type': 'DataTable', 'Rows': {'Scene': {'StringTableID': 'Movie',
                    'Path': {'FilePath': '../../../Projects/HT/Content/Movies/FFMpeg/Story/owned.mp4'},
                    'PlayVoice': {'AssetPathName': '/Game/WwiseAudio/Events/CG/Owned/Play_Vo_Scene.Play_Vo_Scene'}}}}]},
            'dialogue-graphs.json': {'schema': 'nte-original-dialogue-graphs-v1', 'graph_count': 1,
                'graphs': graphs(), 'namespaces': NAMESPACES}, 'original-authoring.json': {'owned': 'model'}}
        for name, value in outputs.items(): (staging/name).write_text(json.dumps(value), encoding='utf-8')
        (staging/'dialogue.usmap').write_bytes(mapping)
        validation = {'schema': reference, 'required_schema_eligible': True, 'reader_sha256': game_data_reader.source_identity}
        raw = native._json(validation); identity = hashlib.sha256(raw).hexdigest()
        path = cache/'native-candidates/validations'/(identity+'.json'); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        candidates[reference['generation']] = SimpleNamespace(receipt={
            'dependencies': {'reader': game_data_reader.source_identity},
            'source_manifest_sha256': hashlib.sha256(native._json(provider.discovery(catalog.snapshot))).hexdigest()})
        return reference, identity
    monkeypatch.setattr(provider, 'read_authoring', authoring)
    monkeypatch.setattr(native, 'load', lambda reference, _cache: candidates[reference['generation']])
    request = {**REQUEST, 'source_locale': locale, 'target_locales': ['en' if locale != 'en' else 'zh-Hans']}
    return original, request


@pytest.mark.parametrize('locale', ['en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'])
def test_normal_text_service_finishes_and_restores_each_study_locale_without_audio(tmp_path, monkeypatch, locale):
    original, request = setup(tmp_path, monkeypatch, locale)
    service = original.service()
    monkeypatch.setattr(assets, 'read_bank_play_layers', lambda *_a, **_k: pytest.fail('Text source parsed a voice bank'))
    try:
        for _ in range(14):
            plan = service.plan('nte', request)['game']; assert plan['can_download']
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
            state = finish(service)
            if state['job']['status'] == 'complete': break
            assert state['job']['status'] == 'needs_plan', state
        else: pytest.fail('Authored text source did not complete')
        restored = service.restore('nte')
        payload = json.loads(restored.snapshot_path.read_bytes())
        assert restored.voice_source is None and payload['content_mode'] == 'text'
        assert payload['source_locale'] == locale and payload['missing_translation_locales'] == []
        assert len(payload['records']) == 1
        row = payload['records'][0]
        assert row['audio'] is None and row['audio_omitted_by_request'] is True
        assert row['voice_status'] == 'unknown' and row['text_capture_verified'] is True
        assert request['target_locales'][0] in row['texts']
    finally: service.close()


def test_authored_subtitle_quote_uses_only_indices_and_retains_source_on_bad_block(tmp_path, monkeypatch):
    original, request = setup(tmp_path, monkeypatch)
    service = original.service()
    try:
        for _ in range(14):
            plan = service.plan('nte', request)['game']
            owned = service.plans[plan['plan_id']]['plan']
            if owned.stage == 'authored-subtitle-ranges': break
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
            assert finish(service)['job']['status'] == 'needs_plan'
        else: pytest.fail('Authored source did not quote its subtitles')
        ctx = SimpleNamespace(cache_directory=original.root/'nte/cache', request=GameDataRequest.parse(request), check=lambda: None)
        reader = runtime.resolve('windows', ctx)
        recipe = owned.handle['text_recipe']
        _, _, _, _, _, members, sources, _, _ = text._parts(recipe['owner'], recipe['authoring_receipt'], ctx, reader)
        row = members[0]; index = row['offset']//65536; source = sources[row['pak']]
        assert source._cached(index) is None
        from backend import nte_publisher_pak as pak
        monkeypatch.setattr(pak.Archive, 'read', lambda *_a: pytest.fail('Subtitle planning read a member body'))
        monkeypatch.setattr(pak.Archive, '_parts', lambda *_a: pytest.fail('Subtitle planning decoded a member'))
        plan = service.plan('nte', request)['game']
        assert service.plans[plan['plan_id']]['plan'].stage == 'authored-subtitle-ranges'
        previous = (original.root/'nte/stage.json').read_bytes()
        original.corrupt = True
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        state = finish(service)
        assert state['job']['status'] == 'failed' and (original.root/'nte/stage.json').read_bytes() == previous
        assert not (source.root/(str(index)+'.chunk')).exists()
        assert not (original.root/'nte/current.json').exists()
    finally: service.close()


def test_text_service_keeps_the_complete_source_on_final_source_change_and_interruption(tmp_path, monkeypatch):
    original, request = setup(tmp_path, monkeypatch)
    service = original.service()
    def download(plan):
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        return finish(service)['job']
    try:
        for _ in range(14):
            plan = service.plan('nte', request)['game']
            job = download(plan)
            if job['status'] == 'complete': break
            assert job['status'] == 'needs_plan'
        else: pytest.fail('Authored text source did not complete')
        old = (original.root/'nte/current.json').read_bytes()
        source = service.restore('nte')
        plan = service.plan('nte', request)['game']
        assert service.plans[plan['plan_id']]['plan'].stage == 'normalize-text'
        previous = original.metadata[updater.VERSION_URL]
        recheck = text._recheck; calls = []
        def changed_final(*args):
            calls.append(True)
            if len(calls) == 2: original.metadata[updater.VERSION_URL] += b'!'
            return recheck(*args)
        with monkeypatch.context() as fault:
            fault.setattr(text, '_recheck', changed_final)
            assert download(plan)['status'] == 'failed'
        original.metadata[updater.VERSION_URL] = previous
        assert len(calls) == 2 and (original.root/'nte/current.json').read_bytes() == old
        assert service.restore('nte').restore_handle == source.restore_handle
        atomic = text._atomic_file
        def interrupted(path, raw):
            if path.name == 'nte-source-receipt.json': raise OSError('Authored publication interruption')
            return atomic(path, raw)
        plan = service.plan('nte', request)['game']
        with monkeypatch.context() as fault:
            fault.setattr(text, '_atomic_file', interrupted)
            assert download(plan)['status'] == 'failed'
        assert (original.root/'nte/current.json').read_bytes() == old
        assert service.restore('nte').restore_handle == source.restore_handle
        assert download(service.plan('nte', request)['game'])['status'] == 'complete'
        assert service.restore('nte').restore_handle == source.restore_handle
        assert (original.root/'nte/current.json').read_bytes() == old
    finally: service.close()
