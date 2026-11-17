"""Original text/index inputs need no fictitious or downloaded audio master."""
import io
import json
import builtins
import importlib.util
import sys

import pytest

from backend import endfield_parameters as parameters, endfield_release as release
from backend import endfield_metadata, endfield_vfs as vfs
from backend.endfield_client_contract import Candidate
from backend.preparation_errors import PreparationFailure
from backend.tests.test_endfield_client_parameters import identity
from backend.tests.test_endfield_vfs import PARAMETERS, index


@pytest.mark.parametrize('block,name', [(18, 'TableCfg/Owned.bytes'), (17, 'Data/LuaScripts/Owned.lua'),
                                       (4, 'Data/Bundles/Windows/manifest.hgmmap')])
def test_modern_table_lua_and_ui_indexes_do_not_request_audio_or_community_seed_data(tmp_path, monkeypatch, block, name):
    client = identity()
    directories = {17: 'A0000017', 18: 'A0000018', 4: 'A0000004'}
    candidate = Candidate(PARAMETERS.key, directories, 3)
    layer = release.CDN + '/9.8/resource/Windows/main/12-3_Owned/files'
    initial = release.CDN + '/9.8/resource/Windows/initial/12-3_Initial/files'
    descriptor = {'version': '9.8.7', 'client': client,
                  'layers': {'main': {'url': layer}, 'initial': {'url': initial}}}
    raw = json.dumps(descriptor).encode()
    stamp = release._stamp(raw)
    path = tmp_path / 'endfield-releases' / stamp
    path.parent.mkdir()
    path.write_bytes(raw)
    monkeypatch.setattr(parameters, 'candidate', lambda *_: candidate)
    monkeypatch.setattr(endfield_metadata, 'parameters', lambda *_: pytest.fail('Modern plain index acquired community/audio seed data'))
    monkeypatch.setattr(release, 'parameters', lambda *_: pytest.fail('Plain index acquired full audio parameters'))
    monkeypatch.setattr(release, 'latest_client', lambda *_: ({}, client))
    calls = []
    def fetch(url, **_):
        calls.append(url)
        root = initial if block == 4 else layer
        assert url == root + '/VFS/' + directories[block] + '/' + directories[block] + '.blc'
        return index(64, block=block, name=name)
    monkeypatch.setattr(release, 'download', fetch)
    base, rows = release.group(tmp_path, stamp, block)
    assert [row.name for row in rows] == [name]
    assert base.parameters == vfs.IndexParameters(PARAMETERS.key, directories)
    assert not hasattr(base.parameters, 'multiplier') and not hasattr(base.parameters, 'xor_constant')
    assert len(calls) == 1 and parameters._active(tmp_path, client)[1]['validated_indices'][str(block)]


def test_common_only_source_reads_outer_bytes_but_cannot_silently_decode_audio():
    params = vfs.IndexParameters(PARAMETERS.key, {18: 'A0000018'})
    file = vfs.File('owned.bytes', 1, '0' * 32 + '.chk', 0, 4, None, 4)
    source = vfs.PackageSource(io.BytesIO(b'data'), file, params)
    assert source.read(0, 4) == b'data'
    source.read = lambda *_: pytest.fail('Missing audio master must stop before package reads')
    for action in (lambda: vfs.Package(source, params), lambda: vfs.xor_data(b'data', 1, params)):
        with pytest.raises(PreparationFailure) as caught:
            action()
        assert caught.value.code == 'missing_original_audio_master'
        assert caught.value.previous_snapshot_retained is True


def test_legacy_descriptor_still_uses_its_exact_frozen_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'descriptor', lambda *_: {'version': 'historical'})
    monkeypatch.setattr(endfield_metadata, 'parameters', lambda *_: PARAMETERS)
    monkeypatch.setattr(parameters, 'candidate', lambda *_: pytest.fail('Old descriptor adopted new original-client provenance'))
    assert release.index_parameters(tmp_path, 'historical') is PARAMETERS


def test_cold_text_index_reader_does_not_require_the_numpy_audio_mask_runtime(monkeypatch):
    original_import = builtins.__import__
    def without_numpy(name, *args, **kwargs):
        if name == 'numpy' or name.startswith('numpy.'):
            pytest.fail('A text/index reader imported the audio mask runtime')
        return original_import(name, *args, **kwargs)
    spec = importlib.util.spec_from_file_location('backend._owned_common_index_probe', vfs.__file__)
    probe = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, probe)
    monkeypatch.setattr(builtins, '__import__', without_numpy)
    spec.loader.exec_module(probe)
    params = probe.IndexParameters(PARAMETERS.key, {18: 'A0000018'})
    rows = probe.parse_index(index(64, block=18, name='TableCfg/Owned.bytes'), params, 18, suffix='.bytes')
    assert [row.name for row in rows] == ['TableCfg/Owned.bytes']


@pytest.mark.parametrize('directories', [{}, {True: 'A0000018'}, {18: 'not-a-directory'},
                                        {17: 'A0000017', 18: 'A0000017'}])
def test_invalid_original_index_map_is_rejected_without_audio_placeholders(directories):
    with pytest.raises(ValueError):
        vfs.IndexParameters(PARAMETERS.key, directories)
