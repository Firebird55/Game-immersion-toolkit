"""Selected official MSG locales with authored SoundID/timeline voice bindings."""
from __future__ import annotations

import re
import struct
import tempfile
from pathlib import Path

from scripts import index_pragmata_assets as reader
from .pragmata_audio import build_sound_id_audio_map, cutscene_audio_for_bank, read_tmlfsm_dialogue_segments
from .languages import resolve_locale

LANGUAGE_INDEX_VERSION = 2
SUPPORTED_LOCALES = ('en', 'fr', 'it', 'de', 'es-ES', 'es-419', 'pt-BR', 'ru', 'zh-Hans', 'ja', 'ko')
VOICE_LOCALES = dict(zip(SUPPORTED_LOCALES, ('en', 'fr', 'it', 'de', 'es', 'es419', 'ptbr', 'ru', 'zhcn', 'ja', 'ko')))
# via.Language identifiers are stable format constants, not inferred positions.
TEXT_LOCALES = {'ja': 0, 'en': 1, 'fr': 2, 'it': 3, 'de': 4, 'es-ES': 5, 'ru': 6,
    'pl': 7, 'pt-BR': 10, 'ko': 11, 'zh-Hant': 12, 'zh-Hans': 13,
    'ar': 21, 'es-419': 32}
fingerprint = reader.fingerprint


def build_records(extracted, source_locale, selected, graph):
    root = extracted / 'natives/stm/message'
    parsed, references = [], {}
    for path in sorted(root.rglob('*.msg.*')):
        entries = reader.read_msg(path, {locale: TEXT_LOCALES[locale] for locale in selected})
        parsed.append((path.relative_to(root).as_posix().casefold(), entries))
        for entry in entries:
            for locale, text in entry['texts'].items():
                if text and not reader.REF_RE.search(text):
                    references.setdefault(locale, {}).setdefault(entry['name'], set()).add(text)
    def clean(text, locale):
        def replace(match):
            candidates = references.get(locale, {}).get(match[1], set())
            return next(iter(candidates)) if len(candidates) == 1 else match[0]
        text = reader.REF_RE.sub(replace, text)
        # An unresolved or conflicting reference cannot become a partial official
        # sentence by silently dropping the missing fragment.
        if reader.REF_RE.search(text):
            return ''
        return reader.TAG_RE.sub('', text).replace('\r\n', '\n').strip()
    code = VOICE_LOCALES[source_locale]
    bank_root = extracted / 'natives/stm/sound/wwise'
    direct = build_sound_id_audio_map(graph, bank_root, code)
    timeline = {}
    for path in sorted(extracted.rglob('*.tmlfsm2.*')):
        match = re.search(r'/(cs\d+)/flow/', path.as_posix(), re.I)
        if not match:
            continue
        base = cutscene_audio_for_bank(graph, match[1].lower() + '_dialogue', bank_root, code)
        if not base:
            continue
        try:
            segments = read_tmlfsm_dialogue_segments(path)
        except (ValueError, OSError, struct.error):
            continue
        for segment in segments:
            guid = str(segment['guid']).lower()
            audio = {**base, 'start_seconds': segment['start_seconds'], 'end_seconds': segment['end_seconds']}
            timeline[guid] = audio if guid not in timeline or timeline[guid] == audio else None
    rows = {}
    for relative, entries in parsed:
        if not relative.startswith(('mes_main/conv/', 'mes_main/event/cutscene/')):
            continue
        for entry in entries:
            name = entry['name']
            texts = {locale: value for locale, text in entry['texts'].items() if (value := clean(text, locale))}
            text = texts.get(source_locale, '')
            if (not text or name.startswith('OP_StaffList_') or name.casefold().startswith('soundsupport_')
                    or '#rejected#' in text.casefold() or re.fullmatch(r'\[[^\]]+\]', text)):
                continue
            audio = direct.get(int(entry.get('sound_id') or 0)) or timeline.get(str(entry['guid']).lower())
            # The selected localized bank must exist in the extracted install.
            # A public graph alone cannot prove an installed voice pack.
            if audio and not (bank_root / (str(audio['bank']) + '.sbnk.1.x64.' + code)).is_file():
                audio = None
            if audio:
                if any(value and not str(value).endswith('.' + code) for value in [audio.get('index'), audio.get('streaming')]):
                    raise ValueError('PRAGMATA voice package disagrees with its selected locale')
                audio = {**audio, 'locale': source_locale}
            identity = 'pragmata:' + relative + ':' + name
            rows[identity] = {'text_id': identity, 'source_locale': source_locale, 'source_text': text,
                'texts': texts, 'english': texts.get('en', ''), 'chinese': texts.get('zh-Hans', ''),
                'audio_locale': source_locale, 'audio': audio}
    return list(rows.values())


def index_language(install: Path, data_dir: Path, source_locale: str, target_locales, progress=lambda _message: None):
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported PRAGMATA study/audio locale')
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(locale for locale in targets.values() if locale)}
    stamp = fingerprint(install)
    data_dir.mkdir(parents=True, exist_ok=True)
    progress(f'Reading selected PRAGMATA {source_locale} voice banks and official text')
    with tempfile.TemporaryDirectory(prefix='language-', dir=data_dir) as value:
        extracted = Path(value)
        reader.extract_assets(install, extracted, data_dir / 'tools', VOICE_LOCALES[source_locale])
        rows = build_records(extracted, source_locale, selected, reader.load_sound_graph(data_dir))
    if not rows or fingerprint(install) != stamp:
        raise ValueError('PRAGMATA files changed or dialogue is incomplete; previous table retained.')
    mapped = sum(bool(row['audio']) for row in rows)
    available = {locale for row in rows for locale in row['texts']}
    missing = [target for target, locale in targets.items() if locale not in available]
    return {'format': 2, 'game': 'pragmata', 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': rows, 'missing_translation_locales': missing,
        'message': f'{len(rows):,} official {source_locale} lines; {mapped:,} original voices' +
        (f'; {len(rows) - mapped:,} entries without a verified voice binding' if mapped < len(rows) else '') +
        (f'; official translations unavailable: {", ".join(missing)}' if missing else '') +
        ('; check the selected voice pack and authored mappings' if not mapped else '')}
