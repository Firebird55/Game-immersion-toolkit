"""Self-maintaining local Mandarin voice library; never modifies game files."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import threading

from .agent_bank import bank_media, package_table


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def package_inventory(game_data: Path) -> dict:
    result = {}
    for layer in ('StreamingAssets', 'Persistent'):
        folder = game_data / layer / 'Audio/Windows/Full/Cn'
        for pattern in ('SoundBank*.pck', 'Streamed*.pck'):
            for path in sorted(folder.glob(pattern)):
                stat = path.stat()
                result[str(path.resolve())] = [stat.st_size, stat.st_mtime_ns]
    return result


def stable_asset_id(media_id: int, digest: str, previous_by_media: dict, previous_by_digest=None, adopt_legacy=False) -> str:
    if previous_by_digest and digest in previous_by_digest:
        return previous_by_digest[digest]
    old = previous_by_media.get(media_id)
    # Adopt hashes for the existing installation without changing saved IDs.
    if old and ((adopt_legacy and not old[1].get('sha256')) or old[1].get('sha256') == digest):
        return old[0]
    if not old:
        return str(media_id)
    # A reused Wwise ID with different audio is a new clip, not a duplicate of
    # the user's old saved voice. Keep the old entry and its playback intact.
    return str(int(digest[:24], 16))


def build_library(game_data: Path, previous: dict) -> dict:
    inventory = package_inventory(game_data)
    if not inventory:
        raise ValueError('Mandarin voice packages are not available yet')
    banks, streams = {}, {}
    for layer in ('StreamingAssets', 'Persistent'):
        for filename in inventory:
            path = Path(filename)
            if layer not in path.parts:
                continue
            if path.name.startswith('SoundBank'):
                banks.update(package_table(path, 2))
            else:
                streams.update(package_table(path, 3))
    media_entries = dict(streams)
    for bank in banks.values():
        for media_id, embedded in bank_media(bank).items():
            media_entries.setdefault(media_id, embedded)
    old = {int(entry['file_id']): (asset, entry) for asset, entry in previous.get('clips', {}).items()}
    by_digest = {entry['sha256']: asset for asset, entry in previous.get('clips', {}).items() if entry.get('sha256')}
    clips = {}
    for media_id, media in media_entries.items():
        stat = media.package.stat()
        prior = old.get(media_id, ('', {}))[1]
        unchanged = (prior.get('package') == str(media.package)
                     and prior.get('package_size') == stat.st_size
                     and prior.get('package_mtime_ns') == stat.st_mtime_ns
                     and prior.get('offset') == media.offset and prior.get('size') == media.size)
        digest = prior.get('sha256') if unchanged else None
        digest = digest or hashlib.sha256(media.read()).hexdigest()
        asset = stable_asset_id(media_id, digest, old, by_digest, adopt_legacy=unchanged)
        clips[asset] = {'package': str(media.package), 'offset': media.offset, 'size': media.size,
                       'file_id': media_id, 'package_size': stat.st_size,
                       'package_mtime_ns': stat.st_mtime_ns, 'sha256': digest}
    if inventory != package_inventory(game_data):
        raise ValueError('Game update is still writing voice files; will retry automatically')
    if not clips:
        raise ValueError('No supported Mandarin clips found; keeping the existing library')
    return {'version': 2, 'game_data': str(game_data), 'inventory': inventory,
            'agents': previous.get('agents', {}), 'clips': clips}


class AgentLibraryUpdater:
    def __init__(self, recognizer, discover_game=None, interval=60):
        self.recognizer = recognizer
        self.folder = recognizer.folder
        self.discover_game = discover_game
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._process = None
        self.state = 'checking'
        self.message = 'Checking installed Mandarin voices'

    def start(self):
        self._thread = threading.Thread(target=self._run, name='zzz-agent-library', daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
        if self._thread:
            self._thread.join(timeout=5)

    def status(self):
        progress = 100 if self.state == 'ready' else 0
        if self.state == 'updating':
            try:
                with (self.folder / 'update.log').open('rb') as stream:
                    stream.seek(max(0, stream.seek(0, 2) - 4096))
                    tail = stream.read().decode('utf-8', errors='replace')
                steps = re.findall(r'(\d+)/(\d+) clips indexed', tail)
                if steps:
                    done, total = map(int, steps[-1])
                    progress = round(100 * done / max(1, total))
            except OSError:
                pass
        return {'state': self.state, 'message': self.message, 'automatic': True, 'progress': progress}

    def _game_data(self):
        library = self.recognizer.library
        candidates = []
        if library.get('game_data'):
            candidates.append(Path(library['game_data']))
        for entry in list(library.get('clips', {}).values())[:1]:
            candidates.extend(p for p in Path(entry['package']).parents if p.name.endswith('_Data'))
        if self.discover_game:
            discovered = self.discover_game()
            if discovered:
                candidates.insert(0, discovered)
        return next((p for p in candidates if package_inventory(p)), None)

    def check_once(self):
        game_data = self._game_data()
        if game_data is None:
            self.state, self.message = 'waiting', 'Waiting for installed Mandarin game voices'
            return
        previous = self.recognizer.library
        inventory = package_inventory(game_data)
        complete = self.folder / 'index-complete.json'
        indexed = json.loads(complete.read_text()) if complete.exists() else {}
        if previous.get('inventory') == inventory and indexed.get('inventory') == inventory and indexed.get('version') == 2:
            self.state, self.message = 'ready', 'All installed agent voices are up to date'
            self.recognizer.updating = False
            return
        self.state, self.message = 'updating', 'Updating agent voices automatically; story capture continues'
        self.recognizer.updating = True
        # Let any in-flight recognition finish before changing its PCM index.
        future = self.recognizer._future
        if future:
            future.result(timeout=90)
        updated = build_library(game_data, previous)
        if self._stop.is_set():
            return
        pending = self.folder / 'next-library.json'
        atomic_json(pending, updated)
        root = Path(__file__).resolve().parents[1]
        with (self.folder / 'update.log').open('w', encoding='utf-8') as log:
            self._process = subprocess.Popen(
                [sys.executable, '-m', 'scripts.build_agent_fingerprints', '--library', str(pending)],
                cwd=root, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            while self._process.poll() is None:
                if self._stop.wait(1):
                    self._process.terminate()
                    return
            if self._process.returncode:
                raise RuntimeError('Some voice files could not be indexed; retrying automatically')
        if inventory != package_inventory(game_data):
            raise ValueError('Game files changed during indexing; retrying automatically')
        pending.replace(self.folder / 'library.json')
        self.recognizer.replace_library(updated)
        atomic_json(complete, {'version': 2, 'inventory': inventory})
        self.state, self.message = 'ready', 'All installed agent voices are up to date'
        self.recognizer.updating = False

    def _run(self):
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as error:
                self.state, self.message = 'retrying', str(error)
            if self._stop.wait(self.interval):
                break
