"""Synthetic original-PC Decima fixtures; no proprietary game content."""
from pathlib import Path
import struct

import pytest

from backend import death_stranding_assets as ds
from backend import decima_archive as archive
from backend.decima_dialogue import (INTERVIEW, MAIL, SENTENCE, SOUND, TEXT,
    core_objects, localized_sound, localized_text, readable, reference, sentence)
from backend.local_game import LocalDialogue
from backend import decima_cinematics as cine


def u(fmt, *values):
    return struct.pack('<' + fmt, *values)


def identity(number):
    return number.to_bytes(16, 'little')


def string(value, hashed=True):
    data = value.encode('utf-8')
    return u('I', len(data)) + (u('I', 123) if data and hashed else b'') + data


def ref(number=None, path=None):
    if number is None:
        return b'\0'
    return bytes([2 if path is not None else 1]) + identity(number) + (string(path) if path is not None else b'')


def obj(kind, number, payload):
    body = identity(number) + payload
    return u('QI', kind, len(body)) + body


def text_payload(texts):
    result = b''
    for language in range(1, 26):
        text = texts.get(language, '').encode('utf-8')
        result += u('H', len(text)) + text + u('HB', 0, 0)
    return result


def sound_payload(languages=archive.AUDIO_NAMES):
    result = string('Synthetic voice') + ref() + b'\0' * 137 + ref() + ref() + u('II', 0, 0) + u('f', 0)
    mask = sum(1 << archive.AUDIO_NAMES.index(language) for language in languages)
    result += u('HBBBHBBIHIHH', mask, 1, 1, 2, 288, 4, 1, 48000, 16, 96000, 2, 1)
    for language in archive.AUDIO_NAMES:
        if language not in languages:
            continue
        source = string(f'localized/synthetic/line.wem.{language}', False) + identity(900) + u('III', 1, 3, 16)
        result += u('B', len(source)) + source
    return result


def sentence_payload(sound=2, text=3, show=1):
    return u('BfB', 2, .5, show) + ref(sound) + ref() + ref(text) + ref()


def pack(root, files, *, language=None, category='initial', encrypted=False):
    body = b''.join(files.values())
    chunks = [body[i:i + 64] for i in range(0, len(body), 64)]
    start = 40 + 32 * (len(files) + len(chunks))
    file_table, position = b'', 0
    for number, (path, data) in enumerate(files.items()):
        words = list(struct.unpack('<8I', u('IIQQII', number, 0, archive.path_hash(path), position, len(data), 0)))
        if encrypted:
            archive._xor_words(words, 7, 0); archive._xor_words(words, 9, 4)
            words[1], words[7] = 7, 9
        file_table += u('8I', *words)
        position += len(data)
    chunk_table, packed, position = b'', b'', 0
    for chunk in chunks:
        words = list(struct.unpack('<8I', u('QIIQII', position, len(chunk), 0, start + len(packed), len(chunk), 0)))
        if encrypted:
            archive._xor_words(words, 11, 0); archive._xor_words(words, 13, 4)
            words[3], words[7] = 11, 13
            data = archive._unmask(chunk, u('QII', position, len(chunk), 11))
        else:
            data = chunk
        chunk_table += u('8I', *words)
        packed += data
        position += len(chunk)
    words = list(struct.unpack('<8I', u('QQQII', start + len(body), len(body), len(files), len(chunks), 64)))
    if encrypted:
        archive._xor_words(words, 5, 0); archive._xor_words(words, 6, 4)
    header = u('II8I', 0x21304050 if encrypted else 0x20304050, 5, *words)
    directory = root / 'data'
    directory.mkdir(exist_ok=True)
    destination = directory / archive.pack_name(category, language)
    destination.write_bytes(header + file_table + chunk_table + packed)
    return destination


@pytest.mark.parametrize('encrypted', [False, True])
def test_native_pack_schema_cross_chunk_and_patch(tmp_path, encrypted):
    raw = bytes(range(180))
    pack(tmp_path, {'synthetic/sample.core': raw}, encrypted=encrypted)
    reader = archive.PackSet(tmp_path)
    assert reader.read('synthetic/sample.core', offset=60, length=70) == raw[60:130]
    with pytest.raises(ValueError, match='bounds'):
        reader.read('synthetic/sample.core', offset=170, length=20)
    pack(tmp_path, {'synthetic/sample.core': b'patch version'}, category='patch', encrypted=encrypted)
    assert archive.PackSet(tmp_path).read('synthetic/sample.core') == b'patch version'


