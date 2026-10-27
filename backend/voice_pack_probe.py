"""Cheap read-only pack checks; unknown layouts never imply missing audio."""
from itertools import islice
import os
import re
import time
import threading
from pathlib import Path
from .game_assets import asset_adapter

LABELS = {'present': 'Installed', 'missing': 'Not detected — install this voice language in the game/launcher',
          'incomplete': 'Incomplete', 'unknown': 'Unable to verify'}

_cache = {}
_lock = threading.Lock()


def bounded_files(root, pattern):
    count = 0
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if not (Path(folder)/name).is_symlink() and not (Path(folder)/name).is_junction()]
        count += len(files) + len(directories)
        if count > 10000:
            raise ValueError('Probe traversal limit reached')
        for name in files:
            if Path(name).match(pattern):
                yield Path(folder)/name


def probe(game, install, locale):
    key = (game, str(install), locale)
    with _lock:
        saved = _cache.get(key)
        if saved and time.monotonic()-saved[0] < 30:
            return saved[1]
    value = _probe(game, install, locale)
    with _lock:
        if len(_cache) > 256:
            _cache.clear()
        _cache[key] = (time.monotonic(), value)
    return value


def _probe(game, install, locale):
    if not install:
        return 'missing'
    install = Path(install)
    try:
        adapter, _ = asset_adapter(game)
        game_probe = getattr(adapter, 'probe_voice_pack', None)
        if game_probe:
            result = game_probe(install, locale)
            return result if isinstance(result, str) and result in LABELS else 'unknown'
        if game == 'zzz':
            root = adapter.game_data(install)
            paths = (p for layer in ('StreamingAssets', 'Persistent') for p in
                     (root / layer / 'Audio/Windows/Full' / adapter.VOICE_FOLDERS[locale]).glob('*.pck'))
        elif game in ('genshin', 'starrail'):
            from . import hoyo_dialogue as common
            root = common.game_data(install, game)
            namespace = common.voice_namespace(game, locale).casefold()
            paths = (p for layer in ('StreamingAssets', 'Persistent') for folder in
                     ('AudioAssets', 'Audio/AudioPackage/Windows', 'Audio/GeneratedSoundBanks/Windows')
                     for p in bounded_files(root / layer / folder, '*.pck') if namespace in {part.casefold() for part in p.parts})
        elif game == 'cyberpunk':
            paths = (p for p in adapter.archive_sources(install) if p.name.removeprefix('ep1_') == 'lang_' + adapter.TEXT_LOCALES[locale] + '_voice.archive')
        elif game == 'witcher3':
            paths = (p for root in ('content', 'dlc') for p in bounded_files(install / root, '*pc.w3speech') if p.name.casefold() == adapter.TEXT_LOCALES[locale] + 'pc.w3speech')
        elif game == 'beyond':
            from .quantic_assets import read_index
            code = adapter.TEXT_LOCALES[locale]
            indexes = list(islice((p for p in install.glob('BigFile_PC*.idx') if p.stem.endswith('_'+code)
                           or code == 'ENG' and not re.search(r'_[A-Z]{3}$', p.stem)), 17))
            if not indexes:
                return 'missing'
            if len(indexes) > 16 or any(p.stat().st_size > 8*1024**2 for p in indexes):
                return 'unknown'
            voices = [entry for path in indexes for entry in read_index(path) if entry.kind == 4091]
            if not voices:
                return 'missing'
            return 'present' if all(entry.path.is_file() and entry.offset+entry.size <= entry.path.stat().st_size for entry in voices) else 'incomplete'
        elif game == 'heavyrain':
            from .quantic_assets import read_index
            from .quantic_legacy import Metadata, references
            indexes = [install/name for name in adapter.SCENE_INDEXES+adapter.VOICE_INDEXES if (install/name).is_file()]
            if not any((install/name).is_file() for name in adapter.VOICE_INDEXES):
                return 'missing'
            if any(p.stat().st_size > 8*1024**2 for p in indexes):
                return 'unknown'
            entries = [entry for path in indexes for entry in read_index(path)]
            voices = {entry.identity: entry for entry in entries if entry.kind == 4091}
            language = adapter.LANGUAGE_IDS[adapter.TEXT_LOCALES[locale]]
            for entry in islice((entry for entry in entries if entry.kind == 29), 16):
                refs, _ = references(Metadata(entry))
                for kind, identity, lang in refs:
                    if kind == 4091 and lang == language and identity in voices:
                        voice = voices[identity]
                        return 'present' if voice.path.is_file() and voice.offset+voice.size <= voice.path.stat().st_size else 'incomplete'
            return 'unknown'
        else:
            # Shared/encrypted banks cannot establish a locale from filenames.
            # An independently verified snapshot can supplement this result.
            return 'unknown'
        found = list(islice(paths, 257))
        if len(found) > 256:
            return 'unknown'
        if not found:
            return 'missing'
        if any(p.stat().st_size < 32 for p in found):
            return 'incomplete'
        if game == 'cyberpunk' and adapter.expansion_status(install, locale)['expansion_state'] in ('missing_text', 'missing_voice'):
            return 'incomplete'
        if game in ('zzz', 'genshin', 'starrail'):
            from .voice_assets import read_external_table
            try:
                if not any(read_external_table(path) for path in found[:4]):
                    return 'unknown'
            except ValueError:
                return 'incomplete'
        return 'present'
    except (OSError, ValueError, KeyError):
        return 'unknown'
