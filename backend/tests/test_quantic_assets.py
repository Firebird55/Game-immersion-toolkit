"""Synthetic Quantic resources only; no game text, voices or private paths."""
import struct
import io
import json
import math
from types import SimpleNamespace
import wave

import pytest

from backend import quantic_assets as q
from backend.beyond_assets import cues, extract_voice
from backend import beyond_assets as beyond


def integers(*values):
    return struct.pack('<' + 'I' * len(values), *values)


def string(value, unicode=False):
    encoded = value.encode('utf-16-le' if unicode else 'ascii')
    return integers(len(encoded)) + encoded


def localization():
    data = b'COM_CONT' + integers(4, 1, 4091, 42) + b'\1'
    data += b'LOADCONT' + integers(2) + b'LOCALIZ_' + integers(5) + b'\0' + integers(2)
    for language, texts in [('DUT', ['{S}{*1}Test een.', '{*TC:100|900}Test twee.']),
                            ('CHS', ['{*1}Synthetic target one.', '{*TC:100|900}Synthetic target two.'])]:
        data += b'\1' + string(language) + integers(2)
        for key, text in zip(['ONE', 'TWO'], texts):
            data += string(key) + string(text, True) + integers(1)
        data += integers(2) + string('ONE') + b'\1\1' + integers(4091, 42) + string('TWO') + b'\0'
    return data


def partition(single=False, silent=False):
    payload = b'NULL' + integers(16000) if silent else b'\xff\xfa\x92\xc0' + bytes(12)
    block = integers(0) + struct.pack('<2f', 0, .5) + integers(0)
    block += integers(4) + b'000000000000' if single else integers(8, 16+len(payload)) + b'00000000'
    block += payload
    footer = b'PARTOFFS' + integers(2, 16, 4092, 7, 2, 0)
    footer += b'STREAMAB' + integers(1, 0)
    footer += b'HEADER__' + integers(6, 20, 1, 2, 1) + struct.pack('<2f', .1, .4)
    data = b'PARTITIO' + integers(2, 2048+len(block)-16) + bytes(2032) + block + footer
    offsets = b'TBOFFSET' + integers(4, 1, 0, len(block), len(block))
    return data, offsets, payload


def test_multiple_localized_paragraphs_keep_exact_official_bindings():
    tables = q.localization(localization())
    assert tables['DUT']['bindings'] == {'ONE': (4091, 42), 'TWO': None}
    assert set(cues(tables['DUT']['texts']['TWO'])) == {'TC:100|900'}
    assert set(cues(tables['CHS']['texts']['ONE'])) == {'1'}
    assert cues('{S}Plain subtitle.') == {'complete': 'Plain subtitle.'}


def test_short_mp3_tails_keep_exact_frame_samples_and_reject_truncation():
    frame = b'\xff\xfa\x92\xc0' + bytes(414)
    assert beyond.mp3_samples(frame) == 1152
    assert beyond.mp3_samples(frame + frame) == 2304
    with pytest.raises(ValueError, match='exceeds'):
        beyond.mp3_samples(frame[:-1])
    with pytest.raises(ValueError, match='Unsupported'):
        beyond.mp3_samples(b'NULL' + bytes(414))


@pytest.mark.parametrize('rate,header,length', [(44100, b'\xff\xfa\x92\xc0', 418),
                                               (48000, b'\xff\xfa\x94\xc0', 384),
                                               (32000, b'\xff\xfa\x98\xc0', 576)])
