"""Closed graph, original PE ownership and transactional helper regressions."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_metadata as metadata


spec = importlib.util.spec_from_file_location('starrail_authored_probe', Path('packaging/starrail-reader/probe.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def fixture(tmp_path):
    base, first, second = 0x180000000, 0x1000, 0x20000000
    code = [b'\xe9' + struct.pack('<i', second - first - 5), bytes.fromhex('7503 90 c3 ff 90 c3 48b8')]
    source = tmp_path / 'inputs' / 'GameAssembly.dll'; source.parent.mkdir()
    source.write_bytes(probe.native_pe(list(zip((first, second), code))))
    regions = [{'rva': rva, 'bytes': len(data), 'offset': 512 + i * 512,
                'unwind_rva': 0x70000000 + 24 + i * 4, 'sha256': hashlib.sha256(data).hexdigest()}
               for i, (rva, data) in enumerate(zip((first, second), code))]
    a, b = base + first, base + second
    value = {'schema': 'proxy-starrail-native-graph-v1', 'image_base': base, 'entry_rva': first,
             'regions': regions, 'instructions': [[a, 'jmp', hex(b), 5], [b, 'jne', hex(b + 5), 2],
                 [b + 2, 'nop', '', 1], [b + 3, 'ret', '', 1], [b + 5, 'nop', '', 1], [b + 6, 'ret', '', 1]],
             'edges': [[a, [b]], [b, [b + 2, b + 5]], [b + 2, [b + 3]], [b + 3, []],
                       [b + 5, [b + 6]], [b + 6, []]], 'calls': [], 'returns': [b + 3, b + 6]}
    native = {'bytes': source.stat().st_size, 'md5': metadata._hash(source, 'md5')}
    def run(operation, actual, request, output, *, work):
        assert operation == 'native-graph' and actual == source
        assert json.loads(request.read_text()) == {'entry_rva': first}
        output.write_text(json.dumps(value))
    outputs = tmp_path / 'outputs'; outputs.mkdir(); (outputs / 'dump.cs').write_text('previous complete metadata')
    receipt = {'identity': {'files': {'native': native}}}
    return metadata.Prepared(tmp_path, source.parent, outputs, receipt, SimpleNamespace(run=run)), value


def test_graph_reads_original_split_regions_without_decoding_metadata(tmp_path):
    prepared, expected = fixture(tmp_path)
    assert prepared.native_graph(0x1000) == expected
    assert not list(tmp_path.glob('native-graph-*'))
    assert (prepared.outputs / 'dump.cs').read_text() == 'previous complete metadata'


@pytest.mark.parametrize('change', ['unknown', 'entry_bool', 'region_count', 'region_size', 'region_hash',
    'region_offset', 'unwind', 'image_base', 'overlap', 'undefined_edge', 'return_edge', 'missing_call',
    'orphan', 'instruction_size_bool', 'unknown_region_field'])
def test_malformed_graph_cannot_escape_original_ownership_or_replace_metadata(tmp_path, change):
    prepared, value = fixture(tmp_path)
    first, second = value['instructions'][0][0], value['instructions'][1][0]
    if change == 'unknown':
        value['unknown'] = 1
    elif change == 'entry_bool':
        value['entry_rva'] = True
    elif change == 'region_count':
        value['regions'] *= 9
    elif change == 'region_size':
        value['regions'][0]['bytes'] = 32769
    elif change == 'region_hash':
        value['regions'][0]['sha256'] = '0' * 64
    elif change == 'region_offset':
        region = value['regions'][0]; region['offset'] += 1
        raw = (prepared.inputs / 'GameAssembly.dll').read_bytes()[region['offset']:region['offset'] + region['bytes']]
        region['sha256'] = hashlib.sha256(raw).hexdigest()
    elif change == 'unwind':
        value['regions'][0]['unwind_rva'] += 4
    elif change == 'image_base':
        value['image_base'] += 1
    elif change == 'overlap':
        value['instructions'].insert(1, [first + 1, 'nop', '', 1])
    elif change == 'undefined_edge':
        value['edges'][0][1] = [second + 1]
    elif change == 'return_edge':
        value['edges'][3][1] = [first]
    elif change == 'missing_call':
        value['instructions'][2][1:3] = ['call', 'rax']
    elif change == 'orphan':
        value['instructions'][0][2] = hex(first); value['edges'][0][1] = [first]
    elif change == 'instruction_size_bool':
        value['instructions'][2][3] = True
    elif change == 'unknown_region_field':
        value['regions'][0]['unknown'] = 1
    with pytest.raises(ValueError):
        prepared.native_graph(0x1000)
    assert not list(tmp_path.glob('native-graph-*'))
    assert (prepared.outputs / 'dump.cs').read_text() == 'previous complete metadata'


def test_native_input_changed_during_graph_read_is_rejected(tmp_path):
    prepared, _ = fixture(tmp_path)
    original = prepared.helper.run
    def mutate(*args, **kwargs):
        original(*args, **kwargs)
        with (prepared.inputs / 'GameAssembly.dll').open('ab') as stream:
            stream.write(b'authored changed input')
    prepared.helper.run = mutate
    with pytest.raises(ValueError):
        prepared.native_graph(0x1000)
    assert (prepared.outputs / 'dump.cs').read_text() == 'previous complete metadata'


@pytest.mark.parametrize('entry', [-1, 2**32, True, '0x1000'])
def test_invalid_graph_entry_never_starts_a_helper(tmp_path, entry):
    prepared, _ = fixture(tmp_path)
    prepared.helper.run = lambda *a, **k: pytest.fail('Invalid graph entry cannot start a process')
    with pytest.raises(ValueError):
        prepared.native_graph(entry)


def test_graph_output_limit_is_checked_before_parsing(tmp_path):
    prepared, _ = fixture(tmp_path)
    def oversized(operation, source, request, output, *, work):
        with output.open('wb') as stream:
            stream.truncate(8 * 1024**2 + 1)
    prepared.helper.run = oversized
    with pytest.raises(ValueError):
        prepared.native_graph(0x1000)
    assert not list(tmp_path.glob('native-graph-*'))
