"""Owned receipt rejection; native eligibility itself is tested independently."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import nte_game_data_authoring as authoring, nte_native_metadata as native


def test_owned_authoring_failure_remains_actionable_without_a_retrying_legacy_catalog(monkeypatch):
    from backend.nte_game_data import NteGameDataProvider
    from backend.preparation_errors import PreparationFailure
    from backend.game_data_protocol import GameDataError
    provider = NteGameDataProvider(platform='windows')
    monkeypatch.setattr(provider, '_reader', lambda _ctx: object())
    def failed(*_args):
        raise PreparationFailure('unsupported_game_format', 'The original dialogue format changed. Your previous library is retained.')
    monkeypatch.setattr(authoring, 'download', failed)
    with pytest.raises(GameDataError) as error:
        provider.download(SimpleNamespace(stage='process-authoring'), SimpleNamespace(check=lambda: None))
    assert error.value.code == 'unsupported_game_format'
    assert str(error.value) == 'The original dialogue format changed. Your previous library is retained.'


@pytest.mark.parametrize('fault', [None, 'output', 'validation', 'inventory', 'reader', 'pointer', 'schema'])
def test_completed_authoring_receipt_is_bound_to_eligible_closure_original_inventory_and_owned_reader(tmp_path, monkeypatch, fault):
    ctx = SimpleNamespace(cache_directory=tmp_path)
    reader = {'kind': 'nte-owned-windows-reader-v1', 'source_sha256': 'a'*64, 'dependencies_sha256': 'b'*64}
    inventory = {'original': 'generation-相'}
    packet = {'schema': authoring.STAGE, 'metadata_recipe': {'imports': {'indices': {'inventory': inventory}}},
        'metadata_receipt': 'c'*64, 'reader': reader}
    identity = authoring.content._identity(packet)
    outputs = {name: ('authored '+name).encode() for name in authoring.OUTPUTS}
    schema = {'owned': 'schema-identity', 'sha256': hashlib.sha256(outputs['dialogue.usmap']).hexdigest()}
    if fault == 'schema': schema['sha256'] = '0'*64
    candidate = SimpleNamespace(receipt={'dependencies': {'reader': reader['source_sha256']},
        'source_manifest_sha256': hashlib.sha256(native._json(inventory)).hexdigest()})
    monkeypatch.setattr(native, 'load', lambda *_a: candidate)
    validation = {'required_schema_eligible': fault != 'validation', 'schema': schema,
        'reader_sha256': reader['source_sha256']}
    raw = authoring.processing._json(validation); proof = hashlib.sha256(raw).hexdigest()
    path = tmp_path/'tools/nte-publisher/native-candidates/validations'/(proof+'.json')
    path.parent.mkdir(parents=True); path.write_bytes(raw)
    receipt = {'schema': authoring.STAGE, 'recipe': identity, 'metadata_receipt': packet['metadata_receipt'],
        'reader': reader, 'type_schema': schema, 'validation': proof,
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()}}
    encoded = authoring.processing._json(receipt); digest = hashlib.sha256(encoded).hexdigest()
    base = authoring._base(ctx); root = base/'objects'/digest; root.mkdir(parents=True)
    (root/'receipt.json').write_bytes(encoded)
    for name, data in outputs.items(): (root/name).write_bytes(data)
    (base/(identity+'.json')).write_text(json.dumps({'recipe': identity, 'receipt': digest}))
    if fault == 'output': (root/'dialogue-events.json').write_bytes(b'altered')
    if fault == 'inventory': candidate.receipt['source_manifest_sha256'] = '0'*64
    if fault == 'reader': candidate.receipt['dependencies']['reader'] = '0'*64
    if fault == 'pointer': (base/(identity+'.json')).write_text(json.dumps({'recipe': identity, 'receipt': '0'*64}))
    result = authoring._read(packet, ctx)
    assert (result is None) is bool(fault)
    if result is not None: assert result == {'receipt': digest, 'root': root}
    assert not (tmp_path/'current.json').exists()