def test_original_sample_rates_and_short_tail_resampling(tmp_path, monkeypatch, rate, header, length):
    frame = header + bytes(length - 4)
    assert beyond.mp3_format(frame) == (1152, rate)
    assert beyond.mp3_format(frame * 2) == (2304, rate)
    entry = SimpleNamespace(kind=4091, identity=42, read=lambda: b'partition')
    monkeypatch.setattr(q, 'read_index', lambda _: [entry])
    monkeypatch.setattr(q, 'partition_blocks', lambda *_: [frame])
    monkeypatch.setattr(beyond, 'ffmpeg_executable', lambda: 'ffmpeg')
    def decode(command, **_):
        assert (tmp_path / 'run-0.mp3').read_bytes() == frame * 2
        assert command[command.index('-ar')+1] == '44100'
        return SimpleNamespace(stdout=b'\1\0' * math.ceil(2304 * 44100 / rate))
    monkeypatch.setattr(beyond.subprocess, 'run', decode)
    audio = {'locale': 'en', 'index': 'BigFile_PC.idx', 'identity': 42, 'offsets': ''}
    data = beyond.extract_voice(tmp_path, audio, None, tmp_path)
    with wave.open(io.BytesIO(data), 'rb') as wav:
        assert wav.getframerate() == 44100 and wav.getnframes() == 44100
        pcm = wav.readframes(44100)
    kept = math.ceil(1152 * 44100 / rate)
    assert pcm[:kept*2] == b'\1\0' * kept
    assert pcm[kept*2:] == bytes((44100-kept)*2)
    with pytest.raises(ValueError, match='exceeds'):
        beyond.mp3_format(frame[:-1])


def test_mixed_or_reserved_mpeg_sample_rates_are_rejected():
    first = b'\xff\xfa\x94\xc0' + bytes(380)
    changed = b'\xff\xfa\x92\xc0' + bytes(414)
    with pytest.raises(ValueError, match='sample rate changed'):
        beyond.mp3_format(first + changed)
    with pytest.raises(ValueError, match='Unsupported'):
        beyond.mp3_format(b'\xff\xfa\x9c\xc0' + bytes(380))


def context_rows():
    rows = []
    for paragraph, voice, continuation in [('ONE', 1, 'We gaan naar huis.'), ('TWO', 2, 'Blijf nog even hier.')]:
        for cue, source, target, start, end in [(1, 'Goed.', '好的', 100, 250),
                                               (2, continuation, '第一段后续' if voice == 1 else '第二段后续', 400, 900)]:
            rows.append({'text_id': f'beyond:{paragraph}:{cue}', 'source_locale': 'nl', 'audio_locale': 'nl',
                         'source_text': source, 'texts': {'nl': source, 'zh-Hans': target},
                         'english': '', 'chinese': target,
                         'audio': {'index': 'BigFile_PC_DUT.idx', 'identity': voice, 'locale': 'nl',
                                   'offsets': '', 'start_ms': start, 'end_ms': end}})
    return rows


def test_short_ambiguous_cue_is_collected_with_its_authored_following_context(tmp_path):
    from backend.multilingual_index import MultilingualTextIndex
    from backend.local_game import LocalDialogue
    rows = beyond.group_short_cues(context_rows())
    assert len(rows) == 4
    for row in rows:
        LocalDialogue(**row)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'beyond', 'source_locale': 'nl', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('beyond', tmp_path)
    index.target_locale = 'zh-Hans'
    assert index.match_lines(['Goed.']) is None
    assert index.match_lines(['好的']) is None
    match = index.match_lines(['We gaan naar huis.'])
    assert match.source_text == 'Goed. We gaan naar huis.'
    assert match.translation_text == '好的 第一段后续'
    grouped = next(row for row in rows if row['text_id'] == match.text_id)
    assert grouped['audio']['identity'] == 1
    assert (grouped['audio']['start_ms'], grouped['audio']['end_ms']) == (100, 900)
    assert grouped['member_text_ids'] == ['beyond:ONE:1', 'beyond:ONE:2']
    assert index.match_lines(['第一段后续']).text_id == match.text_id


def test_context_keeps_unpaired_performances_ambiguous_and_never_crosses_voice_bindings(tmp_path):
    from backend.multilingual_index import MultilingualTextIndex
    rows = context_rows()
    rows[1]['audio']['identity'] = 99
    rows = beyond.group_short_cues(rows)
    assert rows[0]['text_id'] == 'beyond:ONE:1'
    assert rows[1]['text_id'] == 'beyond:ONE:2'
    assert any(row.get('member_text_ids') for row in rows)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'beyond', 'source_locale': 'nl', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('beyond', tmp_path)
    # Removing another performance's fragment would turn this into a wrong,
    # seemingly unique match. Context records must preserve those blockers.
    assert index.match_lines(['Goed.']) is None


