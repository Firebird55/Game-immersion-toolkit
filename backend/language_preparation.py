"""Explicit language preparation; automatic refresh only visits prepared entries."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from datetime import datetime, timezone

from .languages import GAME_LOCALES, LOCALE_NAMES, study_language
from .preparation_worker import PreparationCancelled, PreparationJob


def selected_snapshot(root: Path, game: str):
    """Read an explicit host selection without preparing data or preferences."""
    data = Path(root) / 'data'
    if not (data / 'languages' / game).is_dir():
        return data / game / 'textmap.json', None, 'legacy'
    from .accounts import AccountStore
    accounts = AccountStore()
    account = accounts.status()['active']
    selected = LanguagePreparation(None, None, None).selected(game, account)
    if not selected:
        raise ValueError('Select a prepared learning language before exporting.')
    return data / 'languages' / game / selected / 'textmap.json', accounts, account


class LanguagePreparation:
    def __init__(self, build, activate, state, *, path: Path | None = None, supported=None, rebuild=None, cancellable=False):
        self.path = path or Path(os.environ.get('LOCALAPPDATA', '.')) / 'Proxy Transcript/languages.json'
        self.build, self.activate, self.state = build, activate, state
        self.rebuild = rebuild or build
        self.cancellable = cancellable
        self.supported = supported or (lambda _game: ('zh-Hans',))
        self.lock = threading.RLock()
        self._lifecycle_lock = threading.Lock()
        self.jobs = {}
        self._workers = set()
        self._monitors = set()
        self.stop_event = threading.Event()
        self.monitor = None
        try:
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.data.get('prepared'), dict) or not isinstance(self.data.get('selected'), dict):
                raise ValueError()
        except (OSError, ValueError, TypeError):
            self.data = {'prepared': {}, 'selected': {}}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix('.pending')
        pending.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        pending.replace(self.path)

    def selected(self, game: str, account: str = 'legacy') -> str | None:
        with self.lock:
            return self.data['selected'].get(account, {}).get(game)

    def selection_generation(self, game: str, account: str = 'legacy') -> int:
        with self.lock:
            return self.data.get('selection_generations', {}).get(account, {}).get(game, 0)

    def _select(self, game, locale, account):
        if self.data['selected'].get(account, {}).get(game) != locale:
            versions = self.data.setdefault('selection_generations', {}).setdefault(account, {})
            versions[game] = versions.get(game, 0) + 1
        self.data['selected'].setdefault(account, {})[game] = locale

    def prepared(self, game: str, locale: str) -> dict | None:
        with self.lock:
            value = self.data['prepared'].get(game, {}).get(locale)
            return dict(value) if value else None

    def entries(self):
        with self.lock:
            return [(game, locale, tuple(value['targets'])) for game, sources in self.data['prepared'].items()
                    if game in GAME_LOCALES for locale, value in sources.items()]

    def status(self, game: str, account: str = 'legacy') -> dict:
        if game not in GAME_LOCALES:
            raise ValueError('Unsupported game language setup')
        with self.lock:
            return {'selected': self.selected(game, account), 'locales': [
                {'locale': locale, 'language': study_language(locale), 'name': LOCALE_NAMES[locale],
                 'reader_available': locale in self.supported(game),
                 'prepared': self.prepared(game, locale),
                 'job': dict(self.jobs.get((game, locale), {}))}
                for locale in GAME_LOCALES[game]]}

    def request(self, game: str, locale: str, target: str, account: str = 'legacy', *, refresh=False, rebuild=False) -> bool:
        if game not in GAME_LOCALES or locale not in GAME_LOCALES[game] or locale not in self.supported(game):
            raise ValueError('This game language needs a compatible reader before preparation.')
        if not isinstance(target, str) or not target or len(target) > 24:
            raise ValueError('Reload the translation language from Lexirise.')
        with self.lock:
            if self.stop_event.is_set():
                return False
            key = (game, locale)
            if self.jobs.get(key, {}).get('state') == 'preparing':
                return False
            old = self.prepared(game, locale)
            targets = tuple(dict.fromkeys([*(old or {}).get('targets', []), target]))
            self.jobs[key] = {'state': 'preparing', 'progress': 0, 'message': 'Preparing selected language'}
            worker = threading.Thread(target=self._run, args=(PreparationJob(self, self.stop_event), game, locale, targets, account, refresh, rebuild), daemon=True,
                                      name=f'prepare-{game}-{locale}')
            self._workers.add(worker)
            worker.start()
            return True

    def _run(self, job, game, locale, targets, account, refresh, rebuild=False):
        key = (game, locale)
        try:
            job.checkpoint()
            builder = self.rebuild if rebuild else self.build
            builder(game, locale, targets, **({'job': job} if self.cancellable else {}))
            job.checkpoint()
            state = self.state(game, locale)
            if not state.get('ready'):
                raise ValueError(state.get('message') or 'Language preparation is incomplete; check installed files and tools.')
            with job.publication():
                self.data['prepared'].setdefault(game, {})[locale] = {
                    'targets': list(targets), 'prepared_at': datetime.now(timezone.utc).isoformat(),
                    'mapped_lines': state.get('audio_count', 0)}
                if not refresh:
                    self._select(game, locale, account)
                self._save()
                self.jobs[key] = {'state': 'ready', 'progress': 100, 'message': state.get('message', 'Language prepared')}
                job.checkpoint()
                self.activate(game, locale, account)
        except PreparationCancelled:
            pass
        except Exception as error:
            with self.lock:
                if job.current():
                    self.jobs[key] = {'state': 'error', 'progress': 100, 'message': str(error)}
        finally:
            with self.lock:
                self._workers.discard(threading.current_thread())

    def select(self, game: str, locale: str, account: str = 'legacy') -> None:
        with self.lock:
            if not self.prepared(game, locale):
                raise ValueError('Prepare this language first.')
            self._select(game, locale, account)
            self._save()
        self.activate(game, locale, account)

    def remove(self, game: str, locale: str) -> None:
        with self.lock:
            if self.jobs.get((game, locale), {}).get('state') == 'preparing':
                raise ValueError('Wait for language preparation before removing its table.')
            self.data['prepared'].get(game, {}).pop(locale, None)
            for account, values in self.data['selected'].items():
                if values.get(game) == locale:
                    self._select(game, None, account)
                    del values[game]
            self.jobs.pop((game, locale), None)
            self._save()
        # Selection is disabled immediately. Other games, local credentials and
        # shared extraction tools are never removed by this operation.

    def refresh_prepared(self):
        for game, locale, targets in self.entries():
            if self.stop_event.is_set():
                break
            if targets:
                self.request(game, locale, targets[0], refresh=True)

    def start(self):
        with self._lifecycle_lock, self.lock:
            if self.monitor and self.monitor.is_alive() and not self.stop_event.is_set():
                return
            if self.stop_event.is_set():
                self.stop_event = threading.Event()
                # Retired workers may still unwind after a failed quiesce.
                # Their immutable token cannot publish into this generation.
                for key, job in self.jobs.items():
                    if job.get('state') == 'preparing':
                        self.jobs[key] = {'state': 'cancelled', 'progress': 0, 'message': 'Preparation stopped'}
            # The constructor already owns the initial generation. Attaching
            # its first monitor must preserve explicit preparation in standby.
            cancelled = self.stop_event
            def run():
                try:
                    while not cancelled.is_set():
                        with self.lock:
                            if self.stop_event is not cancelled:
                                return
                            self.refresh_prepared()
                        cancelled.wait(120)
                finally:
                    with self.lock:
                        self._monitors.discard(threading.current_thread())
            self.monitor = threading.Thread(target=run, daemon=True, name='prepared-language-updates')
            self._monitors.add(self.monitor)
            self.monitor.start()

    def close(self, timeout=5):
        deadline = time.monotonic() + timeout
        self.stop_event.set()
        message = 'Language preparation did not stop before the quiesce deadline.'
        if not self._lifecycle_lock.acquire(timeout=max(0, deadline - time.monotonic())):
            raise TimeoutError(message)
        try:
            self.stop_event.set()
            if not self.lock.acquire(timeout=max(0, deadline - time.monotonic())):
                raise TimeoutError(message)
            try:
                workers = [*self._workers, *self._monitors]
                for key, job in self.jobs.items():
                    if job.get('state') == 'preparing':
                        self.jobs[key] = {'state': 'cancelled', 'progress': 0, 'message': 'Preparation stopped'}
            finally:
                self.lock.release()
            for worker in workers:
                if worker is not threading.current_thread():
                    worker.join(timeout=max(0, deadline - time.monotonic()))
            if any(worker.is_alive() for worker in workers):
                raise TimeoutError(message)
        finally:
            self._lifecycle_lock.release()
