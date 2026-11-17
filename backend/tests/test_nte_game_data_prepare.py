"""Real zero-byte service jobs with authored binary locres and reader replies.

Native ABI/EOF behavior is covered separately by compiled owned bridge fixtures
and retained original-registry probes; no fake native acceptance is claimed here.
"""
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import nte_game_data_runtime as runtime, nte_game_data
from backend.tests.test_nte_game_data_content import Originals
from backend.tests.test_nte_game_data import REQUEST, finish


@pytest.mark.parametrize('fault', [None, 'text-eof', 'registry-eof', 'nonce', 'publication'])
def test_zero_transfer_processing_verifies_metadata_without_constructing_http(tmp_path, monkeypatch, fault):
    original = Originals(tmp_path, monkeypatch, selected_metadata=True, processing=True, text_tail=fault == 'text-eof')
    service = original.service(); executions = []
    def execute(self, source, destination, operation, request, *, timeout):
        assert operation == 'publisher-dialogue-inventory' and request['require_registry_eof'] is True
        assert request['capture_original_authoring'] is True and timeout == 180
        registry = (destination/'dialogue-registry.bin').read_bytes()
        assert hashlib.sha256(registry).hexdigest() == request['dialogue_registry_sha256']
        executions.append(True)
        packet = {'schema': 'nte-original-dialogue-inventory-v2', 'complete': True,
            'registry_sha256': request['dialogue_registry_sha256'], 'registry_bytes': len(registry),
            'registry_eof_verified': fault != 'registry-eof',
            'nonce': '0'*32 if fault == 'nonce' else request['inventory_nonce'],
            'package_count': 1, 'packages': {'HT/Content/a.uasset': 80}}
        (destination/'dialogue-inventory.json').write_text(json.dumps(packet))
        from subprocess import CompletedProcess
        return CompletedProcess(['owned'], 0)
    monkeypatch.setattr(runtime.NteGameDataReader, 'execute', execute)
    try:
        for _ in range(10):
            plan = service.plan('nte', REQUEST)['game']
            stage = service.plans[plan['plan_id']]['plan'].stage
            if stage == 'process-metadata': break
            assert plan['can_download']
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
            assert finish(service)['job']['status'] == 'needs_plan'
        else: pytest.fail('Acquired metadata did not reach processing')
        assert plan['can_download'] and plan['download_bytes'] == 0
        previous = (original.root/'nte/stage.json').read_bytes()
        original.forbid_all_http = True
        monkeypatch.setattr(nte_game_data, 'PublisherTransport', lambda *_a, **_k: pytest.fail('Zero-byte job constructed HTTP transport'))
        from backend import nte_game_data_prepare as processing
        if fault == 'publication':
            publish = processing._atomic_file
            def interrupted(path, data):
                if path.name == processing.content._identity(service.plans[plan['plan_id']]['plan'].handle)+'.json':
                    raise OSError('Authored interruption before metadata receipt pointer')
                return publish(path, data)
            monkeypatch.setattr(processing, '_atomic_file', interrupted)
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        state = finish(service)
        if fault:
            assert state['job']['status'] == 'failed'
            assert (original.root/'nte/stage.json').read_bytes() == previous
        else:
            assert state['job']['status'] == 'needs_plan' and state['job']['downloaded_bytes'] == 0
            receipt = json.loads((original.root/'nte/stage.json').read_bytes())['handle']
            assert receipt['registry_eof_verified'] is True and receipt['transferred_bytes'] == 0
            assert len(receipt['receipt']) == 64
            ctx = SimpleNamespace(cache_directory=original.root/'nte/cache')
            recipe = service.plans[plan['plan_id']]['plan'].handle
            verified = processing._read(recipe, ctx)
            assert verified is not None
            wrong_recipe = json.loads(json.dumps(recipe)); wrong_recipe['reader']['source_sha256'] = '0'*64
            assert processing._read(wrong_recipe, ctx) is None
            pointer = processing._base(ctx)/(processing.content._identity(recipe)+'.json')
            saved = pointer.read_bytes()
            pointer.write_text(json.dumps({'recipe': processing.content._identity(recipe), 'receipt': '0'*64}))
            assert processing._read(recipe, ctx) is None
            pointer.write_bytes(saved)
            owner = verified['root']; source_receipt = json.loads((owner/'receipt.json').read_bytes())
            source_receipt['recipe'] = '0'*64
            forged = processing._json(source_receipt); identity = hashlib.sha256(forged).hexdigest()
            swapped = processing._base(ctx)/'objects'/identity; swapped.mkdir()
            for filename in ('localization.json', 'dialogue-inventory.json'):
                (swapped/filename).write_bytes((owner/filename).read_bytes())
            (swapped/'receipt.json').write_bytes(forged)
            pointer.write_text(json.dumps({'recipe': processing.content._identity(recipe), 'receipt': identity}))
            assert processing._read(recipe, ctx) is None
            pointer.write_bytes(saved)
            assert processing._read(recipe, ctx)['receipt'] == verified['receipt']
        assert bool(executions) == (fault != 'text-eof')
        assert not (original.root/'nte/current.json').exists()
    finally: service.close()
