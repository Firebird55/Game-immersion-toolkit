"""Owned Portal VPK/VCCD/event -> exact binding -> original PCM experiment.

Index/language run in the real children. Existing reader extraction and PCM
validation run in the probe process. No general codec or game gate is enabled.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import io
import json
from pathlib import PurePosixPath
import struct
import wave
import zlib

from .runtime_bundle import RuntimeBundleError

TEXTS = {'en': 'An authored source message.', 'fr': 'Un message de test original.'}


def require(condition, message):
    if not condition:
        raise RuntimeBundleError('Authored Source PCM: ' + message)


def pcm(sample):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as writer:
        writer.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        writer.writeframes(struct.pack('<h', sample) * 160)
    return stream.getvalue()


def write_vpk(path, files, *, corrupt_crc=False):
    """One bounded actual VPK v1 tree with inline original members."""
    grouped = defaultdict(lambda: defaultdict(list))
    for name, data in files.items():
        member = PurePosixPath(name)
        grouped[member.suffix[1:]][str(member.parent)].append((member.stem, data))
    tree, payload = bytearray(), bytearray()
    for extension, directories in sorted(grouped.items()):
        tree += extension.encode() + b'\0'
        for directory, entries in sorted(directories.items()):
            tree += directory.encode() + b'\0'
            for name, data in sorted(entries):
                tree += name.encode() + b'\0' + struct.pack('<IHHIIH', zlib.crc32(data), 0,
                    0x7fff, len(payload), len(data), 0xffff)
                payload += data[:-1] + bytes([data[-1] ^ 1]) if corrupt_crc else data
            tree += b'\0'
        tree += b'\0'
    tree += b'\0'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<III', 0x55aa1234, 1, len(tree)) + tree + payload)


def authored_install(root, *, missing_french=False, corrupt_english=False):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'hl2.exe').write_bytes(b'owned non-executable install marker')
    (root / 'portal').mkdir(exist_ok=True)
    (root / 'portal/gameinfo.txt').write_bytes(b'"GameInfo" { "game" "Owned fixture" }')
    files = {'scripts/game_sounds_manifest.txt': b'"game_sounds_manifest" { "precache_file" "scripts/owned.txt" }',
        'scripts/owned.txt': b'"Owned.Line" { "channel" "CHAN_VOICE" "wave" "vo/aperture_ai/owned.wav" }'}
    for locale, native in (('en', 'english'), ('fr', 'french')):
        table = '"lang" { "Language" "' + native + '" "Tokens" { "owned.line" "' + TEXTS[locale] + ' Sidecar placeholder." } }'
        files['resource/closecaption_' + native + '.txt'] = b'\xff\xfe' + table.encode('utf-16-le')
        text = (TEXTS[locale] + '\0').encode('utf-16-le')
        directory = struct.pack('<IIHH', zlib.crc32(b'owned.line'), 0, 0, len(text))
        files['resource/closecaption_' + native + '.dat'] = (
            struct.pack('<4sIIIII', b'VCCD', 1, 1, 4096, 1, 36) + directory + text.ljust(4096, b'\0'))
    write_vpk(root / 'portal/portal_pak_dir.vpk', files)
    for locale, native, sample in (('en', 'english', 11), ('fr', 'french', 22)):
        if locale == 'fr' and missing_french:
            continue
        write_vpk(root / ('portal/portal_sound_vo_' + native + '_dir.vpk'),
            {'sound/vo/aperture_ai/owned.wav': pcm(sample)}, corrupt_crc=corrupt_english and locale == 'en')
    return root


def inventory(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*') if p.is_file()}


def probe(layout, run_worker):
    from .game_assets import asset_adapter
    from .preparation_errors import PreparationFailure
    from .source_dialogue import pack_performance
    adapter, _ = asset_adapter('portal')
    root = layout.work_root / 'authored-source-pcm'
    root.mkdir(parents=True, exist_ok=True)
    installs = {'complete': authored_install(root / 'complete'),
        'missing': authored_install(root / 'missing', missing_french=True),
        'corrupt': authored_install(root / 'corrupt', corrupt_english=True)}
    before = {name: inventory(install) for name, install in installs.items()}
    index = root / 'index.json'
    run_worker('game-index', ['--game', 'portal', '--install', str(installs['complete']),
        '--directory', str(root), '--output', str(index)])
    require(len(json.loads(index.read_text(encoding='utf-8'))['records']) == 1, 'index worker lost authored caption')
    cases = []
    bindings = {}
    for locale, target, sample in (('en', 'fr', 11), ('fr', 'en', 22)):
        language = root / (locale + '.json')
        run_worker('language', ['--game', 'portal', '--install', str(installs['complete']),
            '--directory', str(root), '--output', str(language), '--locale', locale, '--targets', json.dumps([target])])
        payload = json.loads(language.read_text(encoding='utf-8'))
        require(payload.get('dialogue_inventory', {}).get('voice_counts') == {
            'voiced': 1, 'unvoiced': 0, 'unknown': 0, 'unavailable': 0}, 'language worker changed voice classification')
        require(len(payload['records']) == 1, 'unexpected authored captions')
        row = payload['records'][0]
        require(row['text_id'] == 'portal:caption:owned.line' and row['source_locale'] == locale
            and row['source_text'] == TEXTS[locale] and row['texts'].get(target) == TEXTS[target]
            and row['audio_locale'] == locale and row['audio']['locale'] == locale,
            'selected caption/voice locale changed')
        bindings[locale] = row['audio']
        source = adapter.extract_voice(installs['complete'], row['audio'], None, root)
        output = root / (locale + '.wav')
        adapter.decode_voice_source(source, row['audio'], output, None, root)
        require(output.read_bytes() == pcm(sample), 'original selected-pack PCM bytes changed or fell back')
        with wave.open(str(output), 'rb') as stream:
            require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes())
                == (1, 2, 16000, 160), 'original PCM identity changed')
            frames = stream.readframes(160)
        cases.append({'source_locale': locale, 'translation_locale': target, 'frames': 160,
            'wav_sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'pcm_sha256': hashlib.sha256(frames).hexdigest()})
    missing = root / 'missing-fr.json'
    run_worker('language', ['--game', 'portal', '--install', str(installs['missing']), '--directory', str(root),
        '--output', str(missing), '--locale', 'fr', '--targets', '["en"]'])
    missing_payload = json.loads(missing.read_text(encoding='utf-8'))
    require(missing_payload.get('dialogue_inventory', {}).get('voice_counts') == {
        'voiced': 0, 'unvoiced': 0, 'unknown': 0, 'unavailable': 1}
        and missing_payload['records'][0]['audio'] is None and adapter.probe_voice_pack(installs['missing'], 'fr') == 'missing'
        and any('Install the official Portal fr voice pack' in warning for warning in missing_payload['coverage_warnings']),
        'missing localized pack borrowed another voice or lost actionable state')
    for install, binding in ((installs['missing'], dict(bindings['en'], locale='fr')),
                             (installs['corrupt'], bindings['en'])):
        try:
            adapter.extract_voice(install, binding, None, root)
        except PreparationFailure:
            pass
        else:
            raise RuntimeBundleError('Authored Source PCM: changed pack/binding was accepted')
    # The corrupt-container case keeps the complete capsule, so this exercises
    # PCM validation rather than merely the outer capsule's byte count.
    output = root / 'en.wav'
    previous = output.read_bytes()
    try:
        adapter.decode_voice_source(pack_performance([previous[:-10]]), bindings['en'], output, None, root)
    except PreparationFailure:
        pass
    else:
        raise RuntimeBundleError('Authored Source PCM: truncated PCM was accepted')
    require(output.read_bytes() == previous and not list(root.glob('source-pcm-*')), 'failed PCM publication lost prior output')
    require(before == {name: inventory(install) for name, install in installs.items()}, 'reader changed authored installation')
    return {'schema': 'proxy-r19-source-pcm-probe-v1', 'scope': 'authored-portal-vpk1-vccd1-single-original-pcm-only',
        'game_index_worker': 'passed', 'language_worker': 'passed', 'reader_extraction': 'in-process-existing-adapter-passed',
        'cases': cases, 'missing_selected_voice_pack': 'unavailable-no-fallback', 'changed_binding': 'rejected',
        'vpk_crc_mismatch': 'rejected', 'truncated_pcm': 'rejected-previous-output-preserved',
        'authored_installations': 'unchanged', 'external_codec_used': False,
        'composite_mp3_bink': 'not-run', 'voiced_mobile_export': 'not-run', 'installed_game_probe': 'not-run',
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}
