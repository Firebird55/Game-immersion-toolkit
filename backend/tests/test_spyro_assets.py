"""Synthetic shipped-format regressions; no proprietary text or media fixtures."""
import hashlib
from pathlib import Path
import struct
import zlib

import pytest

from backend import spyro_assets as spyro
from backend.spyro_unreal import Package, PakSet, read_locres


def u(fmt, *values):
    return struct.pack('<' + fmt, *values)


def string(value, wide=False):
    raw = value.encode('utf-16-le' if wide else 'utf-8')
    return u('i', -(len(raw) // 2 + 1) if wide else len(raw) + 1) + raw + (b'\0\0' if wide else b'\0')


def locres(values):
    keys = b''
    texts = []
    for key, value in values.items():
        keys += string(key, True) + u('II', 123, len(texts))
        texts.append(value)
    directory = u('I', 1) + string('') + u('I', len(values)) + keys
    return (bytes.fromhex('0e147475674a03fc4a15909dc3377f1b') + b'\1' + u('Q', 25 + len(directory)) + directory
            + u('I', len(texts)) + b''.join(string(text, True) for text in texts))


def pak_file(root, files, compressed=()):
    payload = bytearray()
    directory = b''
    for name, raw in files.items():
        offset = len(payload)
        if name in compressed:
            block_size = 64
            chunks = [zlib.compress(raw[i:i + block_size]) for i in range(0, len(raw), block_size)]
            header_size = 57 + 16 * len(chunks)
            position = offset + header_size
            blocks = []
            for chunk in chunks:
                blocks.append((position, position + len(chunk)))
                position += len(chunk)
            data = b''.join(chunks)
            tail = u('I', len(blocks)) + b''.join(u('QQ', *block) for block in blocks) + u('BI', 0, block_size)
            method = 1
        else:
            data, tail, method = raw, u('BI', 0, 0), 0
        middle = u('QQI', len(data), len(raw), method) + hashlib.sha1(raw).digest() + tail
        payload += u('Q', 0) + middle + data
        directory += string(name) + u('Q', offset) + middle
    index = string('../../../') + u('I', len(files)) + directory
    footer = b'\0' + u('IIQQ', 0x5A6F12E1, 4, len(payload), len(index)) + hashlib.sha1(index).digest()
    folder = root / 'Falcon/Content/Paks'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'pakchunk0-WindowsNoEditor.pak'
    path.write_bytes(payload + index + footer)
    (root / 'Spyro.exe').touch()
    return path


def package_table(row_type, rows, referenced_table=None):
    names = []

    def name(value):
        if value not in names:
            names.append(value)
        return u('II', names.index(value), 0)

    def prop(key, kind, payload, extra=b''):
        return name(key) + name(kind) + u('II', len(payload), 0) + extra + b'\0' + payload

    def text(key):
        return u('IB', 0, 0) + string('') + string(key) + string('Synthetic source')

    def properties(row):
        result = b''
        for key, (kind, value) in row.items():
            if kind == 'TextProperty':
                result += prop(key, kind, text(value))
            elif kind == 'StructProperty':
                result += prop(key, kind, name(value) + string(''), name('SoftObjectPath') + b'\0' * 16)
            elif kind == 'BoolProperty':
                result += prop(key, kind, b'', bytes([value]))
            elif kind == 'NameProperty':
                result += prop(key, kind, name(value))
            else:
                result += prop(key, kind, u('i', value))
        return result + name('None')

    content = prop('RowStruct', 'ObjectProperty', u('i', -2)) + name('None') + u('II', 0, len(rows))
    for identity, row in rows.items():
        content += name(identity) + properties(row)
    imports = name('/Script/CoreUObject') + name('Class') + u('i', 0) + name('DataTable')
    imports += name('/Script/TfbPlugin') + name('ScriptStruct') + u('i', 0) + name(row_type)
    if referenced_table:
        imports += name('/Script/Engine') + name('DataTable') + u('i', -4) + name('SyntheticTable')
        imports += name('/Script/CoreUObject') + name('Package') + u('i', 0) + name(referenced_table)
    name_bytes = b''.join(string(value) + b'\0' * 4 for value in names)
    name_offset = 80
    import_offset = name_offset + len(name_bytes)
    export_offset = import_offset + len(imports)
    total = export_offset + 104
    header = u('Ii4II', 0x9E2A83C1, -7, 0, 0, 0, 0, total) + string('None') + u('I', 0)
    header += u('8I', len(names), name_offset, 0, 0, 1, export_offset, len(imports) // 28, import_offset)
    header += b'\0' * (name_offset - len(header))
    export = u('i', -1) + b'\0' * 24 + u('QQ', len(content), total) + b'\0' * 60
    return header + name_bytes + imports + export, content + bytes.fromhex('c1832a9e')


def bank(language, events, embedded=(), multi=False):
    objects = []
    media_index, media_data = b'', b''
    for number, (event_name, media) in enumerate(events.items()):
        sound_id, action_id = 500 + number, 700 + number
        sound = u('IIBII', sound_id, 0x40001, 0 if media in embedded else 2, media, 50) + b'\1'
        action = u('IH', action_id, 0x0403) + u('I', sound_id)
        event = u('IBI', spyro.wwise_hash(event_name), 1, action_id)
        if multi:
            event = u('IBII', spyro.wwise_hash(event_name), 2, action_id, action_id)
        objects.extend([(2, sound), (3, action), (4, event)])
        if media in embedded:
            wem = b'RIFF' + u('I', 16) + b'WAVE' + b'synthetic'
            media_index += u('III', media, len(media_data), len(wem))
            media_data += wem
    hierarchy = u('I', len(objects)) + b''.join(u('BI', kind, len(value)) + value for kind, value in objects)
    chunks = [(b'BKHD', u('III', 128, 111, spyro.wwise_hash(language))), (b'HIRC', hierarchy)]
    if media_data:
        chunks += [(b'DIDX', media_index), (b'DATA', media_data)]
    return b''.join(kind + u('I', len(value)) + value for kind, value in chunks)


def synthetic_install(root, missing_locale=None):
    files, voices = {}, {}
    texts = {'caption': 'First page{N}Second page', 'silent': 'Read this instruction', 'speaker': 'Example speaker', 'missing': 'Missing recording'}
    for game in (1, 2, 3):
        rows = {}
        for prefix, key in [('vo', 'caption'), ('tx', 'silent')]:
            identity = f'{prefix}_s{game}_synthetic'
            rows[identity] = {'VoicedLine': ('StructProperty', 'None'),
                'Text': ('TextProperty', key), 'DisplayName': ('TextProperty', 'speaker'),
                'IsSubtitle': ('BoolProperty', prefix == 'vo')}
        path = spyro._SOUND + f'VO_Spyro{game}/SyntheticTable'
        files[path + '.uasset'], files[path + '.uexp'] = package_table('TfbDialogueTableRow', rows)
        voices[f'vo_s{game}_synthetic'] = 900 + game
        caption = {'tfbDialogueDataTable_1': ('ObjectProperty', -3), 'RowName_2': ('NameProperty', f'vo_s{game}_synthetic'),
                   'SplitIndex_3': ('IntProperty', 1)}
        sub = spyro._SOUND + f'Subtitles/Synthetic{game}'
        files[sub + '.uasset'], files[sub + '.uexp'] = package_table('tfbSubtitleDataTableRow', {'page': caption}, f'/Sound/VO_Spyro{game}/SyntheticTable')
    for locale in spyro.SUPPORTED_LOCALES:
        for collection, values in [('VoiceLocalizations', texts), ('MenuLocalizations', {'menu': 'Synthetic menu'})]:
            path = f'Falcon/Content/Localization/{collection}/{spyro.TEXT_LOCALES[locale]}/{collection}.locres'
            files[path] = locres(values)
        if locale == missing_locale:
            continue
        prefix = spyro._WWISE + spyro.VOICE_LOCALES[locale] + '/'
        files[prefix + 'VO_Test.bnk'] = bank(spyro.VOICE_LOCALES[locale], voices, embedded=(901,))
        for media in (902, 903):
            files[prefix + str(media) + '.wem'] = b'RIFF' + u('I', 16) + b'WAVE' + b'synthetic'
    pak_file(root, files, compressed=[name for name in files if name.endswith('.locres')])
    return files


def test_pak_reads_bounded_compressed_blocks_and_rejects_directory_corruption(tmp_path):
    original = b'synthetic asset ' * 100
    path = pak_file(tmp_path, {'Falcon/sample': original}, ['Falcon/sample'])
    archive = PakSet(tmp_path)
    assert archive.read('Falcon/sample') == original
    with pytest.raises(ValueError, match='size limit'):
        archive.read('Falcon/sample', 10)
    damaged = bytearray(path.read_bytes()); damaged[-46] ^= 1; path.write_bytes(damaged)
    with pytest.raises(ValueError, match='checksum'):
        PakSet(tmp_path)


def test_pak_rejects_traversal_names(tmp_path):
    pak_file(tmp_path, {'../outside': b'x'})
    with pytest.raises(ValueError, match='Unsafe'):
        PakSet(tmp_path)


def test_locres_preserves_utf16_identity_and_rejects_bad_string_index():
    data = locres({'one': 'نص تجريبي', 'two': 'Övning'})
    assert read_locres(data)['', 'one'] == (123, 'نص تجريبي')
    with pytest.raises(ValueError):
        read_locres(data[:-1])
    damaged = bytearray(data)
    string_offset = struct.unpack_from('<Q', data, 17)[0]
    struct.pack_into('<I', damaged, string_offset - 4, 999)
    with pytest.raises(ValueError):
        read_locres(damaged)


def test_tagged_table_reads_ftext_and_null_soft_voice_without_guessing():
    asset, data = package_table('TfbDialogueTableRow', {'tx_example': {'Text': ('TextProperty', 'key'), 'VoicedLine': ('StructProperty', 'None')}})
    kind, rows = Package(asset).table(data)
    assert kind == 'TfbDialogueTableRow'
    assert rows['tx_example']['Text'] == ('', 'key', 'Synthetic source')
    assert rows['tx_example']['VoicedLine'] == ('None', '')
    with pytest.raises(ValueError):
        Package(asset).table(data[:-1])


def test_bank_resolves_authored_graph_embedded_media_and_rejects_locale_mismatch():
    data = bank('latam', {'vo_example': 77}, embedded=(77,))
    events, embedded, unresolved = spyro.read_bank(data, 'latam')
    assert events == {spyro.wwise_hash('vo_example'): 77}
    offset, size = embedded[77]
    assert data[offset:offset + size].startswith(b'RIFF')
    assert not unresolved
    with pytest.raises(ValueError, match='language'):
        spyro.read_bank(data, 'es')
    events, _, unresolved = spyro.read_bank(bank('latam', {'vo_example': 77}, multi=True), 'latam')
    assert not events and unresolved == {spyro.wwise_hash('vo_example')}


@pytest.mark.parametrize('locale', spyro.SUPPORTED_LOCALES)
def test_every_official_locale_joins_all_three_games_and_original_audio(tmp_path, locale):
    synthetic_install(tmp_path)
    payload = spyro.index_language(tmp_path, tmp_path, locale, ['en', 'no'])
    records = payload['records']
    assert len(records) == 7
    assert sum(row['voice_status'] == 'voiced' for row in records) == 3
    assert sum(row['voice_status'] == 'unvoiced' for row in records) == 3
    assert sum(row['voice_status'] == 'unknown' for row in records) == 1
    assert payload['narrative_inventory']['unresolved_cinematic_row_references'] == 0
    for row in records:
        if row['audio']:
            assert row['ocr_texts'][locale] == ['First page', 'Second page']
            assert row['source_text'] == 'First page Second page'
            assert spyro.extract_voice(tmp_path, row['audio'], Path(), Path()).startswith(b'RIFF')


def test_missing_pack_is_unavailable_while_explicit_text_only_rows_remain_unvoiced(tmp_path):
    synthetic_install(tmp_path, missing_locale='ar')
    result = spyro.index_language(tmp_path, tmp_path, 'ar', [])
    assert spyro.probe_voice_pack(tmp_path, 'ar') == 'missing'
    assert sum(row['voice_status'] == 'unavailable' for row in result['records']) == 3
    assert sum(row['voice_status'] == 'unvoiced' for row in result['records']) == 3
    assert any('Steam Properties' in warning for warning in result['coverage_warnings'])


def test_extraction_revalidates_event_media_locale_and_embedded_binding(tmp_path):
    synthetic_install(tmp_path)
    row = next(row for row in spyro.index_language(tmp_path, tmp_path, 'en', [])['records'] if row['audio'])
    for replacement in [{'media': 1234}, {'embedded': False}, {'locale': 'fr'}, {'bank': '../outside'}]:
        with pytest.raises(ValueError):
            spyro.extract_voice(tmp_path, {**row['audio'], **replacement}, Path(), Path())
