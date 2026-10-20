"""Local, cached storage inventory. Never download or prepare while inspecting."""
import json
import os
from pathlib import Path
import threading
import time

from .languages import GAME_LOCALES


def directory_bytes(root):
    """Logical bytes, without following directory links or counting hardlinks twice."""
    total, seen = 0, set()
    if not root.exists():
        return 0
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories
                          if not (Path(folder) / name).is_symlink()
                          and not (Path(folder) / name).is_junction()]
        for name in files:
            path = Path(folder) / name
            if path.is_symlink():
                continue
            try:
                stat = path.stat()
                identity = (stat.st_dev, stat.st_ino)
                if identity not in seen:
                    seen.add(identity)
                    total += stat.st_size
            except OSError:
                return None
    return total


class LanguageInventory:
    def __init__(self, data, catalog, install_lookup):
        self.data, self.catalog, self.install_lookup = Path(data), Path(catalog), install_lookup
        self._cache = {}
        self._lock = threading.RLock()

    def invalidate(self):
        with self._lock:
            self._cache.clear()

    def table(self, game, locale):
        if game not in GAME_LOCALES or locale not in GAME_LOCALES[game]:
            raise ValueError('Unknown game language.')
        root = (self.data / 'languages').resolve()
        path = self.data / 'languages' / game / locale / 'textmap.json'
        if not path.resolve().is_relative_to(root) or any(
                p.is_symlink() or p.is_junction() for p in [self.data / 'languages', path.parent.parent, path.parent]):
            raise ValueError('Language storage is outside the managed directory.')
        return path

    def status(self, game, preparation):
        with self._lock:
            key = (game, tuple((row['locale'], json.dumps(row.get('prepared'), sort_keys=True),
                               row.get('job', {}).get('state')) for row in preparation['locales']))
            now = time.monotonic()
            if key in self._cache and now - self._cache[key][0] < 60:
                return self._cache[key][1]
            catalog = json.loads(self.catalog.read_text(encoding='utf-8'))
            entry = next(row for row in catalog['games'] if row['id'] == game)
            install = self.install_lookup(game)
            installed_bytes = None
            fingerprint = None
            if install:
                try:
                    from .game_assets import asset_adapter
                    adapter, _ = asset_adapter(game)
                    fingerprint = adapter.fingerprint(install)
                    if hasattr(adapter, 'archive_sources'):
                        sources = {p.resolve() for p in adapter.archive_sources(install)
                                   if not p.is_symlink() and p.resolve().is_relative_to(install.resolve())}
                        installed_bytes = sum(p.stat().st_size for p in sources) if sources else None
                except (OSError, ValueError, KeyError):
                    pass
            locales = {}
            for row in preparation['locales']:
                path = self.table(game, row['locale'])
                size = path.stat().st_size if path.is_file() else 0
                locales[row['locale']] = {
                    'table_bytes': size, 'reclaimable_bytes': size,
                    'voice_state': 'not_checked' if not install else 'check_during_preparation',
                    'support': 'expected' if row['reader_available'] else 'unsupported',
                }
                # A prepared table proves bindings, not continued pack installation.
                if size and install:
                    try:
                        payload = json.loads(path.read_text(encoding='utf-8'))
                        if fingerprint and payload.get('fingerprint') == fingerprint:
                            locales[row['locale']]['voice_state'] = 'present'
                            locales[row['locale']]['support'] = 'prepared'
                    except (OSError, ValueError, KeyError):
                        pass
            value = {'locales': locales, 'translation_locales': entry['targets'],
                     'expected_targets': entry.get('expectedTargets', []),
                     'official_text_locales': entry['officialText'],
                     'storage': {'tables_bytes': sum(row['table_bytes'] for row in locales.values()),
                                 'audio_cache_bytes': directory_bytes(self.data / 'audio'),
                                 'shared_tools_bytes': directory_bytes(self.data / 'voice-assets'),
                                 'installed_game_bytes': installed_bytes, 'exports_bytes': None,
                                 'measured_at': time.time(),
                                 'note': 'Audio and tools are shared across languages. Game packs and external exports are managed separately.'}}
            self._cache[key] = (now, value)
            return value

    def cleanup(self, game, locale, manager, busy=False):
        """Delete only the generated table; no recursive deletion or arbitrary paths."""
        with self._lock, manager.lock:
            path = self.table(game, locale)
            if busy or manager.jobs.get((game, locale), {}).get('state') == 'preparing':
                raise ValueError('Wait for preparation or export to finish before cleanup.')
            removed = path.stat().st_size if path.is_file() else 0
            # Unlink first so a permission failure does not unregister usable data.
            path.unlink(missing_ok=True)
            manager.remove(game, locale)
            self._cache.clear()
            return {'removed': True, 'reclaimed_bytes': removed}
