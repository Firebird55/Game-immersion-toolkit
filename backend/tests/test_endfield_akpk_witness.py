"""Provider-local original master identity, whole-data gate and retention."""
import copy
from types import SimpleNamespace as NS

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Shared pure preparation dependency')
from backend import endfield_akpk_witness as witness
from backend.game_data_protocol import GameDataError, GameDataRequest
from backend.endfield_native_import import Import
from backend.endfield_akpk_contract import Candidate
from backend.tests.test_endfield_akpk_contract import declaration
from backend.tests.test_endfield_vfs import PARAMETERS, package
from backend.tests.test_endfield_client_parameters import identity


def fixture(tmp_path, monkeypatch):
    original = identity()
    request = GameDataRequest('global', 'en', (), 'text-audio')
    ctx = NS(game='endfield', phase='download', request=request, cache_directory=tmp_path,
             check=lambda: None)
    bootstrap = NS(identity=original, transport=None, artifact=lambda _: NS())
    stage = {'schema': 1, 'stage': 'original-audio-native-source-downloaded',
             'client': original, 'request': request.json(), 'source_receipt_sha256': 'b' * 64}
    generation = {'main': {'url': 'authored-original-main-generation', 'sha256': 'c' * 64}}
    # Simulate only native/source candidates. The real complete PCK encoder and
    # control parser below remain independent of these source-recognizer seams.
    monkeypatch.setattr(witness, 'Metadata', lambda _: NS())
    monkeypatch.setattr(witness, 'Image', lambda _: NS())
    monkeypatch.setattr(witness, 'managed_import', lambda *_: Import('Owned', 'Entry'))
    monkeypatch.setattr(witness, 'common_candidate', lambda *_: NS(key=PARAMETERS.key,
        directories=PARAMETERS.directories, protocol=PARAMETERS.protocol))
    monkeypatch.setattr(witness, 'NativeImage', lambda _: NS())
    monkeypatch.setattr(witness, 'audio_candidate', lambda *_: Candidate(5, 7))
    class Verified:
        def __init__(self, *_): pass
        def verified(self, imported, receipt):
            assert imported == Import('Owned', 'Entry') and receipt == 'b' * 64
            return b'authored original module', {'sha256': 'd' * 64}
    monkeypatch.setattr(witness, 'OriginalNativeSource', Verified)
    data = package()
    def activate(**kwargs):
        return witness.activate(ctx, bootstrap, stage, generation, declaration(data), 102,
            'default_owned_banks.pck', data, recheck=lambda: (original, generation), **kwargs)
    return NS(ctx=ctx, bootstrap=bootstrap, stage=stage, generation=generation, data=data,
              original=original, activate=activate)


def test_explicit_immutable_reference_restores_same_original_parameters_without_legacy_cache_adoption(tmp_path, monkeypatch):
    source = fixture(tmp_path, monkeypatch)
    legacy = tmp_path / 'tools' / 'format-metadata' / 'retained-profile'
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'old exact frozen provenance')
    reference = source.activate()
    assert set(reference) == {'schema', 'client_sha256', 'generation_sha256', 'module_sha256',
                              'control_sha256', 'witness_sha256'}
    assert witness.restore(source.ctx, reference, source.original, source.generation) == PARAMETERS
    assert legacy.read_bytes() == b'old exact frozen provenance'
    assert len(list(tmp_path.glob('endfield-original-akpk/*/*.json'))) == 1
    assert source.activate() == reference
    assert 'key' not in reference and 'multiplier' not in reference and 'xor_constant' not in reference


@pytest.mark.parametrize('change', ['client', 'generation', 'module', 'control', 'witness', 'traversal', 'body'])
def test_reference_does_not_remap_to_other_source_or_search_for_an_alternative(tmp_path, monkeypatch, change):
    source = fixture(tmp_path, monkeypatch)
    reference = source.activate()
    expected = copy.deepcopy(reference)
    original, generation = copy.deepcopy(source.original), copy.deepcopy(source.generation)
    if change == 'client': original['game_files_md5'] = 'e' * 32
    elif change == 'generation': generation['main']['sha256'] = 'f' * 64
    elif change in {'module', 'control', 'witness'}: reference[change + '_sha256'] = 'a' * 64
    elif change == 'traversal': reference['witness_sha256'] = '../other'
    elif change == 'body': next(tmp_path.glob('endfield-original-akpk/*/*.json')).write_bytes(b'tampered')
    with pytest.raises(GameDataError):
        witness.restore(source.ctx, reference, original, generation)
    if change != 'body':
        assert witness.restore(source.ctx, expected, source.original, source.generation) == PARAMETERS


@pytest.mark.parametrize('change', ['no_consent', 'text', 'other_dub', 'wrong_candidate', 'file_md5', 'generation_recheck'])
def test_failed_activation_does_not_change_previously_referenced_material(tmp_path, monkeypatch, change):
    source = fixture(tmp_path, monkeypatch)
    previous = source.activate()
    path = next(tmp_path.glob('endfield-original-akpk/*/*.json'))
    saved = path.read_bytes()
    payload, block, recheck = source.data, 102, lambda: (source.original, source.generation)
    if change == 'no_consent': source.ctx.phase = 'plan'
    elif change == 'text': source.ctx.request = GameDataRequest('global', 'en', (), 'text')
    elif change == 'other_dub': block = 101
    elif change == 'wrong_candidate': monkeypatch.setattr(witness, 'audio_candidate', lambda *_: Candidate(13, 7))
    elif change == 'file_md5': payload = payload[:-1] + bytes([payload[-1] ^ 1])
    elif change == 'generation_recheck': recheck = lambda: (source.original, {})
    with pytest.raises((ValueError, GameDataError)):
        witness.activate(source.ctx, source.bootstrap, source.stage, source.generation,
            declaration(source.data), block, 'default_owned_banks.pck', payload, recheck=recheck)
    assert path.read_bytes() == saved and len(list(tmp_path.glob('endfield-original-akpk/*/*.json'))) == 1
    assert witness.restore(source.ctx, previous, source.original, source.generation) == PARAMETERS