def test_pack_bounds_and_safe_paths(tmp_path):
    path = pack(tmp_path, {'synthetic/sample.core': b'test'})
    data = bytearray(path.read_bytes())
    struct.pack_into('<Q', data, 24, 3_000_000)
    path.write_bytes(data)
    with pytest.raises(ValueError, match='header'):
        archive.Archive(path)
    for value in ('../sample', '/absolute', 'a//b', 'a/../b', 'C:/sample', 'a\\b', ''):
        with pytest.raises(ValueError, match='virtual path'):
            archive.path_hash(value)


def test_actual_pack_hash_and_missing_locale(tmp_path):
    assert archive.pack_name('initial') == '7017f9bb9d52fc1c4433599203cc51b1.bin'
    assert len(ds.SUPPORTED_LOCALES) == 12
    assert len(ds.TEXT_LOCALES) == 20
    assert ds.probe_voice_pack(tmp_path, 'ja') == 'missing'
    assert ds.probe_voice_pack(tmp_path, 'zh-Hans') == 'unknown'
    pack(tmp_path, {'synthetic/ja.core': b'Japanese pack'}, language='japanese')
    assert ds.probe_voice_pack(tmp_path, 'ja') == 'present'


def test_empty_language_slots_do_not_shift_and_structural_bounds():
    body = identity(3) + text_payload({16: '日本語', 21: '简体中文', 23: 'Ελληνικά'})
    values = localized_text(body)
    assert values[1][0] == ''
    assert values[16][0] == '日本語'
    assert values[21][0] == '简体中文'
    assert values[23][0] == 'Ελληνικά'
    with pytest.raises(ValueError):
        localized_text(body[:-1])
    with pytest.raises(ValueError):
        sentence(identity(1) + sentence_payload() + b'extra')
    with pytest.raises(ValueError):
        core_objects(obj(SENTENCE, 1, sentence_payload()) * 2)


@pytest.mark.parametrize('language', archive.AUDIO_NAMES)
def test_all_official_voice_masks_and_offsets(language):
    values = localized_sound(identity(2) + sound_payload([language]))
    assert set(values) == {language}
    assert values[language]['stream'] == f'localized/synthetic/line.wem.{language}.core.stream'
    assert values[language]['offset'] == 3
    assert values[language]['length'] == 16
    assert localized_sound(identity(2) + sound_payload([])) == {}


def test_readable_only_schema_and_empty_streaming_image():
    body = identity(7) + ref() + ref(3) + ref(4) + ref() + b'\0' * 14
    assert readable(MAIL, body)['body'] == (None, identity(4).hex())
    interview = (identity(8) + b'\0' * 5 + ref(3) + ref(4) + ref() + b'\1'
                 + ref() * 3 + b'\3' + identity(0) + string('') + b'\0' * 9)
    assert readable(INTERVIEW, interview)['body'] == (None, identity(4).hex())
    with pytest.raises(ValueError):
        reference(archive.Cursor(b'\3' + identity(0) + string('')))


class FakePacks:
    def __init__(self, source='english', missing=False):
        dialogue = 'localized/sentences/ds_lines_mission/synthetic/sentences'
        cine = 'localized/sentences/ds_lines_cutscene/synthetic/sentences'
        ui = 'localized/sentences/ds_ui/ds_mail/simpletext'
        text = {number: f'Synthetic locale {locale}' for locale, number in ds.TEXT_LOCALES.items()}
        self.files = {
            dialogue + '.core': (obj(SENTENCE, 1, sentence_payload()) + obj(SOUND, 2, sound_payload())
                                  + obj(TEXT, 3, text_payload(text))),
            cine + '.core': obj(SENTENCE, 10, sentence_payload(None, 11)) + obj(TEXT, 11, text_payload(text)),
            ui + '.core': (obj(TEXT, 20, text_payload(text)) + obj(TEXT, 21, text_payload(text))
                          + obj(TEXT, 22, text_payload({number: '\n\t ' for number in ds.TEXT_LOCALES.values()}))),
            'ds/archives/mail_resource.core': obj(MAIL, 30, ref() + ref(20, ui) + ref(21, ui) + ref() + b'\0' * 14),
            'ds/archives/interviews_resource.core': b'',
        }
        self.packs = [('initial', source, None)]
        if not missing:
            for language in archive.AUDIO_NAMES:
                self.files[f'localized/synthetic/line.wem.{language}.core.stream'] = b'padRIFF\x08\0\0\0WAVEsyn!'
        self.paths = [dialogue, cine, ui]

    def manifest(self, with_links=False):
        return (self.paths, {}) if with_links else self.paths

    def has(self, path):
        return path in self.files

    def read(self, path, limit=0, offset=0, length=None):
        value = self.files[path]
        return value[offset:offset + length] if length is not None else value[offset:]


