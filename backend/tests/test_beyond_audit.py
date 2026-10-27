"""Synthetic BEYOND localization audit: no shipped game text or media."""
import struct

import pytest

from backend import quantic_assets as q


def integers(*values):
    return struct.pack('<' + 'I' * len(values), *values)


def string(value, unicode=False):
    encoded = value.encode('utf-16-le' if unicode else 'ascii')
    return integers(len(encoded)) + encoded


def table(pointer=b'\0', flag=0, dependency=True, repeated=False):
    dependencies = integers(4091, 42) + b'\1' if dependency else b''
    data = b'COM_CONT' + integers(4, int(dependency)) + dependencies
    data += b'LOADCONT' + integers(2) + b'LOCALIZ_' + integers(5) + b'\0' + integers(1)
    data += b'\1' + string('ENG') + integers(1) + string('TEST') + string('Synthetic text only.', True) + integers(flag)
    data += integers(2 if repeated else 1) + string('TEST') + pointer
    if repeated:
        data += string('TEST') + b'\1\1' + integers(4091, 999)
    return data


def test_localization_preserves_null_vs_unresolved_pointer_and_text_flags():
    null = q.localization(table(flag=7))['ENG']
    assert null['texts'] == {'TEST': 'Synthetic text only.'}
    assert null['bindings'] == {'TEST': None}
    assert null['binding_states'] == {'TEST': 'none'}
    assert null['text_flags'] == {'TEST': 7}
    unresolved = q.localization(table(b'\1\1' + integers(4091, 42), dependency=False))['ENG']
    assert unresolved['bindings'] == {'TEST': None}
    assert unresolved['binding_states'] == {'TEST': 'unresolved'}
    internal = q.localization(table(b'\1\0' + integers(4091, 42)))['ENG']
    assert internal['binding_states'] == {'TEST': 'internal'}
    resolved = q.localization(table(b'\1\1' + integers(4091, 42)))['ENG']
    assert resolved['bindings'] == {'TEST': (4091, 42)}
    assert resolved['binding_states'] == {'TEST': 'resolved'}


def test_localization_rejects_unsupported_scope_and_contradictory_null_pointer():
    with pytest.raises(ValueError, match='pointer scope'):
        q.localization(table(b'\1\2' + integers(4091, 42)))
    with pytest.raises(ValueError, match='pointer state'):
        q.localization(table(repeated=True))


def test_standalone_localization_validates_section_sizes_and_keeps_texture_identity(tmp_path, monkeypatch):
    from backend.beyond_assets import standalone_localization
    dependencies = integers(1, 13002, 42) + b'\1'
    localized = b'\0' + integers(1) + b'\1' + string('ENG') + integers(1)
    localized += string('TEXTURE') + string('Synthetic texture label', True) + integers(4)
    localized += integers(1) + string('TEXTURE') + b'\1\1' + integers(13002, 42)
    data = b'COM_CONT' + integers(4, len(dependencies)) + dependencies
    data += b'LOADCONT' + integers(2, 0) + b'LOCALIZ_' + integers(5, len(localized)) + localized
    result = standalone_localization(data)['ENG']
    assert result['bindings']['TEXTURE'] == (13002, 42)
    assert result['text_flags']['TEXTURE'] == 4
    for broken in [data[:-1], data + b'extra', data[:12] + integers(9999999) + data[16:]]:
        with pytest.raises(ValueError):
            standalone_localization(broken)
    from types import SimpleNamespace
    from backend import beyond_assets as beyond
    (tmp_path / 'BigFile_PC.idx').write_bytes(b'synthetic index')
    monkeypatch.setattr(q, 'read_index', lambda _: [SimpleNamespace(kind=1016, size=q.METADATA_LIMIT + 1)])
    def forbidden_read(*args, **kwargs):
        raise AssertionError('Oversized raw metadata must be rejected before allocation')
    monkeypatch.setattr(q, 'metadata', forbidden_read)
    with pytest.raises(beyond.PreparationFailure) as failure:
        beyond.index_language(tmp_path, tmp_path / 'cache', 'en', [])
    assert 'exceeds the metadata limit' in str(failure.value.__cause__)


