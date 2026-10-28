"""Synthetic Director's Cut fixtures; no shipped text or audio is included."""
import json
import struct
from types import SimpleNamespace
import wave
import zlib

import pytest

from backend import deusex_hr_assets as game
from backend import deusex_hr_formats as fmt
from backend.local_game import LocalDialogue
from backend.multilingual_index import MultilingualTextIndex
from backend.preparation_errors import PreparationFailure


def pack(pattern, *values):
    return struct.pack('<' + pattern, *values)


def local_table(locale, text):
    strings = [None, text, 'Synthetic undecided interface text.', 'Synthetic silent document.']
    body, offsets = b'', []
    for value in strings:
        offsets.append(8 + len(strings) * 4 + len(body) if value else 0)
        if value:
            body += value.encode('utf-8') + b'\0'
    return pack('II', game.TEXT_LOCALES[locale], len(strings)) + pack('4I', *offsets) + body


def drm(sections, root=0):
    header = pack('8I', 21, 0, 0, 0, 0, 1, len(sections), root)
    for section in sections:
        header += pack('IBBHIII', len(section.data), section.kind, 0, 0,
                       (len(section.fixup) << 8) | (section.subtype << 1), section.identity, section.locale)
    result = header + b'\0' * (-len(header) % 16)
    for section in sections:
        result += section.fixup + b'\0' * (-len(section.fixup) % 16)
        result += section.data + b'\0' * (-len(section.data) % 16)
    return result


def cdrm(data, codec=2):
    compressed = zlib.compress(data) if codec == 2 else data
    return b'CDRM' + pack('3I', 2, 1, 8) + pack('II', (len(data) << 8) | codec, len(compressed)) + b'\0' * 8 + compressed


VOICE_PATH = 'vo\\eng\\test\\synthetic_dia_001'
MEDIA = fmt.filename_hash('pc-w\\audio\\streams\\' + VOICE_PATH + '.mul')
OWNER = 100
SOUND = 200


def sound_section(path=VOICE_PATH):
    data = bytearray(144)
    struct.pack_into('<I', data, 0, 5)
    struct.pack_into('<I', data, 96, 4)
    struct.pack_into('<H', data, 130, 1)
    data.extend(path.encode('ascii') + b'\0')
    references = {4: 16, 16: 96, 100: 112, 112: 144}
    fixup = pack('5I', len(references), 0, 0, 0, 0) + b''.join(pack('II', *item) for item in references.items())
    return fmt.Section(SOUND, 7, 13, 0xffffffff, bytes(data), fixup)


def mul(locale='en', channels=1):
    head = pack('4I', 44100, 0xffffffff, 44100, channels) + b'\0' * (2048 - 16)
    fsb = b'FSB4' + pack('I', 1) + b'\0' * 40 + locale.encode('ascii')
    block = b''.join(pack('4I', len(fsb), channel, 0x2001, 0) + fsb for channel in range(channels))
    return head + pack('4I', 0, len(block), 0, 0) + block + b'\0' * (-len(block) % 16)