@pytest.mark.parametrize('locale', ds.SUPPORTED_LOCALES)
@pytest.mark.parametrize('missing', [False, True])
def test_index_language_bindings_unvoiced_and_missing_pack(monkeypatch, tmp_path, locale, missing):
    packs = FakePacks(ds.VOICE_LOCALES[locale], missing)
    monkeypatch.setattr(ds, '_packs', lambda *_args: packs)
    monkeypatch.setattr(ds, 'fingerprint', lambda *_args: 'unchanged')
    monkeypatch.setattr(ds, 'probe_voice_pack', lambda *_args: 'missing' if missing else 'present')
    result = ds.index_language(tmp_path, tmp_path, locale, ['zh-Hans'])
    rows = result['records']
    assert len(rows) == 4
    assert result['narrative_inventory']['blank_or_markup_only_localized_fields'] >= 1
    for row in rows:
        LocalDialogue(**row)
        assert row['texts'][locale] == f'Synthetic locale {locale}'
        assert row['texts']['zh-Hans'] == 'Synthetic locale zh-Hans'
    assert rows[0]['voice_status'] == ('unavailable' if missing else 'voiced')
    assert rows[1]['dialogue_kind'] == 'cinematic'
    assert rows[1]['voice_status'] == 'unavailable'
    assert [row['voice_status'] for row in rows[2:]] == ['unvoiced', 'unvoiced']
    if not missing:
        assert ds.extract_voice(tmp_path, rows[0]['audio'], None, None).startswith(b'RIFF')
        bad = {**rows[0]['audio'], 'offset': 0}
        with pytest.raises(ValueError, match='binding changed'):
            ds.extract_voice(tmp_path, bad, None, None)


def test_changes_keep_previous_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, '_packs', lambda *_args: FakePacks())
    stamps = iter(['before', 'after'])
    monkeypatch.setattr(ds, 'fingerprint', lambda *_args: next(stamps))
    with pytest.raises(ValueError, match='files changed') as failure:
        ds.index_language(tmp_path, tmp_path, 'en', [])
    assert failure.value.previous_snapshot_retained


def sequence_object(number, sorted_ids):
    body = (b'\0' * 2 + identity(number) + u('IB', 0, 3) + ref() * 2 + b'\0' * 3 + ref()
        + b'\0' * 10 + ref() * 2 + u('I', 0) + string('Synthetic scene')
        + b'\0' * 32 + string('') + b'\0' * 8 + u('IIiI', 0, 0, 600, len(sorted_ids))
        + b''.join(ref(item) for item in sorted_ids) + u('II', 0, 0) + b'\0' * 7
        + ref() + string('') + b'\0' * 13)
    return u('QI', cine.SEQUENCE, len(body)) + body


