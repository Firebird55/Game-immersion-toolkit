"""Authored GoldSrc -> real worker -> portable text export experiment.

This proves a bounded unvoiced route, never installed-game or Windows acceptance.
The worker callback must execute the actual child and enforce its expected exit.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
import zipfile

from .runtime_bundle import RuntimeBundleError

TEXTS = {'en': 'Authored screen message', 'zh-Hans': '\u81ea\u5236\u5c4f\u5e55\u6d88\u606f'}


def require(condition, message):
    if not condition:
        raise RuntimeBundleError('Authored unvoiced export: ' + message)


def authored_install(root):
    """Only owned strings, non-executable markers and a bounded BSP entity lump."""
    entities = '\n'.join('{\n' + '\n'.join(json.dumps(key) + ' ' + json.dumps(value)
        for key, value in entity.items()) + '\n}' for entity in (
            {'classname': 'env_message', 'message': 'CARD'},
            {'classname': 'env_message', 'message': 'SOUND', 'messagesound': 'scientist/missing.wav'},
        )) + '\0'
    data = entities.encode('ascii')
    files = {'hl.exe': b'owned fixture marker, not an executable',
        'valve/liblist.gam': b'game "Owned runtime fixture"',
        'valve/maps/owned.bsp': struct.pack('<III', 30, 124, len(data)) + bytes(112) + data}
    for locale, mount in (('en', 'valve'), ('zh-Hans', 'valve_schinese')):
        table = 'CARD\n{\n' + TEXTS[locale] + '\n}\nSOUND\n{\nAuthored attached sound\n}\nUNUSED\n{\nAuthored unused title\n}\n'
        files[mount + '/titles.txt'] = table.encode('utf-8') if locale == 'en' else b'\xff\xfe' + table.encode('utf-16-le')
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    return root


def inventory(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob('*') if path.is_file()}


def read_export(output, source, target):
    from .mobile_export_layout import latest_export
    _, bundle = latest_export(output, 'halflife')
    with zipfile.ZipFile(bundle) as outer:
        metadata = json.loads(outer.read('manifest.json'))
        require(set(outer.namelist()) == {'manifest.json', 'library/catalog.zip'}, 'unexpected transfer members')
        require(metadata.get('game') == 'halflife' and metadata.get('voices') == []
            and metadata.get('audioLocales') == [], 'unexpected original voices')
        with zipfile.ZipFile(io.BytesIO(outer.read('library/catalog.zip'))) as catalog:
            manifest = json.loads(catalog.read('manifest.json'))
            require(manifest.get('format') == 'proxy-mobile-library-v1' and manifest.get('game') == 'halflife'
                and manifest.get('packs') == [] and manifest.get('coverage') == {
                    'dialogue': 1, 'mappedVoices': 0, 'exportedVoices': 0, 'partial': True}, 'catalog coverage changed')
            for value in (metadata, manifest):
                require(value.get('sourceLocale') == source and value.get('audioLocale') == source
                    and value.get('translationLocale') == target, 'selected locale identity changed')
            rows = []
            require(set(catalog.namelist()) == {'manifest.json', *(part['name'] for part in manifest['catalog'])},
                'unexpected catalog members')
            for part in manifest['catalog']:
                data = catalog.read(part['name'])
                require(len(data) == part['size'] and hashlib.sha256(data).hexdigest() == part['sha256'],
                    'catalog bytes do not match their identity')
                rows.extend(json.loads(line) for line in data.splitlines())
    require(len(rows) == 1, 'unknown or attached-sound entries were exported')
    row = rows[0]
    require(row.get('textId') == 'halflife:title:card' and row.get('sourceLocale') == source
        and row.get('sourceText') == TEXTS[source] and row.get('translationLocale') == target
        and row.get('translationText') == TEXTS[target] and row.get('audioLocale') == source
        and row.get('audio') is None and row.get('sourceVoice') is None, 'authored row identity changed')
    require(not any(key in row for key in ('install', 'archive', 'package', 'path')), 'private source reference escaped')
    return bundle


def probe(layout, run_worker):
    root = layout.work_root / 'authored-unvoiced-export'
    root.mkdir(parents=True, exist_ok=True)
    fixture = authored_install(root / 'install')
    before = inventory(fixture)
    index = root / 'index.json'
    run_worker('game-index', ['--game', 'halflife', '--install', str(fixture),
        '--directory', str(root), '--output', str(index)])
    require(bool(json.loads(index.read_text(encoding='utf-8'))['records']), 'game-index worker returned no records')
    cases = []
    for source, target in (('en', 'zh-Hans'), ('zh-Hans', 'en')):
        directory = root / source
        directory.mkdir(exist_ok=True)
        language = directory / 'language.json'
        run_worker('language', ['--game', 'halflife', '--install', str(fixture),
            '--directory', str(directory), '--output', str(language), '--locale', source,
            '--targets', json.dumps([target])])
        payload = json.loads(language.read_text(encoding='utf-8'))
        require(payload.get('dialogue_inventory', {}).get('voice_counts') == {
            'voiced': 0, 'unvoiced': 1, 'unavailable': 0, 'unknown': 2}, 'authored binding classifications changed')
        require(payload.get('source_locale') == source and any(row['text_id'] == 'halflife:title:card'
            and row['source_text'] == TEXTS[source] and row['texts'].get(target) == TEXTS[target]
            for row in payload['records']), 'language worker lost selected authored text')
        output = layout.default_export_root / 'authored-unvoiced' / source
        arguments = ['--root', str(root / 'companion'), '--game', 'halflife', '--output', str(output),
            '--source-locale', source, '--translation-locale', target, '--automatic-install', str(fixture)]
        # Ordinary export mode, including its language preparation, atomic
        # publication and final portable bundle. No catalog-only escape hatch.
        run_worker('mobile-export', arguments)
        bundle = read_export(output, source, target)
        saved = ((output / 'latest.json').read_bytes(), bundle.read_bytes(), bundle.stat().st_mtime_ns)
        run_worker('mobile-export', arguments)
        require(saved == ((output / 'latest.json').read_bytes(), bundle.read_bytes(), bundle.stat().st_mtime_ns),
            'unchanged worker export did not reuse the completed bundle')
        if source == 'en':
            missing = root / 'missing-de'
            missing.mkdir(exist_ok=True)
            run_worker('language', ['--game', 'halflife', '--install', str(fixture), '--directory', str(missing),
                '--output', str(missing / 'language.json'), '--locale', 'de', '--targets', '["en"]'], expected_status=1)
            failure = json.loads((missing / 'failure.json').read_text(encoding='utf-8'))
            require(failure.get('code') == 'halflife_language_pack_missing' and not (missing / 'language.json').exists(),
                'absent selected pack silently substituted another language')
            rejected = list(arguments)
            rejected[rejected.index('--source-locale') + 1] = 'de'
            run_worker('mobile-export', rejected, expected_status=1)
            require(saved == ((output / 'latest.json').read_bytes(), bundle.read_bytes(), bundle.stat().st_mtime_ns),
                'missing-pack failure replaced the completed export')
        cases.append({'source_locale': source, 'translation_locale': target, 'rows': 1, 'voice_packs': 0,
            'bundle_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest()})
    require(before == inventory(fixture), 'workers changed the authored installation')
    return {'schema': 'proxy-r19-unvoiced-export-probe-v1', 'fixture': 'owned-goldsrc-bsp-v30-and-localized-titles',
        'game_index_worker': 'passed', 'language_worker': 'passed', 'mobile_export_worker': 'passed',
        'cases': cases, 'unchanged_export_reuse': 'passed', 'missing_selected_pack': 'rejected',
        'failed_export_previous_bundle': 'preserved', 'authored_installation': 'unchanged',
        'audio_decoder_used': False, 'scope': 'authored-unvoiced-screen-messages-only',
        'installed_game_voice_export': 'not-run', 'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}