def install(root, missing_voice=None, missing_text=None, invalid_time=False, mismatch_translation=False, cinematic=False):
    (root / 'DXHRDC.exe').touch()
    entries = [(OWNER, 0xffffffff, cdrm(drm([sound_section()])))]
    email = drm([fmt.Section(0, 0, 0, 0xffffffff, pack('II', 1, 201), b''),
                 fmt.Section(201, 7, 0, 0xffffffff, pack('4H', 3, 3, 3, 3) + b'\0' * 45, b'')])
    entries.append((fmt.filename_hash('pc-w\\email_database.drm'), 0xffffffff, email))
    if cinematic:
        definition = movie_section()
        binding = game.movies.movie_binding(definition)
        entries.extend([(501, 0xffffffff, cdrm(drm([definition]))),
                        (binding['media'], 0xffffffff, usm())])
    for locale in game.SUPPORTED_LOCALES:
        mask = fmt.LOCALE_BITS[locale]
        time = '9.0' if invalid_time else '0.4'
        text = f'First synthetic caption {locale}.//({time})\\Second synthetic caption {locale}.'
        if mismatch_translation and locale == 'fr':
            text = 'One unsplit synthetic translation.'
        if locale != missing_text:
            entries.append((game._LOCALS, mask, local_table(locale, text)))
        if locale != missing_voice:
            entries.append((MEDIA, mask, mul(locale)))
    entries.sort()
    header_size = 72 + len(entries) * 20
    start = (header_size + 2047) // 2048 * 2048
    content, directory = bytearray(), b''
    for identity, locale, data in entries:
        directory += pack('4I', len(data), (start + len(content)) // 2048, locale, 0)
        content.extend(data)
        content.extend(b'\0' * (-len(content) % 2048))
    header = pack('I', 0x7ff00000) + b'pc-w\0' + b'\0' * 59 + pack('I', len(entries))
    header += b''.join(pack('I', entry[0]) for entry in entries) + directory
    (root / 'BIGFILE.000').write_bytes(header + b'\0' * (start-len(header)) + content)


def utf_table(columns, rows):
    strings, schema, body = bytearray(b'\0'), bytearray(), bytearray()

    def string(value):
        offset = len(strings)
        strings.extend(value.encode() + b'\0')
        return offset

    for name, kind in columns:
        schema.extend(bytes([0x50 | kind]) + struct.pack('>I', string(name)))
    for row in rows:
        for name, kind in columns:
            body.extend(struct.pack('>I', string(row[name]) if kind == 10 else row[name]))
    rows_at = 32 + len(schema)
    strings_at = rows_at + len(body)
    size = strings_at + len(strings)
    return b'@UTF' + struct.pack('>IIIIIHHI', size-8, rows_at-8, strings_at-8, size-8, 0,
        len(columns), len(columns)*4, len(rows)) + schema + body + strings


def packet(tag, kind, channel, payload):
    return tag + struct.pack('>I', 24 + len(payload)) + bytes([0, 24, 0, 0, channel, 0, 0, kind]) + bytes(16) + payload


def adx(locale='en'):
    header = bytearray(32)
    header[:8] = b'\x80\0\0\x1c\x03\x12\x04\x01'
    struct.pack_into('>II', header, 8, 44100, 44100)
    header[18] = 4
    header[26:32] = b'(c)CRI'
    return bytes(header) + bytes(18) + locale.encode()


MOVIE_NAMES = {'en': 'eng', 'fr': 'fra', 'de': 'ger', 'it': 'ita', 'es-ES': 'spa'}
MOVIE_TRACKS = {'en': 4, 'fr': 2, 'de': 7, 'it': 1, 'es-ES': 6}


def usm(duplicate=False):
    names = [{'filename': 'synthetic_vo_' + MOVIE_NAMES[locale] + '.wav',
              'stmid': int.from_bytes(b'@SFA', 'big'), 'chno': track}
             for locale, track in MOVIE_TRACKS.items()]
    if duplicate:
        names.append({**names[0], 'chno': 9})
    result = packet(b'CRID', 1, 0, utf_table([('filename', 10), ('stmid', 4), ('chno', 4)], names))
    channels = [*MOVIE_TRACKS.values(), *([9] if duplicate else [])]
    for channel in channels:
        result += packet(b'@SFA', 1, channel, utf_table([(key, 4) for key in ('sampling_rate', 'total_samples', 'num_channels')],
            [{'sampling_rate': 44100, 'total_samples': 44100, 'num_channels': 1}]))
    for locale, channel in MOVIE_TRACKS.items():
        result += packet(b'@SFA', 0, channel, adx(locale))
    if duplicate:
        result += packet(b'@SFA', 0, 9, adx())
    return result


def movie_section(localized_basename='synthetic'):
    data, references = bytearray(32), {}

    def add(value):
        offset = len(data)
        data.extend(value)
        data.extend(bytes(-len(data) % 16))
        return offset

    def ref(origin, target):
        references[origin] = target
        struct.pack_into('<I', data, origin, 0xbeebbeeb)

    folder = add(b'cinematics\\synthetic\0')
    name = add(b'cinematics\\synthetic\\synthetic.avi\0')
    ref(0, folder)
    ref(4, name)
    ref(8, name)
    ref(20, folder)
    struct.pack_into('<I', data, 16, 5)
    table = add(bytes(40 * 5))
    ref(12, table)
    for index, (locale, code) in enumerate(MOVIE_NAMES.items()):
        at = table + index * 40
        # Deliberately inconsistent numeric language IDs demonstrate that the
        # exact authored source filename, not channel ordinal, picks voices.
        struct.pack_into('<II', data, at+16, 1, 0)
        resource = add(bytes(16))
        basename = 'synthetic' if locale == 'en' else localized_basename
        path = add(('cinematics\\synthetic\\' + code + '\\' + basename + '_vo_' + code + '.wav\0').encode())
        ref(resource, path)
        ref(at+12, resource)
        if locale == 'en':
            cues = add(pack('III', 100, 900, 1))
            ref(at+32, cues)
            struct.pack_into('<I', data, at+36, 1)
    fixup = pack('5I', len(references), 0, 0, 0, 0) + b''.join(pack('II', *item) for item in references.items())
    return fmt.Section(500, 7, 0, 0xffffffff, bytes(data), fixup)


@pytest.mark.parametrize('locale', game.SUPPORTED_LOCALES)
def test_all_official_voice_locales_follow_identical_authored_schema(tmp_path, locale):
    install(tmp_path)
    assert game.discover_install([tmp_path]) == tmp_path
    assert game.probe_voice_pack(tmp_path, locale) == 'present'
    payload = game.index_language(tmp_path, tmp_path, locale, ['en', 'fr'])
    rows = [row for row in payload['records'] if row['voice_status'] == 'voiced']
    assert len(rows) == 2
    assert rows[0]['source_text'] == f'First synthetic caption {locale}.'
    assert rows[1]['source_text'] == f'Second synthetic caption {locale}.'
    assert rows[0]['text_id'] != rows[1]['text_id']
    assert (rows[0]['audio']['start_ms'], rows[0]['audio']['end_ms']) == (0, 400)
    assert (rows[1]['audio']['start_ms'], rows[1]['audio']['end_ms']) == (400, 1000)
    assert game.extract_voice(tmp_path, rows[0]['audio'], None, None).endswith(locale.encode())
    assert {row['voice_status'] for row in payload['records']} == {'voiced', 'unvoiced', 'unknown'}
    for row in payload['records']:
        LocalDialogue(**row)
    (tmp_path / 'textmap.json').write_text(json.dumps(payload), encoding='utf-8')
    index = MultilingualTextIndex(game.GAME, tmp_path)
    assert index.ready, index.message
    assert index.match_lines([rows[0]['source_text']], exact_only=True)
    assert not index.match_lines(['Synthetic silent document.'], exact_only=True)
    index.capture_unvoiced = True
    assert index.match_lines(['Synthetic silent document.'], exact_only=True)


def test_missing_pack_stays_actionable_and_never_silent(tmp_path):
    install(tmp_path, missing_voice='fr')
    assert game.probe_voice_pack(tmp_path, 'fr') == 'missing'
    payload = game.index_language(tmp_path, tmp_path, 'fr', [])
    assert all(row['voice_status'] == 'unavailable' for row in payload['records'] if row['text_id'].startswith(game.GAME + ':1:'))
    assert 'Steam Properties' in ' '.join(payload['coverage_warnings'])


def test_missing_text_requires_pack_and_unsupported_regional_voices_are_not_invented(tmp_path):
    install(tmp_path, missing_text='de')
    with pytest.raises(PreparationFailure, match='selected Deus Ex language pack'):
        game.index_language(tmp_path, tmp_path, 'de', [])
    assert game.probe_voice_pack(tmp_path, 'ru') == 'unknown'
    with pytest.raises(ValueError, match='Unsupported original'):
        game.index_language(tmp_path, tmp_path, 'ru', [])


def test_invalid_authored_times_use_full_track_without_future_caption_text(tmp_path):
    install(tmp_path, invalid_time=True, mismatch_translation=True)
    payload = game.index_language(tmp_path, tmp_path, 'en', ['fr'])
    rows = [row for row in payload['records'] if row['audio']]
    assert len(rows) == 2
    for row in rows:
        assert row['audio']['playback_scope'] == 'full_track'
        assert row['dialogue_kind'].endswith('_full_track')
        assert 'start_ms' not in row['audio']
        assert 'fr' not in row['texts']
    assert 'Second' not in rows[0]['source_text']


def test_extraction_revalidates_original_sound_binding(tmp_path):
    install(tmp_path)
    payload = game.index_language(tmp_path, tmp_path, 'en', [])
    audio = next(row['audio'] for row in payload['records'] if row['audio'])
    for field in ('caption', 'media', 'sound', 'owner'):
        with pytest.raises(PreparationFailure):
            game.extract_voice(tmp_path, {**audio, field: audio[field] + 1}, None, None)
    with pytest.raises(PreparationFailure):
        game.extract_voice(tmp_path, {**audio, 'locale': '../../en'}, None, None)


def test_bounds_compression_fixups_and_multichannel_audio_fail_closed(tmp_path):
    install(tmp_path)
    assert fmt.filename_hash('pc-w\\local\\locals.bin') == 0x7cd333d3
    section = sound_section()
    assert fmt.stream_binding(section) == (1, VOICE_PATH, MEDIA)
    with pytest.raises(ValueError, match='Unsafe'):
        fmt.stream_binding(sound_section('vo\\eng\\..\\synthetic'))
    with pytest.raises(ValueError, match='multichannel'):
        fmt.demux_voice(mul(channels=2))
    with pytest.raises(ValueError):
        fmt.decompress(cdrm(b'synthetic', codec=3))
    truncated = cdrm(drm([section]))[:-8]
    with pytest.raises(ValueError):
        fmt.sections(truncated)
    bad = bytearray(local_table('en', 'Synthetic text.'))
    struct.pack_into('<I', bad, 12, len(bad) + 1)
    with pytest.raises(ValueError, match='offset'):
        fmt.locals_table(bytes(bad))
    archive = fmt.Archive(tmp_path)
    with pytest.raises(ValueError, match='range'):
        archive.read(archive.entries[0], -1)


def test_changed_files_retain_previous_snapshot(tmp_path, monkeypatch):
    install(tmp_path)
    stamps = iter(['before', 'after'])
    monkeypatch.setattr(game, 'fingerprint', lambda _root: next(stamps))
    with pytest.raises(PreparationFailure) as error:
        game.index_language(tmp_path, tmp_path, 'en', [])
    assert error.value.game_files_changed
    assert error.value.previous_snapshot_retained


@pytest.mark.parametrize('locale', game.SUPPORTED_LOCALES)
def test_authored_cinematic_locale_track_and_caption_times(tmp_path, locale):
    install(tmp_path, cinematic=True)
    payload = game.index_language(tmp_path, tmp_path, locale, [])
    rows = [row for row in payload['records'] if row['dialogue_kind'] == 'cinematic']
    assert len(rows) == 2
    assert [(row['audio']['start_ms'], row['audio']['end_ms']) for row in rows] == [(100, 500), (500, 900)]
    assert all(row['audio']['track'] == MOVIE_TRACKS[locale] for row in rows)
    assert all('Second' not in row['source_text'] for row in rows[:1])
    assert game.extract_voice(tmp_path, rows[0]['audio'], None, None) == adx(locale)
    with pytest.raises(PreparationFailure):
        game.extract_voice(tmp_path, {**rows[0]['audio'], 'track': 0}, None, None)
    with pytest.raises(PreparationFailure):
        game.extract_voice(tmp_path, {**rows[0]['audio'], 'caption': 3}, None, None)


def test_cri_duplicate_streams_and_decoder_hook(tmp_path, monkeypatch):
    data = usm(duplicate=True)

    class MemoryArchive:
        def read(self, _entry, offset, length):
            return data[offset:offset+length]

    archive, entry = MemoryArchive(), SimpleNamespace(size=len(data))
    tracks = game.movies.movie_tracks(archive, entry)
    assert tracks['synthetic_vo_eng.wav']['duplicate_tracks'] == [9]
    assert game.movies.demux_adx(archive, entry, 9) == adx()
    output = tmp_path / 'decoded.wav'

    def decode(command, **_options):
        source = game.Path(command[-1])
        assert source.suffix == '.adx'
        assert source.read_bytes() == adx()
        with wave.open(str(output), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(44100)
            stream.writeframes(bytes(44100 * 2))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(game.subprocess, 'run', decode)
    game.decode_voice_source(adx(), {'decoder_format': 'adx', 'channels': 1, 'rate': 44100, 'samples': 44100},
                             output, 'verified-decoder', tmp_path / 'scratch')
    assert output.is_file()
    assert not list((tmp_path / 'scratch').iterdir())
    with pytest.raises(ValueError, match='original CRI ADX'):
        game.decode_voice_source(b'not audio', {'decoder_format': 'adx'}, output, 'decoder', tmp_path)


def test_choice_transition_labels_are_not_selected_speech():
    data = bytearray(300)
    struct.pack_into('<III', data, 112, 1, 0xbeebbeeb, 1)
    struct.pack_into('<I', data, 124, 0xbeebbeeb)
    struct.pack_into('<III', data, 176, 0, 0, 1)
    struct.pack_into('<HH', data, 212, 44, 45)
    name = b'dtp\\conversation\\sharednodes\\Conversation_Choice.dtp\0'
    data[224:224+len(name)] = name
    references = {116: 128, 124: 176, 132: 224, 192: 208}
    fixup = pack('5I', len(references), 0, 0, 0, 0) + b''.join(pack('II', *item) for item in references.items())
    section = fmt.Section(1, 7, 42, 0xffffffff, bytes(data), fixup)
    assert fmt.choice_text_ids(section) == {44, 45}
    struct.pack_into('<I', data, 184, 7)
    with pytest.raises(ValueError, match='choice transition'):
        fmt.choice_text_ids(fmt.Section(1, 7, 42, 0xffffffff, bytes(data), fixup))


def test_movie_single_performance_uses_authored_locale_names_even_when_basenames_differ():
    binding = game.movies.movie_binding(movie_section(localized_basename='different_authored_name'))
    assert len(binding['variants']) == 1
    group = next(iter(binding['variants'].values()))
    assert group['cues'] == [(100, 900, 1)]
    assert group['voices']['en'] == 'synthetic_vo_eng.wav'
    assert group['voices']['fr'] == 'different_authored_name_vo_fra.wav'


def test_stereo_mul_preserves_both_original_channels(tmp_path, monkeypatch):
    data, output = mul(channels=2), tmp_path / 'stereo.wav'
    streams = fmt.demux_streams(data)
    assert len(streams) == 2 and all(stream.startswith(b'FSB4') for stream in streams)

    def decode(command, **_options):
        channel = int(game.Path(command[-1]).stem.rsplit('-', 1)[-1])
        with wave.open(command[3], 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(pack('h', 100 + channel) * 44100)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(game.subprocess, 'run', decode)
    game.decode_voice_source(data, {'decoder_format': 'mul', 'channels': 2, 'rate': 44100, 'samples': 44100},
                             output, 'verified-decoder', tmp_path / 'scratch')
    with wave.open(str(output)) as wav:
        assert wav.getnchannels() == 2
        assert struct.unpack('<4h', wav.readframes(2)) == (100, 101, 100, 101)
    assert not list((tmp_path / 'scratch').iterdir())