class FakeCinematics(FakePacks):
    def __init__(self, ambiguous=False):
        super().__init__()
        self.parent = 'levels/synthetic/cinematic_sequence'
        sound = 'ds/sounds/wwise_cinematics_sound_resource/synthetic/sound'
        subtitle_path = 'localized/sentences/ds_lines_cutscene/synthetic/sentences'
        subtitle = obj(cine.SUBTITLE, 100, u('iBi', 30, 1, 180) + ref(10, subtitle_path) + u('Bii', 0, 5, 10))
        event = obj(cine.WEM_EVENT, 101, u('iBi', 0, 1, 600) + ref()
            + u('BBBfBBB', 0, 0, 1, 0, 1, 0, 0) + ref(300, sound))
        ordered = obj(cine.SORTED, 200, u('iB', 0, 1) + ref(100) + identity(100) + u('II', 0, 0))
        ordered += obj(cine.SORTED, 201, u('iB', 0, 1) + ref(101) + identity(101) + u('II', 0, 0))
        self.files[self.parent + '.core'] = sequence_object(500, [200, 201, *([201] if ambiguous else [])]) + subtitle + event + ordered
        sound_obj = obj(cine.WEM_SOUND, 300, string('Synthetic full voice track') + ref() + b'\0' * 137 + ref(400))
        localized = b'\1' + identity(400) + u('IIIHfI', 123, 16, 0, 257, 20, sum(1 << ds.TEXT_LOCALES[l] for l in ds.VOICE_LOCALES))
        for locale, number in sorted(ds.TEXT_LOCALES.items(), key=lambda item: item[1]):
            if locale not in ds.VOICE_LOCALES:
                continue
            stream = f'ds/sounds/synthetic/wav/{ds.VOICE_LOCALES[locale]}/windows/voice'
            localized += string(stream, False) + identity(900) + u('IIIQ', 1, 3, 16, 0)
            self.files[stream + '.core.stream'] = b'padRIFF\x08\0\0\0WAVEsyn!'
        self.files[sound + '.core'] = sound_obj + u('QI', cine.WEM_LOCALIZED, len(localized)) + localized
        self.links = {self.parent: [subtitle_path, sound]}

    def manifest(self, with_links=False):
        return (self.paths, self.links) if with_links else self.paths


@pytest.mark.parametrize('locale', ds.SUPPORTED_LOCALES)
def test_authored_cinematic_graph_uses_complete_localized_track(monkeypatch, tmp_path, locale):
    packs = FakeCinematics()
    monkeypatch.setattr(ds, '_packs', lambda *_args: packs)
    monkeypatch.setattr(ds, 'fingerprint', lambda *_args: 'same')
    monkeypatch.setattr(ds, 'probe_voice_pack', lambda *_args: 'present')
    result = ds.index_language(tmp_path, tmp_path, locale, ['en'])
    scene = next(row for row in result['records'] if row['dialogue_kind'] == 'cinematic')
    LocalDialogue(**scene)
    assert scene['voice_status'] == 'voiced'
    assert scene['member_text_ids'] == ['deathstranding:sentence:' + identity(10).hex()]
    assert 'start_seconds' not in scene['audio']  # no fabricated subtitle-time cuts
    assert ds.extract_voice(tmp_path, scene['audio'], None, None) == b'RIFF\x08\0\0\0WAVEsyn!'
    with pytest.raises(ValueError, match='binding changed'):
        ds.extract_voice(tmp_path, {**scene['audio'], 'track_event': identity(999).hex()}, None, None)


def test_overlapping_cinematic_sources_remain_unavailable():
    packs = FakeCinematics(ambiguous=True)
    groups, _counts = cine.scene_bindings(packs, packs.links, 'en', 1, lambda _message: None)
    assert groups == []


def test_original_wem_uses_declared_riff_boundary():
    wem = b'RIFF\x08\0\0\0WAVEsyn!'
    assert ds._original_wem(wem + b'container trailer') == wem
    with pytest.raises(ValueError):
        ds._original_wem(wem[:-1])
    with pytest.raises(ValueError):
        ds._original_wem(b'not an original RIFF recording')


def test_missing_cinematic_recording_remains_unavailable(monkeypatch, tmp_path):
    packs = FakeCinematics()
    del packs.files['ds/sounds/synthetic/wav/english/windows/voice.core.stream']
    monkeypatch.setattr(ds, '_packs', lambda *_args: packs)
    monkeypatch.setattr(ds, 'fingerprint', lambda *_args: 'same')
    monkeypatch.setattr(ds, 'probe_voice_pack', lambda *_args: 'present')
    result = ds.index_language(tmp_path, tmp_path, 'en', [])
    scene = next(row for row in result['records'] if row['dialogue_kind'] == 'cinematic')
    assert scene['voice_status'] == 'unavailable'
    assert scene['audio'] is None
