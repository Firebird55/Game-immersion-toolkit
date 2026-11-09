"""Recorded phone messages in the Global PC launcher release."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from . import game_tools, hoyo_publisher_voice as voice, sophon_assets as sophon
from .hoyo_dialogue import voice_namespace
from .languages import audio_locale, resolve_locale
from .prebuilt_node_reader import require_zzz_reader
from .runtime_bundle import discover_layout
from .runtime_paths import voice_work_root
from .textmaps import gender_variants
from .voice_assets import voice_hash
from .zzz_assets import MESSAGE_SOURCE, TEXT_LOCALES, _text

CHANNEL = 'zzz-global'
BASE = 'ZenlessZoneZero_Data/StreamingAssets/'
SCOPE = ('Only recorded phone messages in the Global PC launcher release are prepared without a game folder. '
         'Installed files are needed for other presentations and later in-version overrides.')


def fingerprint():
    return voice.descriptor(sophon.release(CHANNEL))[0]


def _design_files(build, cache, work):
    files = sophon.manifest(cache, CHANNEL, tuple(build['manifests']['game']), ('/data_version', '.blk'))
    index = files[BASE + 'data_version']
    rows = json.loads(index.read(cache, 0, index.size))['files']
    if not isinstance(rows, list) or not rows or len(rows) > 4096:
        raise ValueError('Unsupported ZZZ launcher design list.')
    assets = {}
    for row in rows:
        match = re.fullmatch(r'Blocks/Data/(\d+)\.blk', row['remoteName'])
        if not match:
            raise ValueError('Unknown ZZZ launcher design directory structure.')
        asset = files[BASE + row['remoteName']]
        name = 'design-' + match[1] + '.blk'
        if name in assets or row['fileSize'] != asset.size:
            raise ValueError('ZZZ launcher design inventory differs from the selected manifest.')
        assets[name] = asset

    def stage(item):
        name, asset = item
        (work / name).write_bytes(asset.read(cache, 0, asset.size))
        return name

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(stage, assets.items()))


def _read_messages(build, data_dir, locales):
    packaged = require_zzz_reader()
    cache = data_dir / 'tools/sophon'
    parent = packaged.work_root if packaged else cache
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='zzz-messages-', dir=parent) as tmp:
        work = Path(tmp).resolve()
        design = _design_files(build, cache, work)
        (work / 'messages-input.json').write_text(json.dumps({'design': design, 'locales': sorted(locales)}), encoding='utf-8')
        options = {'cwd': work, 'timeout': 600, 'check': True, 'capture_output': True,
                   'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
        if packaged:
            command = packaged.publisher_messages_command(work)
            options['env'] = packaged.environment()
        else:
            layout = discover_layout()
            project = layout.legacy_project_root if os.environ.get('PROXY_TRANSCRIPT_PROJECT_ROOT') else data_dir.parent.parent
            source = voice_work_root(project) / 'galgame-perform.ts'
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != game_tools.READER_SHA:
                raise ValueError('Prepare the ZZZ reader in Setup before preparing a language.')
            script = game_tools.CODE_ROOT / 'scripts/zzz-publisher-dialogue.mjs'
            subprocess.run(['node', str(script), 'compile', str(work), str(source)], **options)
            command = ['node', str(script), 'messages', str(work), str(work / 'galgame-perform.mjs')]
        subprocess.run(command, **options)
        return json.loads((work / 'messages-output.json').read_bytes())


def build_language(data_dir, source_locale, target_locales, progress):
    build = sophon.release(CHANNEL)
    stamp, raw = voice.descriptor(build)
    game_tools._atomic_file(data_dir / 'tools/sophon/releases' / stamp, raw)
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(value for value in targets.values() if value)}
    progress('Reading recorded phone messages and translations from the Global ZZZ launcher release')
    result = _read_messages(build, data_dir, selected)
    dub = audio_locale(source_locale)
    namespace = voice_namespace('zzz', dub)
    messages = result['messages']
    if not messages or any(not MESSAGE_SOURCE.fullmatch(row['source']) for row in messages):
        raise ValueError('The released ZZZ message table contains no supported recording bindings.')
    progress('Matching authored messages to original recordings in the selected publisher voice pack')
    paths = {row['id']: f"{namespace}/ex/{row['source']}.wem" for row in messages}
    entries = voice.inventory(data_dir, stamp, dub, 'zzz', wanted={voice_hash(path) for path in paths.values()})
    rows, missing_voices, missing_subtitles = [], 0, 0
    for item in messages:
        identity, values = item['id'], item['texts']
        source = paths[identity]
        file_id = voice_hash(source)
        entry = entries.get(file_id)
        if not entry:
            missing_voices += 1
            continue
        if not values.get(source_locale, '').strip():
            missing_subtitles += 1
            continue
        gendered = any(gender_variants(value) for value in values.values())
        for gender in ('M', 'F') if gendered else (None,):
            texts = {locale: text for locale, value in values.items() if (text := _text(value, gender))}
            if source_locale not in texts:
                continue
            rows.append({'text_id': identity + ':' + gender if gender else identity,
                'source_locale': source_locale, 'source_text': texts[source_locale], 'texts': texts,
                'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                'audio_locale': dub, 'dialogue_kind': 'message', 'voice_status': 'voiced',
                'player_voice': {'M': 'male', 'F': 'female'}.get(gender),
                'member_text_ids': [identity] if gender else None, 'channels': ['dialogue', 'cinematic'],
                'audio': {**entry, 'locale': dub, 'source': source, 'file_id': f'{file_id:016x}'}})
    if not rows or fingerprint() != stamp:
        raise ValueError('No verified ZZZ phone messages or the launcher release changed. Retry preparation.')
    available = {locale for row in rows for locale in row['texts']}
    return {'format': 2, 'game': 'zzz', 'source_locale': source_locale, 'install': None, 'source_mode': 'publisher',
            'fingerprint': stamp, 'metadata_revision': build['build'], 'records': rows,
            'missing_translation_locales': [target for target, locale in targets.items() if locale not in available],
            'coverage': {'message_sources': len(messages), 'unresolved_sources': result['unresolved'],
                         'missing_recordings': missing_voices, 'missing_study_text': missing_subtitles},
            'coverage_warnings': [SCOPE],
            'message': f"{len(rows):,} recorded Global phone message entries in {source_locale}. {SCOPE}"}
