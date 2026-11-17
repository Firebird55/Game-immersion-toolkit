"""Acquired original metadata receipts may quote only matching TOC packages."""
import hashlib
import json
from subprocess import CompletedProcess

import pytest

from backend import nte_game_data_runtime as runtime
from backend.tests.test_nte_game_data_content import Originals
from backend.tests.test_nte_game_data import REQUEST, finish


@pytest.mark.parametrize('corrupt', [False, True])
def test_normal_receipt_to_package_range_stage_keeps_checksum_and_no_ready_boundary(tmp_path, monkeypatch, corrupt):
    original = Originals(tmp_path, monkeypatch, selected_metadata=True, processing=True)
    service = original.service()
    def execute(self, source, destination, operation, request, **kwargs):
        raw = (destination/'dialogue-registry.bin').read_bytes()
        assert request['require_registry_eof'] is True
        packet = {'schema': 'nte-original-dialogue-inventory-v2', 'complete': True,
            'registry_sha256': hashlib.sha256(raw).hexdigest(), 'registry_bytes': len(raw), 'registry_eof_verified': True,
            'nonce': request['inventory_nonce'], 'package_count': 1, 'packages': {'HT/Content/a.uasset': 80}}
        (destination/'dialogue-inventory.json').write_text(json.dumps(packet))
        return CompletedProcess(['owned'], 0)
    monkeypatch.setattr(runtime.NteGameDataReader, 'execute', execute)
    try:
        for _ in range(12):
            before = len([call for call in original.calls if call['range']])
            plan = service.plan('nte', REQUEST)['game']
            assert len([call for call in original.calls if call['range']]) == before
            owned = service.plans[plan['plan_id']]['plan']
            if owned.stage == 'dialogue-package-ranges': break
            original.forbid_all_http = owned.stage == 'process-metadata'
            assert plan['can_download']
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
            assert finish(service)['job']['status'] == 'needs_plan'
            original.forbid_all_http = False
        else: pytest.fail('Original metadata did not yield a package quote')
        assert plan['download_bytes'] > 0 and owned.handle['ranges']
        previous = (original.root/'nte/stage.json').read_bytes()
        original.corrupt = corrupt
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        state = finish(service)
        blocks = list((original.root/'nte/cache/tools/nte-publisher/iostore').rglob('*.block'))
        if corrupt:
            assert state['job']['status'] == 'failed' and not blocks
            assert (original.root/'nte/stage.json').read_bytes() == previous
        else:
            assert state['job']['status'] == 'needs_plan' and blocks
            assert state['job']['downloaded_bytes'] == plan['download_bytes']
            following = service.plan('nte', REQUEST)['game']
            assert not following['can_download'] and following['revision'].startswith('nte-native-authoring-')
        assert not (original.root/'nte/current.json').exists()
    finally: service.close()


def test_larger_normal_package_inventory_is_quoted_in_bounded_continuations(tmp_path):
    from backend import nte_graph_prefetch as prefetch, nte_game_data_packages as packages
    from backend.nte_publisher_iostore import Container, Block
    from backend.preparation_errors import PreparationFailure
    source = object.__new__(Container); source.root = tmp_path
    size = 4*1024**2; source.block_size = size
    names = [f'HT/Content/Future{i}.uasset' for i in range(17)]
    source.paths = {name.casefold(): (name, index) for index, name in enumerate(names)}
    source.locations = tuple((i*size, size) for i in range(17))
    source.blocks = tuple(Block(i*size, size, size, 0, size, bytes(20)) for i in range(17))
    containers = {'Paks/owned.utoc': source}; claims = {name: size for name in names}
    with pytest.raises(PreparationFailure): prefetch.plan(containers, claims)
    retained = {'packages': claims, 'receipt': 'a'*64}
    selected, receipt = packages._selection({'owned': True}, retained, containers)
    assert selected.new_bytes == 64*1024**2 and len(receipt['ranges']) == 16
    source._cached = lambda index: b'already independently verified' if index < 16 else None
    continuation, receipt = packages._selection({'owned': True}, retained, containers)
    assert continuation.new_bytes == size and receipt['ranges'] == [{'toc': 'Paks/owned.utoc', 'first': 16, 'stop': 17}]
