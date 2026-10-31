"""Host export preferences and jobs partitioned by account and learning locale."""
from __future__ import annotations

from .runtime_paths import data_root as runtime_data_root
import hashlib
import json
from pathlib import Path
import threading

from .game_paths import GAMES
from .languages import GAME_LOCALES
from .mobile_export_controls import MobileExportManager, ACTIVE


def account_signature(accounts):
    path = accounts.path
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'absent'


class ScopedMobileExports:
    def __init__(self, root, accounts, languages):
        self.root, self.accounts, self.languages = Path(root), accounts, languages
        self.lock = threading.RLock()
        self.managers, self.last_games = {}, {}
        self._paused = False

    def context(self, game=None):
        status = self.accounts.status()
        account = status['active']
        game = game or self.last_games.get(account, 'zzz')
        if game not in GAMES:
            raise ValueError('Unsupported export game')
        locale = self.languages.selected(game, account)
        if locale and locale not in GAME_LOCALES.get(game, ('zh-Hans',)):
            raise ValueError('Select a supported prepared learning language.')
        if not locale:
            legacy = account == 'legacy' and not (runtime_data_root(self.root) / 'languages' / game).is_dir()
            locale = 'zh-Hans' if game == 'hito' or legacy else 'unconfigured'
        signature = account_signature(self.accounts)
        generation = self.languages.selection_generation(game, account)
        token = hashlib.sha256(json.dumps([account, status['generation'], game, locale, signature, generation]).encode()).hexdigest()
        return account, locale, game, signature, token

    def _manager(self, game=None):
        with self.accounts.lock, self.lock:
            if self._paused:
                raise RuntimeError('Mobile exports are paused for the runtime update.')
            account, locale, game, signature, token = self.context(game)
            self.last_games[account] = game
            for old in self.managers.values():
                if not old.guard():
                    old.cancel()
                    old.close_picker()
            key = (account, locale)
            manager = self.managers.get(key)
            if manager is None:
                manager = self.managers[key] = MobileExportManager(self.root, scope=key)
            if not (manager._thread and manager._thread.is_alive()) and not manager._picker:
                selected = self.languages.selected(game, account)
                generation = self.languages.selection_generation(game, account)
                # Worker/picker guards must not acquire the account lock while
                # holding a manager lock. The atomic protected-file signature
                # detects account changes, including switching away and back.
                manager.guard = lambda: (account_signature(self.accounts) == signature
                    and self.languages.selected(game, account) == selected
                    and self.languages.selection_generation(game, account) == generation)
                manager.account_signature, manager.source_locale = signature, locale
            return manager, token, locale

    def require_scope(self, game, expected):
        context = self.context(game)
        if context[4] != expected:
            raise ValueError('Account or learning language changed. Reload Setup before retrying.')
        if context[1] == 'unconfigured':
            raise ValueError('Select and prepare a learning language in Languages before exporting.')
        self._require_table(context[0], context[2], context[1])

    def _require_table(self, account, game, locale):
        if self.languages.selected(game, account) and not (runtime_data_root(self.root) / 'languages' / game / locale / 'textmap.json').is_file():
            raise ValueError('The selected language table is unavailable. Rebuild it in Languages before exporting.')

    def status(self, game=None):
        manager, token, locale = self._manager(game)
        return {**manager.status(), 'scope': token, 'sourceLocale': locale, 'selectedGame': game or self.context()[2]}

    def preview(self, game, include_audio=True, destination_folder=None):
        manager, _, locale = self._manager(game)
        if locale == 'unconfigured':
            raise ValueError('Select and prepare a learning language before exporting.')
        self._require_table(manager.scope[0], game, locale)
        return manager.preview(game, include_audio, destination_folder)

    def start(self, game, include_audio=True, destination_folder=None):
        with self.accounts.lock, self.lock:
            manager, _, locale = self._manager(game)
            if locale == 'unconfigured':
                raise ValueError('Select and prepare a learning language before exporting.')
            self._require_table(manager.scope[0], game, locale)
            if any((other._thread and other._thread.is_alive()) or other._picker or other._status['state'] in ACTIVE
                   for other in self.managers.values()):
                return False
            return manager.start(game, include_audio, destination_folder)

    def browse(self, folder=None, *, game=None):
        manager, _, _ = self._manager(game)
        return manager.browse(folder)

    def close_picker(self, game=None):
        return self._manager(game)[0].close_picker()

    def cancel(self, game=None):
        return self._manager(game)[0].cancel()

    def cancel_all(self):
        with self.accounts.lock, self.lock:
            for manager in self.managers.values():
                manager.cancel()
                manager.close_picker()

    def drain(self):
        with self.lock:
            self._paused = True
            managers = list(self.managers.values())
        # Join outside account/manager locks: completion callbacks need them.
        for manager in managers:
            manager.drain()

    def resume(self):
        with self.lock:
            for manager in self.managers.values():
                if manager._thread and manager._thread.is_alive():
                    raise RuntimeError('A mobile export is still stopping.')
            self._paused = False
