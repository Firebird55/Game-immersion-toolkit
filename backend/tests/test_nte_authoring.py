"""Original publisher authoring packets; synthetic ownership and drift only."""
import copy
import json

import pytest

from backend import nte_authoring as authoring
from backend.nte_cinematics import catalog_rows
from backend.preparation_errors import PreparationFailure


def packet():
    return dict(schema=authoring.SCHEMA, complete=True, nonce='b'*32,
        schema_sha256='a'*64, registry_sha256='c'*64, table_count=2, tables=[
            dict(path='HT/Content/Future/UnfamiliarPackage.uasset', package='/Game/Future/UnfamiliarPackage',
                 object_name=name, row_structure=structure, role=role, rows={'SameRow': row})
            for name, structure, role, row in [
                ('RenamedExport', '/Script/HTGame.BubbleVoiceMsgDetail', 'voice',
                 {'DialogSoundEvent': {'AssetPathName': '/Game/WwiseAudio/Events/Owned/Play_Vo_Actual.Play_Vo_Actual'}}),
                ('SiblingExport', '/Script/HTGame.StorySequenceAndVedioData', 'sequence',
                 {'SequenceInfo': [None, {'CaptionsID': 'SameCaption'}, {'CaptionsID': 'SameCaption'}]})]])


def read(tmp_path, value):
    path = tmp_path/'original-authoring.json'
    path.write_bytes(json.dumps(value).encode())
    return authoring.read_original_authoring(path, schema_sha256='a'*64, nonce='b'*32, registry_sha256='c'*64)


def test_exact_export_and_duplicate_sequence_slots_are_retained_without_a_filename_list(tmp_path):
    value = packet()
    assert read(tmp_path, value) == value
    slots = value['tables'][1]['rows']['SameRow']['SequenceInfo']
    assert slots[0] is None and slots[1] == slots[2]


@pytest.mark.parametrize('bad', ['nonce', 'schema', 'registry', 'complete', 'count', 'unknown-type',
    'role', 'path', 'escape', 'object', 'duplicate', 'case-collision', 'row', 'row-value'])
def test_stale_partial_or_ambiguous_packets_fail_closed(tmp_path, bad):
    value = packet()
    if bad == 'nonce': value['nonce'] = 'd'*32
    elif bad == 'schema': value['schema_sha256'] = 'd'*64
    elif bad == 'registry': value['registry_sha256'] = 'd'*64
    elif bad == 'complete': value['complete'] = False
    elif bad == 'count': value['table_count'] = True
    elif bad == 'unknown-type': value['tables'][0]['row_structure'] = '/Script/HTGame.FutureUnknownFormat'
    elif bad == 'role': value['tables'][0]['role'] = 'caption'
    elif bad == 'path': value['tables'][0]['path'] = 'HT/Content/Future/Wrong.uasset'
    elif bad == 'escape': value['tables'][0]['package'] = '/Game/../Escaped'
    elif bad == 'object': value['tables'][0]['object_name'] = 'Wrong/Object'
    elif bad in ('duplicate', 'case-collision'):
        value['tables'].append(copy.deepcopy(value['tables'][0])); value['table_count'] += 1
        if bad == 'case-collision': value['tables'][-1]['object_name'] = value['tables'][-1]['object_name'].lower()
    elif bad == 'row': value['tables'][0]['rows'] = {'Bad\0Row': {}}
    elif bad == 'row-value': value['tables'][0]['rows'] = {'Bad': []}
    with pytest.raises(PreparationFailure) as error:
        read(tmp_path, value)
    assert error.value.code == 'game_metadata_unavailable'


def test_duplicate_json_rows_are_not_silently_collapsed(tmp_path):
    path = tmp_path/'original-authoring.json'
    path.write_text(json.dumps(packet()).replace('"SameRow":', '"SameRow": {}, "SameRow":', 1))
    with pytest.raises(PreparationFailure):
        authoring.read_original_authoring(path, schema_sha256='a'*64, nonce='b'*32, registry_sha256='c'*64)


def test_movie_catalog_reads_all_declared_future_tables_without_filename_assumptions():
    key = 'HT/Content/Future/Package.uasset#DifferentExport'
    row = {'StringTableID': 'FutureAlias', 'Path': {'FilePath':
        '../../../Projects/HT/Content/Movies/FFMpeg/Story/Future.mp4'},
        'PlayVoice': {'AssetPathName': '/Game/WwiseAudio/Events/CG/Owned/Play_Vo_Future.Play_Vo_Future'}}
    value = {'OriginalMovieTables.json': [key], key: [{'Type': 'DataTable', 'Rows': {'Owned': row}}],
             'StringTableNamespaces.json': {'FutureAlias': 'Owned.Namespace'}}
    assert catalog_rows(value) == [row]
    value['OriginalMovieTables.json'] = [key, key]
    with pytest.raises(ValueError): catalog_rows(value)
    value['OriginalMovieTables.json'] = None
    with pytest.raises(ValueError): catalog_rows(value)