def test_context_does_not_repeat_identifiable_fragments_or_invent_missing_translations():
    rows = context_rows()
    rows[0]['texts']['en'] = 'A unique fragment.'
    result = beyond.group_short_cues(rows)
    assert result[1]['text_id'] == 'beyond:ONE:2'
    rows = context_rows()
    del rows[0]['texts']['zh-Hans']
    result = beyond.group_short_cues(rows)
    assert result[1]['text_id'] == 'beyond:ONE:2'
    assert result[1]['texts']['zh-Hans'] == rows[1]['texts']['zh-Hans']
    rows = context_rows()
    rows[1]['audio'].update(start_ms=14000, end_ms=15000)
    assert beyond.group_short_cues(rows)[1]['text_id'] == 'beyond:ONE:2'


def test_two_observed_cues_resolve_an_ambiguous_official_translation(tmp_path):
    from backend.multilingual_index import MultilingualTextIndex
    from backend.tests.test_subtitle_capture import fixture_service
    rows = context_rows()
    other = {**rows[1], 'text_id': 'beyond:OTHER:complete', 'source_text': 'Een andere tekst.',
             'texts': {'nl': 'Een andere tekst.', 'zh-Hans': rows[1]['texts']['zh-Hans']},
             'audio': {'index': 'BigFile_PC_DUT.idx', 'identity': 99, 'locale': 'nl'}}
    rows = beyond.group_short_cues([*rows, other])
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'beyond', 'source_locale': 'nl', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('beyond', tmp_path)
    index.target_locale = 'zh-Hans'
    assert index.match_lines(['第一段后续']) is None
    fragments = index.context_fragments(['好的'])
    hit = index.match_context(fragments, ['第一段后续'])
    assert hit.source_text == 'Goed. We gaan naar huis.'
    assert hit.translation_text == '好的 第一段后续'
    assert index.match_context([], ['第一段后续']) is None
    service, *_ = fixture_service(tmp_path / 'capture')
    try:
        scope = ('window', 'nl', 'zh-Hans', 'account-generation-one')
        assert service._authored_caption_context(index, ['好的'], 0, scope, 2) is None
        assert service._authored_caption_context(index, ['第一段后续'], .1, scope, 2) is None
        service._authored_caption_context(index, ['好的'], 1, scope, 2)
        service._authored_caption_context(index, ['好的'], 1.25, scope, 2)
        assert service._authored_caption_context(index, ['第一段后续'], 2, scope, 2).text_id == hit.text_id
        assert service._authored_caption_context(index, ['第一段后续'], 2.25, (*scope, 'new-account'), 2) is None
        service._authored_caption_context(index, ['好的'], 3, scope, 2)
        service._authored_caption_context(index, ['好的'], 3.25, scope, 2)
        assert service._authored_caption_context(index, ['第一段后续'], 16, scope, 2) is None
        service._authored_caption_context(index, ['好的'], 17, scope, 2)
        service._authored_caption_context(index, ['好的'], 17.25, scope, 2)
        service._update_snapshot(phase='waiting_for_game')
        assert service._authored_caption_context(index, ['第一段后续'], 18, scope, 2) is None
    finally:
        service._executor.shutdown()


@pytest.mark.parametrize('single,silent', [(False, False), (True, False), (False, True), (True, True)])
def test_partition_uses_authored_sizes_and_preserves_silent_seconds(single, silent):
    data, offsets, payload = partition(single, silent)
    assert q.partition(data)[0] == 7
    assert q.partition_blocks(data, offsets) == [None if silent else payload]