def test_beyond_silent_choices_survive_absent_dub_without_claiming_missing_speech(tmp_path):
    from backend import beyond_assets as beyond
    from backend.tests.test_quantic_assets import write_archive
    content = b'COM_CONT' + integers(4, 1, 4091, 42) + b'\1'
    content += b'LOADCONT' + integers(2) + b'LOCALIZ_' + integers(5) + b'\0' + integers(2)
    choice = 'IW_0701_DIAL_TEST_K1'
    speech = 'IW_0701_DIAL_TEST_K2'
    system = 'IW_5000_SONY_TRC_K1'
    for locale in ['ENG', 'CHS']:
        content += b'\1' + string(locale) + integers(3)
        for key, text, flag in [(choice, 'Synthetic choice', 2), (speech, '{S}{*1}Synthetic speech.', 1), (system, 'Synthetic system prompt', 2)]:
            content += string(key) + string(text, True) + integers(flag)
        content += integers(1) + string(speech) + b'\1\1' + integers(4091, 42)
    references = integers(1016, 100)
    info = b'DC_INFO ' + integers(2, 4 + len(references), 1) + references
    component = integers(len(content) + 4) + bytes(10) + integers(0) + content
    metadata = b'QZIP\0' + info + b'DC_DATA ' + integers(20, len(component)) + component
    write_archive(tmp_path / 'BigFile_PC.idx', [(29, 9, metadata)])
    result = beyond.index_language(tmp_path, tmp_path / 'cache', 'en', ['zh-Hans'])
    rows = {row['text_id']: row for row in result['records']}
    assert len(rows) == 2
    assert rows[f'beyond:{choice}:complete']['voice_status'] == 'unvoiced'
    assert rows[f'beyond:{choice}:complete']['dialogue_kind'] == 'choice'
    assert rows[f'beyond:{choice}:complete']['texts']['zh-Hans'] == 'Synthetic choice'
    assert rows[f'beyond:{speech}:unresolved']['voice_status'] == 'unavailable'
    assert all(row['audio'] is None for row in rows.values())
    assert any('voice pack' in warning for warning in result['coverage_warnings'])
    assert result['diagnostics']['excluded_system_or_shared_prompts'] == 1
    (tmp_path / 'BigFile_PC.idx').write_bytes(b'New update format')
    with pytest.raises(beyond.PreparationFailure) as failure:
        beyond.index_language(tmp_path, tmp_path / 'cache', 'en', ['zh-Hans'])
    assert failure.value.code == 'unsupported_game_format'


def test_missing_pointer_or_future_flags_do_not_certify_silence():
    from backend.beyond_assets import unbound_status
    key = 'IW_0701_DIAL_TEST_K1'
    for flag, pointer in [(1, 'absent'), (2, 'unresolved'), (2, 'internal'), (7, 'absent')]:
        source = {'text_flags': {key: flag}, 'binding_states': {key: pointer}}
        assert unbound_status(key, 'Synthetic line.', source)[0] != 'unvoiced'
    assert unbound_status(key, '{S}{*1}Synthetic speech.', {'text_flags': {key: 2}})[0] != 'unvoiced'
    from backend.beyond_assets import unbound_paragraph, cues
    malformed_unused = '{S}{*1}First sentence.{*1}Second sentence.'
    assert unbound_paragraph(malformed_unused) == 'First sentence.Second sentence.'
    with pytest.raises(ValueError, match='Ambiguous'):
        cues(malformed_unused)


def test_repeated_container_reference_validates_original_performance_once(tmp_path, monkeypatch):
    from backend import beyond_assets as beyond
    from backend.tests.test_quantic_assets import partition, write_archive
    raw, offsets, _ = partition()
    content = b'COM_CONT' + integers(4, 1, 4091, 42) + b'\1'
    content += b'LOADCONT' + integers(2) + b'LOCALIZ_' + integers(5) + b'\0' + integers(1)
    content += b'\1' + string('ENG') + integers(1) + string('LINE') + string('{*1}Synthetic study text.', True) + integers(1)
    content += integers(1) + string('LINE') + b'\1\1' + integers(4091, 42)
    references = integers(1016, 100, 4091, 42) + b'\1' + integers(4092, 7)
    info = b'DC_INFO ' + integers(2, 4 + len(references), 3) + references
    components = bytearray()
    for kind, body in [(1016, content), (4091, b'typed original metadata'), (4092, offsets)]:
        header = integers(len(body) + 4) + (bytes(9) + struct.pack('<H', 1) if kind in (4091, 4092) else bytes(10))
        components.extend(header + integers(0) + body)
    metadata = b'QZIP\0' + info + b'DC_DATA ' + integers(20, len(components)) + components
    write_archive(tmp_path / 'BigFile_PC.idx', [(29, 9, metadata), (29, 10, metadata), (4091, 42, raw)])
    calls = []
    original = q.partition_blocks
    monkeypatch.setattr(q, 'partition_blocks', lambda *args: calls.append(True) or original(*args))
    result = beyond.index_language(tmp_path, tmp_path / 'cache', 'en', [])
    assert len(result['records']) == 1 and len(calls) == 1
    assert result['diagnostics']['validated_performances'] == 1
    changed_offsets = offsets[:-4] + integers(1)
    write_archive(tmp_path / 'BigFile_PC.idx', [(29, 9, metadata),
        (29, 10, metadata.replace(offsets, changed_offsets)), (4091, 42, raw)])
    with pytest.raises(beyond.PreparationFailure) as failure:
        beyond.index_language(tmp_path, tmp_path / 'cache', 'en', [])
    assert 'Conflicting original dialogue chunk tables' in str(failure.value.__cause__)
