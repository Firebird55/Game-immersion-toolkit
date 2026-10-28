"""Persona 5 Royal's official message pages and original CRI voice cues."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import urllib.error
import urllib.request
import wave

from .persona_cri import Cpk, awb_entries, invalid, read_acb, safe_name
from .persona_message import package_members, read_messages
from .preparation_errors import PreparationFailure
from .textmaps import display_text

GAME = 'persona5royal'
LANGUAGE_INDEX_VERSION = 1
SUPPORTED_LOCALES = ('en', 'ja')
TEXT_LOCALES = {'en': 'EN', 'fr': 'FR', 'it': 'IT', 'de': 'DE', 'es-ES': 'ES',
                'ja': 'JP', 'ko': 'KR', 'zh-Hans': 'SC', 'zh-Hant': 'TC'}
VOICE_PACKS = {'en': 'SOUND_E', 'ja': 'SOUND_J'}
_CHARSET_COMMIT = '05483fe12f9c482ee17f38ded2e115f4c55015b3'
_CHARSET_ROOT = f'https://raw.githubusercontent.com/tge-was-taken/Atlus-Script-Tools/{_CHARSET_COMMIT}/'
_CHARSETS = {
    'P5R_EFIGS': 'f43a1791f02522bd36312bdf2dbb650cf09363bfb2a56424a1a44356d8beddd2',
    'P5R_Japanese': '77ab77071ea92b1b3caf3dbbcc8e5f2ab015168c3491c5335edddfd60118f578',
    'P5R_CHS': 'f29402d9813794ffa13cdbbcee07f044389a9fb6057554564eccd11ab6f2f83b',
    'P5R_CHT': 'f623e732689b0c8ab4e479caf6b439b0f99ab7496ebfb548c200fc53de661411',
    'P5_Korean': '95f13f6d3dd18221903c41bc147c2bca02f7bc082176b1ed30f74e550e90fcbb'}
_LICENSE_HASH = 'c53a65c2fd561c87eaabf1072ef5dcab8653042bc15308465f52413585eb6271'


def discover_install(candidates=None):
    if candidates is None:
        from .game_paths import discover_install as discover
        return discover(GAME)
    return next((Path(path) for path in candidates if (Path(path) / 'P5R.exe').is_file()
                 and (Path(path) / 'CPK/BASE.CPK').is_file()), None)


def archive_sources(install):
    allowed = {'BASE', 'MOVIE_JE', 'MOVIE_J', *TEXT_LOCALES.values(), *VOICE_PACKS.values()}
    return sorted((path for path in (Path(install) / 'CPK').glob('*.CPK') if path.stem in allowed), key=lambda p: p.name)


def fingerprint(install):
    return hashlib.sha256('|'.join(f'{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}'
                                  for p in archive_sources(install)).encode()).hexdigest()


def probe_voice_pack(install, locale):
    if locale not in SUPPORTED_LOCALES:
        return 'unknown'
    path = Path(install) / 'CPK' / (VOICE_PACKS[locale] + '.CPK')
    if not path.is_file():
        return 'missing'
    try:
        bank = Cpk(path)
        return 'present' if any(name.startswith('sound/event/') and name.endswith('.acb') for name in bank.entries) else 'incomplete'
    except (OSError, ValueError, PreparationFailure):
        return 'incomplete'


def _metadata(path, relative, expected):
    if path.is_file():
        if path.stat().st_size <= 256 * 1024:
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() == expected:
                return data
    try:
        with urllib.request.urlopen(_CHARSET_ROOT + relative, timeout=30) as response:
            data = response.read(256 * 1024 + 1)
    except (OSError, urllib.error.URLError) as error:
        raise PreparationFailure('persona5_charset_download',
            'Persona character metadata is not cached. Connect to the internet and retry Prepare; subsequent preparation works offline with the verified cache.') from error
    if len(data) > 256 * 1024 or hashlib.sha256(data).hexdigest() != expected:
        raise invalid('Persona character metadata failed its pinned checksum.')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.pending')
    temporary.write_bytes(data)
    temporary.replace(path)
    return data


def load_charset(data_dir, locale, progress):
    name = {'ja': 'P5R_Japanese', 'ko': 'P5_Korean', 'zh-Hans': 'P5R_CHS', 'zh-Hant': 'P5R_CHT'}.get(locale, 'P5R_EFIGS')
    directory = Path(data_dir) / 'persona5-charsets'
    progress(f'Checking verified Persona {locale} character metadata (first preparation needs internet)')
    _metadata(directory / 'AtlusScriptTools-LICENSE.txt', 'LICENSE.txt', _LICENSE_HASH)
    data = _metadata(directory / (name + '.tsv'), 'Source/AtlusScriptLibrary/Charsets/' + name + '.tsv', _CHARSETS[name])
    (directory / 'NOTICE.txt').write_text(
        'Character mapping metadata from Atlus Script Tools, TGE and contributors.\n'
        'Upstream license: GNU General Public License version 3; see AtlusScriptTools-LICENSE.txt.\n'
        f'Source: {_CHARSET_ROOT}Source/AtlusScriptLibrary/Charsets/{name}.tsv\n'
        'Only data tables are downloaded; no upstream program is executed.\n', encoding='utf-8')
    values = [value for line in data.decode('utf-8-sig').splitlines() for value in line.split('\t')]
    if not 128 <= len(values) <= 15000:
        raise invalid('Invalid Persona character table.')
    return [chr(int(value[2:], 16)) if re.fullmatch(r'\\u[0-9a-fA-F]{4}', value) else value for value in values]


def _category(path, choice):
    if choice:
        return 'choice'
    if path.startswith('camp/chat/') or path.startswith('font/chat/'):
        return 'phone_message'
    if path.startswith('event_data/'):
        return 'story_or_social_event'
    if path.startswith('battle/'):
        return 'battle_dialogue'
    if path.startswith(('field/npc/', 'field/assist/')):
        return 'ambient_or_npc_dialogue'
    if path.startswith(('script/', 'field/')):
        return 'field_dialogue'
    if path.startswith(('init/', 'mission/', 'tutorial/', 'minigame/', 'mypalace/')):
        return 'readable_or_system_text'
    return 'other_message'


def _bank_path(path, command):
    """Context-bound event selector; never search unrelated banks by cue number."""
    if len(command) != 6 or command[0] not in (1, 6, 8) or command[1] != 0:
        return None
    stem = PurePosixPath(path.split('!')[-1]).stem
    if path.startswith('event_data/') and re.fullmatch(r'e\d{3}_\d{3}', stem) and command[2] == 0:
        return f'sound/event/{stem}.acb'
    if path.startswith('battle/event/script/') and re.fullmatch(r'[0-9a-f]{4}', stem) and command[2] == 2:
        return f'sound/event_battle/e{int(stem, 16):03x}.acb'
    return None


def _wave_data(archive, name, bank, ref):
    if ref['streamed']:
        entry = archive.entries.get(name[:-4] + '.awb')
        if entry is None or entry.size != entry.extracted or not bank['stream_header']:
            return None
        table = awb_entries(bank['stream_header'], entry.size)
        if ref['id'] not in table:
            return None
        offset, size = table[ref['id']]
        return archive.read_at(entry.offset + offset, size, 32 * 1024 * 1024)
    table = awb_entries(bank['embedded'], len(bank['embedded']))
    if ref['id'] not in table:
        return None
    offset, size = table[ref['id']]
    return bank['embedded'][offset:offset + size]


def silent_adx(data):
    """Verify an authored zero-residual ADX silence cue; absence is never silence."""
    if not data or len(data) < 24 or data[:2] != b'\x80\0' or data[4:7] != b'\3\x12\4' or data[7] != 1:
        return False
    start = struct.unpack_from('>H', data, 2)[0] + 4
    samples = struct.unpack_from('>I', data, 12)[0]
    blocks = (samples + 31) // 32
    if not 0 < samples <= 48000 * 10 or start + blocks * 18 > len(data):
        return False
    return all(not any(data[at + 2:at + 18]) for at in range(start, start + blocks * 18, 18))


def _script_tables(archive, charset, inventory, progress):
    result = {}
    paths = [path for path in archive.entries if path.endswith(('.bf', '.bmd', '.msg'))]
    packages = [path for path in archive.entries if path.endswith(('.pak', '.pac'))]

    def consume(path, data, depth=0):
        if path.endswith(('.bf', '.bmd', '.msg')):
            if len(data) >= 12 and data[8:12] in (b'MSG1', b'1GSM', b'FLW0', b'0WLF'):
                endian = '<' if data[8:12] in (b'MSG1', b'0WLF') else '>'
                declared = struct.unpack_from(endian + 'I', data, 4)[0]
                # Named packages round script payloads to 32 bytes; padding
                # can contain stale header bytes and is outside the script.
                if depth and declared < len(data) and len(data) == (declared + 31) // 32 * 32:
                    data = data[:declared]
            else:
                inventory['nonbinary_message_sources'] += 1
                return
            for row in read_messages(data, charset):
                result[path, row['ordinal']] = row
            inventory['message_sources'] += 1
        elif path.endswith(('.pak', '.pac', '.bin')):
            if depth >= 3:
                inventory['unresolved_nested_packages'] += 1
                return
            for child, payload in package_members(data):
                if child.endswith(('.bf', '.bmd', '.msg', '.pak', '.pac')):
                    consume(path + '!' + child, payload, depth + 1)

    for number, path in enumerate(paths + packages):
        consume(path, archive.read(path))
        if number % 300 == 0:
            progress(f'Reading Persona message sources: {number:,}/{len(paths) + len(packages):,}')
    inventory['unparsed_table_or_binary_sources'] += sum(path.endswith(('.tbl', '.ftd', '.bin')) and not path.startswith('model/') for path in archive.entries)
    return result


def index_language(install, data_dir, source_locale, target_locales, progress=lambda _message: None):
    from .languages import resolve_locale
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Persona 5 Royal study/audio locale')
    install = Path(install)
    stamp, inventory = fingerprint(install), Counter()
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    text_path = install / 'CPK' / (TEXT_LOCALES[source_locale] + '.CPK')
    if not text_path.is_file():
        raise PreparationFailure('persona5_missing_text_pack',
            'The selected Persona 5 Royal text pack is missing. Select the study language in Steam Properties → Language, finish its download, then Prepare again. Voice selection is separate in the game settings.')
    tables = {}
    for locale in sorted({source_locale, 'en', *(locale for locale in targets.values() if locale)}):
        path = install / 'CPK' / (TEXT_LOCALES[locale] + '.CPK')
        if path.is_file():
            tables[locale] = _script_tables(Cpk(path), load_charset(data_dir, locale, progress), inventory, progress)
    voice_path = install / 'CPK' / (VOICE_PACKS[source_locale] + '.CPK')
    voices = Cpk(voice_path) if voice_path.is_file() else None
    base_path = install / 'CPK/BASE.CPK'
    base = Cpk(base_path) if base_path.is_file() else None

    @lru_cache(maxsize=2048)
    def bank(name):
        if voices is None or name not in voices.entries:
            return None
        result = read_acb(voices.read(name, 64 * 1024 * 1024))
        stream_entry = voices.entries.get(name[:-4] + '.awb')
        streamed = (awb_entries(result['stream_header'], stream_entry.size)
                    if stream_entry and stream_entry.size == stream_entry.extracted and result['stream_header'] else {})
        embedded = awb_entries(result['embedded'], len(result['embedded'])) if result['embedded'] else {}
        result['available'] = {cue for cue, ref in result['bindings'].items()
                               if ref['id'] in (streamed if ref['streamed'] else embedded)}
        inventory['read_voice_banks'] += 1
        inventory['read_voice_cues'] += len(result['bindings'])
        inventory['unsupported_voice_cues'] += len(result['unresolved'])
        return result

    @lru_cache(maxsize=2048)
    def silence(name, cue):
        value = bank(name)
        archive = voices
        # Localized banks replace BASE members. The common archive is a valid
        # fallback only when that bank is absent, and only for proven silence.
        if value is None and base and name in base.entries:
            value, archive = read_acb(base.read(name, 64 * 1024 * 1024)), base
            inventory['read_shared_silence_banks'] += 1
        ref = value['bindings'].get(cue) if value else None
        return bool(ref and silent_adx(_wave_data(archive, name, value, ref)))

    records = []
    for (path, ordinal), row in tables[source_locale].items():
        for page_index, page in enumerate(row['pages']):
            text = display_text(page['text'].replace('\n', ' '))
            if not text:
                continue
            texts, speakers = {}, {}
            for locale, table in tables.items():
                translated = table.get((path, ordinal))
                if translated and translated['id'] == row['id'] and translated['kind'] == row['kind'] and len(translated['pages']) == len(row['pages']):
                    value = translated['pages'][page_index]
                    # Locale page boundaries are accepted only when the authored
                    # voice call agrees. Never align translations by row order alone.
                    if value['voices'] == page['voices']:
                        texts[locale] = display_text(value['text'].replace('\n', ' '))
                        speakers[locale] = translated['speaker']
            texts[source_locale] = text
            audio, state, reason = None, 'unknown', None
            commands = page['voices']
            if row['kind'] == 1 and not commands:
                state = 'unvoiced'
            elif len(commands) == 1:
                command = commands[0]
                name = _bank_path(path, command)
                selected_bank = bank(name) if name else None
                ref = selected_bank['bindings'].get(command[3]) if selected_bank else None
                state = 'unavailable'
                reason = ('missing_voice_pack' if voices is None else 'unresolved_bank_selector' if name is None
                          else 'missing_context_bank' if selected_bank is None else 'unsupported_cue_graph'
                          if command[3] in selected_bank['unresolved'] else 'missing_authored_cue' if ref is None
                          else 'unverified_zero_cue' if command[3] == 0 else 'missing_wavebank')
                if name and command[3] == 0 and silence(name, 0):
                    state, reason = 'unvoiced', None
                elif ref:
                    if command[3] != 0:
                        if command[3] in selected_bank['available']:
                            audio = {'locale': source_locale, 'bank': name, 'cue': command[3], **ref}
                            state, reason = 'voiced', None
            elif commands:
                state = 'unavailable'
                reason = 'multiple_voice_commands'
                inventory['multiple_voice_command_pages'] += 1
            if page['dynamic']:
                inventory['runtime_substitution_pages'] += 1
                # A partially reconstructed line is not an exact OCR target.
                audio, state, reason = None, 'unknown', None
            if reason:
                inventory['unavailable_' + reason] += 1
            identity = hashlib.sha256(f'{path}\0{ordinal}\0{row["id"]}\0{page_index}'.encode()).hexdigest()[:32]
            records.append({'text_id': f'{GAME}:page:{identity}', 'english': texts.get('en', ''),
                'chinese': texts.get('zh-Hans', texts.get('zh-Hant', '')), 'source_locale': source_locale,
                'source_text': text, 'texts': texts, 'audio_locale': source_locale, 'audio': audio,
                'voice_status': state, 'speaker_english': speakers.get('en'),
                'speaker_chinese': speakers.get('zh-Hans', speakers.get('zh-Hant')),
                'dialogue_kind': _category(path, row['kind'] == 1)})
    if fingerprint(install) != stamp:
        raise PreparationFailure('persona5_files_changed', 'Persona game files changed during preparation. Finish Steam downloads and retry.',
                                 game_files_changed=True, previous_snapshot_retained=True)
    inventory['voice_banks_installed'] = sum(name.endswith('.acb') for name in voices.entries) if voices else 0
    counts = Counter(row['voice_status'] for row in records)
    warnings = [
        'Exact event cue bindings cover story/social event pages and battle event pages. Shared reaction voices, ambient bank selectors, runtime-dependent flow-script bindings and non-subtitled battle barks remain unavailable or unknown.',
        'Choices without a voice command and verified zero-residual cue-zero silence are confirmed unvoiced. Missing cues, missing packs and an absent voice command in ordinary dialogue are never classified as silence.',
        'Animated USM movies, some FTD/TBL/binary text tables, and runtime name/variable substitutions are not yet resolved. Moving dialogue, phone messages, thought bubbles and choices require full-frame capture or independent calibrated regions.',
        'Each authored message page uses its complete original cue. Scene timeline times are not inferred as audio cut points.',
        'English installed-text indexing and English/Japanese original voice-bank decoding have native evidence. Japanese text and the other absent text packs use evidenced locale paths and character mappings; their native text indexing has not been verified.']
    if voices is None:
        warnings.append('The selected original voice pack is missing. Verify Persona 5 Royal files in Steam and finish its download, then Prepare again.')
    return {'format': 2, 'game': GAME, 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': records, 'narrative_inventory': dict(inventory),
        'coverage_warnings': warnings,
        'missing_translation_locales': [target for target, locale in targets.items() if locale not in tables],
        'message': f'{len(records):,} official {source_locale} pages; {counts["voiced"]:,} original voice bindings; {counts["unvoiced"]:,} confirmed text-only pages'}


def index_install(install, data_dir, progress=lambda _message: None):
    return index_language(install, data_dir, 'en', [], progress)


def extract_voice(install, audio, _executable, _destination):
    locale, name, cue = audio.get('locale'), audio.get('bank'), audio.get('cue')
    if locale not in VOICE_PACKS or type(cue) is not int or not isinstance(name, str):
        raise invalid('Invalid Persona original voice reference.')
    safe_name(name)
    if not re.fullmatch(r'sound/(?:event/e\d{3}_\d{3}|event_battle/e[0-9a-f]{3,4})\.acb', name):
        raise invalid('Invalid Persona event bank path.')
    archive = Cpk(Path(install) / 'CPK' / (VOICE_PACKS[locale] + '.CPK'))
    selected = read_acb(archive.read(name, 64 * 1024 * 1024))
    ref = selected['bindings'].get(cue)
    if ref is None or any(audio.get(key) != value for key, value in ref.items()):
        raise invalid('Persona original voice binding changed; prepare again.')
    data = _wave_data(archive, name, selected, ref)
    if not data or data[:2] != b'\x80\0' or len(data) < 24:
        raise invalid('Missing or unsupported Persona ADX recording.')
    return data


def decode_voice_source(data, audio, output, decoder, scratch):
    if len(data) < 24 or data[:2] != b'\x80\0':
        raise invalid('Invalid Persona original ADX source.')
    scratch, output = Path(scratch), Path(output)
    scratch.mkdir(parents=True, exist_ok=True)
    source = scratch / 'persona-voice.adx'
    source.write_bytes(data)
    try:
        process = subprocess.run([str(decoder), '-i', '-o', str(output), str(source)], capture_output=True, timeout=45,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        diagnostics = (getattr(process, 'stdout', b'') + getattr(process, 'stderr', b'')).lower()
        if process.returncode or b'decryption keycode not found' in diagnostics or not output.is_file() or output.stat().st_size > 128 * 1024 * 1024:
            raise invalid('Persona original voice decoding failed.')
        result = output.read_bytes()
        with wave.open(io.BytesIO(result)) as decoded:
            if decoded.getnchannels() != audio.get('channels') or decoded.getframerate() != audio.get('rate') or decoded.getnframes() != audio.get('samples'):
                raise invalid('Persona decoded audio disagrees with its authored waveform.')
    finally:
        source.unlink(missing_ok=True)
