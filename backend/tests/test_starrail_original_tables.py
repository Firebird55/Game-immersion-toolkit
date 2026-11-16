"""Original-table regressions: locale routing, new IDs and failed publication.

Existing caption tests do not exercise localized DesignV package tails or the
native dialogue/text row format. Fixtures here contain only authored data.
"""
import hashlib
import struct

import pytest

from backend import starrail_original_tables as original
from backend.xxhash64 import xxhash64


def uint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes((value,)))


def sint(value):
    return uint(value << 1 if value >= 0 else ((-value) << 1) - 1)


def string(value):
    raw = value.encode('utf-8')
    return uint(len(raw)) + raw


def textid(value):
    return sint(-5) + uint(value)


def package(resources, folder=''):
    body, entries = bytearray(), bytearray()
    for path, raw in resources:
        entries.extend(struct.pack('>QII', xxhash64(path.encode()), len(raw), len(body)))
        body.extend(raw)
    digest = hashlib.md5(body).hexdigest()
    folder = folder.encode('ascii')
    record = struct.pack('>Q16sQI', xxhash64(resources[0][0].encode()), bytes.fromhex(digest),
                         len(body), len(resources))
    return digest, bytes(body), record + entries + struct.pack('>H', len(folder)) + folder + b'\x80'


def source(tmp_path, monkeypatch, groups):
    parts = [package(*group) for group in groups]
    index = struct.pack('>4I', 255, 4, len(parts), sum(len(group[0]) for group in groups))
    index += b''.join(record for _, _, record in parts)
    bodies = {digest: body for digest, body, _ in parts}
    reads = []
    monkeypatch.setattr(original.hotfix, 'index', lambda *args: index)
    monkeypatch.setattr(original.hotfix, 'audio_roots', lambda build: ({'design': 'https://publisher/'}, {}))
    def read(asset, directory, start, length):
        reads.append(asset.url)
        return bodies[asset.digest][start:start + length]
    monkeypatch.setattr(original.hotfix.AudioFile, 'read', read)
    return original.OriginalTables(tmp_path, {}), bodies, reads


def test_original_locale_packages_and_updated_voice_ids_need_no_mirror(tmp_path, monkeypatch):
    prefix = 'BakedConfig/ExcelOutput/'
    subtitle, speaker = (1 << 63) + 91, 47
    talk = sint(1) + uint(15) + uint(3001) + uint(4101) + textid(speaker) + textid(subtitle)
    voice = sint(1) + uint(15) + uint(4101) + b'\x01' + string('vo_original_player') + sint(14)
    en = sint(2) + uint(3) + textid(subtitle) + string('A complete utterance.')
    en += uint(3) + textid(speaker) + string('Guide')
    ja = sint(1) + uint(7) + textid(subtitle) + string('原文です。') + b'\x01'
    reader, _, reads = source(tmp_path, monkeypatch, [
        ([(prefix + 'TalkSentenceConfig.bytes', talk), (prefix + 'VoiceConfig.bytes', voice)], ''),
        ([(prefix + 'Textmap_en.bytes', en)], 'en'),
        ([(prefix + 'Textmap_jp.bytes', ja)], 'jp')])
    assert reader.file('ExcelOutput/TalkSentenceConfig.json') == [{
        'TalkSentenceID': 3001, 'VoiceID': 4101,
        'TextmapTalkSentenceName': {'Hash': speaker}, 'TalkSentenceText': {'Hash': subtitle}}]
    assert reader.file('ExcelOutput/VoiceConfig.json') == [{
        'VoiceID': 4101, 'IsPlayerInvolved': True, 'VoicePath': 'vo_original_player', 'VoiceType': 'StoryNew'}]
    assert reader.file('TextMap/TextMapEN.json') == {str(subtitle): 'A complete utterance.', str(speaker): 'Guide'}
    assert reader.file('TextMap/TextMapJP.json') == {str(subtitle): '原文です。'}
    assert any('/en/' in url for url in reads) and any('/jp/' in url for url in reads)
    # A newly indexed ID/path and a moved package use the same frozen reader.
    updated = sint(1) + uint(3) + uint(99999) + uint(88888)
    new_reader, _, _ = source(tmp_path, monkeypatch, [
        ([(prefix + 'NewChapterPadding.bytes', b'padding'), (prefix + 'TalkSentenceConfig.bytes', updated)], '')])
    assert new_reader.table('TalkSentenceConfig')[0]['VoiceID'] == 88888
    # Old complete packages survive a subsequent preparation.
    assert len(list((tmp_path / 'starrail-design-packages').glob('*.bytes'))) == 4