@pytest.mark.parametrize('change', ['truncate', 'offset', 'frame', 'timing'])
def test_changed_original_partitions_fail_closed(change):
    data, offsets, _ = partition()
    if change == 'truncate':
        data = data[:-1]
    elif change == 'offset':
        offsets = offsets[:16] + integers(100000) + offsets[20:]
    elif change == 'frame':
        data = data[:2048] + integers(1) + data[2052:]
    else:
        data = data[:-8] + struct.pack('<2f', float('nan'), .4)
    with pytest.raises(ValueError):
        q.partition_blocks(data, offsets)


def test_incomplete_localization_and_wrong_pack_are_not_guessed(tmp_path):
    with pytest.raises(ValueError):
        q.localization(localization()[:-1])
    with pytest.raises(ValueError, match='locale'):
        extract_voice(tmp_path, {'locale': 'nl', 'index': 'BigFile_PC_FRE.idx'}, None, tmp_path)
    with pytest.raises(ValueError, match='reference'):
        extract_voice(tmp_path, {'locale': 'nl', 'index': '../BigFile_PC_DUT.idx'}, None, tmp_path)


def write_archive(path, entries):
    content, rows = bytearray(), []
    for kind, identity, data in entries:
        rows.append(struct.pack('>7I', kind, 1, identity, len(content), len(data), 0, 0))
        content.extend(data)
    path.write_bytes(q.MAGIC + struct.pack('>2I', 17, 0) + b'ZEP'*24 + struct.pack('>I', len(rows)) + b''.join(rows))
    path.with_suffix('.dat').write_bytes(content)


@pytest.mark.parametrize('locale', beyond.SUPPORTED_LOCALES)
def test_selected_locale_uses_authored_voice_and_official_translation_only(tmp_path, locale):
    code = beyond.TEXT_LOCALES[locale]
    language = beyond.LANGUAGE_IDS[code]
    raw, offsets, _ = partition()
    loc = b'COM_CONT' + integers(4, 1, 4091, 42) + b'\1'
    loc += b'LOADCONT' + integers(2) + b'LOCALIZ_' + integers(5) + b'\0' + integers(2)
    for tag, text in [(code, '{*1}Synthetic study text.'), ('CHS', '{*1}Synthetic official translation.')]:
        loc += b'\1' + string(tag) + integers(1) + string('LINE') + string(text, True) + integers(1)
        loc += integers(1) + string('LINE') + b'\1\1' + integers(4091, 42)
    references = integers(1016, 100, 4091, 42) + bytes([language]) + integers(4092, 7)
    info = b'DC_INFO ' + integers(2, 4+len(references), 3) + references
    components = bytearray()
    for kind, body in [(1016, loc), (4091, b'typed original metadata'), (4092, offsets)]:
        header = integers(len(body)+4) + (bytes(9)+struct.pack('<H', language) if kind in (4091, 4092) else bytes(10))
        components.extend(header + integers(0) + body)
    metadata = b'QZIP\0' + info + b'DC_DATA ' + integers(20, len(components)) + components
    write_archive(tmp_path/'BigFile_PC.idx', [(29, 9, metadata)])
    write_archive(tmp_path/f'BigFile_PC_{code}.idx', [(4091, 42, raw)])
    result = beyond.index_language(tmp_path, tmp_path/'cache', locale, ['zh-hans', 'ar'])
    assert len(result['records']) == 1
    row = result['records'][0]
    assert row['source_locale'] == row['audio_locale'] == row['audio']['locale'] == locale
    assert row['source_text'] == 'Synthetic study text.'
    assert row['texts']['zh-Hans'] == 'Synthetic official translation.'
    assert row['audio']['identity'] == 42 and row['audio']['start_ms'] == 100
    assert 'ar' in result['missing_translation_locales'] and 'ar' not in row['texts']
    (tmp_path/f'BigFile_PC_{code}.idx').unlink()
    missing = beyond.index_language(tmp_path, tmp_path/'cache', locale, ['zh-hans'])
    assert missing['records'][0]['voice_status'] == 'unavailable'
    assert missing['records'][0]['audio'] is None
    assert any('voice pack' in warning for warning in missing['coverage_warnings'])
