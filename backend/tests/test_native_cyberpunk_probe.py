"""Authored CR2W structure and semantic assertions used by native acceptance."""
import importlib.util
from pathlib import Path
import struct
import zlib

import pytest


def module():
    path = Path(__file__).resolve().parents[2] / 'scripts/probe-native-cyberpunk.py'
    spec = importlib.util.spec_from_file_location('native_cyberpunk_probe', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_authored_cr2w_has_two_closed_chunks_and_matching_checksums():
    data = module().authored_cr2w()
    assert data[:4] == b'CR2W'
    version, flags, timestamp, build, objects_end, buffers_end, crc, count = struct.unpack_from('<IIQIIIII', data, 4)
    assert (version, objects_end, buffers_end, count) == (195, len(data), len(data), 2)
    tables = [struct.unpack_from('<III', data, 40 + i * 12) for i in range(10)]
    for index, item_size in ((0, 1), (1, 8), (4, 24)):
        offset, count, checksum = tables[index]
        assert zlib.crc32(data[offset:offset + count * item_size]) == checksum
    exports = tables[4][0]
    cursor = exports + 48
    for index in range(2):
        kind, flags, parent, size, offset, template, checksum = struct.unpack_from('<HHIIIII', data, exports + index * 24)
        assert offset == cursor and zlib.crc32(data[offset:offset + size]) == checksum
        cursor += size
    assert cursor == len(data)


def valid_output():
    return {'Header': {'DataType': 'CR2W'}, 'Data': {'Version': 195, 'RootChunk': {
        '$type': 'JsonResource', 'root': {'Data': {'$type': 'localizationPersistenceOnScreenEntries',
        'entries': [{'$type': 'localizationPersistenceOnScreenEntry', 'primaryKey': '12345',
                     'secondaryKey': 'toolkit_authored', 'femaleVariant': 'Authored female dialogue.',
                     'maleVariant': 'Authored male dialogue.'}]}}}}}


def test_semantic_output_accepts_complete_authored_entry():
    module().assert_authored_cr2w_output(valid_output())


@pytest.mark.parametrize('fault', ['empty', 'key', 'female', 'male', 'duplicate', 'type'])
def test_semantic_output_rejects_successful_process_with_missing_or_changed_content(fault):
    value = valid_output()
    collection = value['Data']['RootChunk']['root']['Data']
    entry = collection['entries'][0]
    if fault == 'empty': value = {}
    elif fault == 'key': entry['primaryKey'] = '999'
    elif fault == 'female': del entry['femaleVariant']
    elif fault == 'male': entry['maleVariant'] = 'Changed'
    elif fault == 'duplicate': collection['entries'].append(entry)
    elif fault == 'type': value['Data']['RootChunk']['$type'] = 'DifferentResource'
    with pytest.raises(ValueError, match='preserve'):
        module().assert_authored_cr2w_output(value)