@pytest.mark.parametrize('bad', [
    sint(1) + uint(16),                         # Unknown serialized field.
    sint(1) + uint(1) + b'\x80',               # Truncated integer.
    sint(1) + uint(1) + b'\x80\x00',          # Noncanonical integer.
    sint(1) + uint(1) + uint(1 << 32),         # ID width overflow.
    sint(1) + uint(0) + b'extra',               # Trailing bytes.
    sint(2) + uint(1) + uint(3) + uint(1) + uint(3),  # Duplicate identity.
    sint(-1),                                 # Negative row count.
    sint(2_000_001),                           # Unbounded allocation request.
])
def test_unknown_or_malformed_dialogue_cannot_publish_a_catalog(bad):
    with pytest.raises(ValueError):
        original.decode_table(bad, original.SCHEMAS['TalkSentenceConfig'], 'TalkSentenceID')


@pytest.mark.parametrize('bad', [
    sint(1) + uint(2) + b'\x02',
    sint(1) + uint(4) + uint(100) + b'short',
    sint(1) + uint(4) + b'\x01\xff',
])
def test_invalid_boolean_or_utf8_is_not_a_supported_voice_row(bad):
    with pytest.raises(ValueError):
        original.decode_table(bad, original.SCHEMAS['VoiceConfig'], 'VoiceID')


def test_zero_defaults_and_new_enum_do_not_invent_unvoiced_status(tmp_path, monkeypatch):
    prefix = 'BakedConfig/ExcelOutput/'
    reader, _, _ = source(tmp_path, monkeypatch, [
        ([(prefix + 'VoiceConfig.bytes', sint(1) + uint(9) + uint(73) + sint(201))], '')])
    row = reader.table('VoiceConfig')[0]
    assert row == {'VoiceID': 73, 'VoicePath': '', 'IsPlayerInvolved': False, 'VoiceType': 201}
    assert original.decode_table(sint(1) + b'\x00', original.SCHEMAS['TalkSentenceConfig'], 'TalkSentenceID')[0] == {
        'TalkSentenceID': 0, 'VoiceID': 0, 'TextmapTalkSentenceName': {'Hash': 0}, 'TalkSentenceText': {'Hash': 0}}


def test_failed_package_hash_never_replaces_previous_complete_package(tmp_path, monkeypatch):
    path = 'BakedConfig/ExcelOutput/VoiceConfig.bytes'
    first, _, _ = source(tmp_path, monkeypatch, [([(path, sint(1) + uint(1) + uint(73))], '')])
    assert first.table('VoiceConfig')[0]['VoiceID'] == 73
    old = next((tmp_path / 'starrail-design-packages').glob('*.bytes'))
    prior = old.read_bytes()
    second, _, _ = source(tmp_path, monkeypatch, [([(path, sint(1) + uint(1) + uint(74))], '')])
    monkeypatch.setattr(original.hotfix.AudioFile, 'read', lambda *args: b'corrupt transport')
    with pytest.raises(ValueError):
        second.table('VoiceConfig')
    assert old.read_bytes() == prior
    assert list((tmp_path / 'starrail-design-packages').glob('*.bytes')) == [old]


def test_resource_and_locale_paths_cannot_escape_the_fixed_publisher_root(tmp_path, monkeypatch):
    path = 'BakedConfig/ExcelOutput/VoiceConfig.bytes'
    for folder in ('../en', '/en', 'en/other'):
        with pytest.raises(ValueError):
            source(tmp_path, monkeypatch, [([(path, b'\x00')], folder)])
    reader, _, _ = source(tmp_path, monkeypatch, [([(path, b'\x00')], '')])
    for name in ('../VoiceConfig.json', 'ExcelOutput/UnprovedNewTable.json', 'TextMap/TextMapKR_0.json'):
        with pytest.raises(ValueError):
            reader.file(name)
    with pytest.raises(ValueError):
        reader.resource('BakedConfig/ExcelOutput/../VoiceConfig.bytes')
    with pytest.raises(ValueError):
        reader.textmap('../en')


def test_new_native_description_can_be_supplied_without_a_version_allowlist():
    schema = (*original.SCHEMAS['TalkSentenceConfig'], ('FutureSpeakerID', 'u32'))
    data = sint(1) + uint(17) + uint(99) + uint(111)
    assert original.decode_table(data, schema, 'TalkSentenceID')[0]['FutureSpeakerID'] == 111
    with pytest.raises(ValueError):
        original.decode_table(data, original.SCHEMAS['TalkSentenceConfig'], 'TalkSentenceID')
