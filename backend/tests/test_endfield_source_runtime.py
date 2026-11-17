"""Missing host/runtime capability is distinct from a changed publisher format."""
import pytest

from backend import endfield_parameters as parameters, genshin_native_x64, endfield_xxhash
from backend.preparation_errors import PreparationFailure, public_failure
from backend.tests.test_endfield_client_parameters import identity
from backend.tests.test_endfield_vfs import PARAMETERS, index
from backend.endfield_client_contract import Candidate


@pytest.mark.parametrize('missing', ['decoder', 'hash'])
def test_missing_runtime_blocks_before_any_native_header_or_body(tmp_path, monkeypatch, missing):
    def unavailable():
        raise ValueError('authored unavailable host or native software')
    monkeypatch.setattr(genshin_native_x64, 'decoder', unavailable if missing == 'decoder' else lambda: None)
    monkeypatch.setattr(endfield_xxhash, 'implementation', unavailable if missing == 'hash' else lambda: None)
    monkeypatch.setattr(parameters, 'Ranges', lambda *_: pytest.fail('Unavailable runtime attempted native acquisition'))
    parameters._candidate.cache_clear()
    for operation in (parameters.preflight_client, parameters.candidate):
        with pytest.raises(PreparationFailure) as caught:
            operation(tmp_path, identity())
        failure = public_failure(caught.value)
        assert failure['code'] == 'missing_toolkit_runtime'
        assert failure['previous_snapshot_retained'] is True
        assert 'Endfield' in failure['message'] and 'Windows amd64' in failure['message']
        assert 'not a changed game format' in failure['message']
    assert not parameters._path(tmp_path, identity()).exists()


def test_existing_validated_witness_is_readable_without_new_host_runtime(tmp_path, monkeypatch):
    client = identity()
    candidate = Candidate(PARAMETERS.key, PARAMETERS.directories, 3)
    parameters.activate(tmp_path, client, candidate, PARAMETERS, 102, index(64, name='authored.pck'),
                        recheck=lambda: client)
    retained = parameters._path(tmp_path, client).read_bytes()
    monkeypatch.setattr(parameters, 'source_runtime', lambda: pytest.fail('Existing witness requires no cold extraction'))
    monkeypatch.setattr(parameters, 'Ranges', lambda *_: pytest.fail('Offline witness attempted a native download'))
    parameters._candidate.cache_clear()
    assert parameters.candidate(tmp_path, client) == candidate
    assert parameters.preflight_client(tmp_path, client)['parameters_already_validated'] is True
    assert parameters._path(tmp_path, client).read_bytes() == retained
