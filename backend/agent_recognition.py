from __future__ import annotations

from collections import Counter
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
import tempfile
import time
import wave

import numpy as np

from .agent_fingerprint import HOP, RATE, landmarks, mono_audio, waveform_score
from .agent_store import AgentVoiceStore
from .voice_assets import VoiceEntry
from .agent_library import atomic_json


# Some playable variants do not expose a character voice-bank name in the
# avatar metadata used to seed library.json.  Keep their public UI identity
# here so a shared suffix ("Anby") cannot collapse the variant into the base
# agent before dynamic nameplate learning has a chance to run.
BUILTIN_AGENT_IDENTITIES = {
    'Soldier 0 - Anby': {'name': 'Soldier 0 - Anby', 'chinese_name': '零号·安比'},
}


class AgentRecognizer:
    def __init__(self, folder: Path, audio, publish, activity=None):
        self.folder, self.audio, self.publish = folder, audio, publish
        self.store = AgentVoiceStore(folder / 'entries.db')
        self.library = json.loads((folder / 'library.json').read_text(encoding='utf-8')) if (folder / 'library.json').exists() else {'agents':{}, 'clips':{}}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='zzz-agent-voice')
        self._future = None
        self._pending = []
        self._context: tuple[str | None, float, float] = (None, 0., 0.)
        self._selected_at = 0.
        self._lock = threading.Lock()
        self._last_scan = 0.
        self._occurrences: dict[str, float] = {}
        self._last_error = None
        self._last_match = None
        self._replay_until = 0.
        self.indexed = 0
        self._consumed_until = 0.
        self.activity = activity
        self.updating = False
        self.updater = None
        self._diagnostics = {}
        names = folder/'observed-agents.json'
        self.observed_agents = json.loads(names.read_text(encoding='utf-8')) if names.exists() else {}
        self.library['agents'].update(BUILTIN_AGENT_IDENTITIES)
        self.library['agents'].update(self.observed_agents)

    def replace_library(self, library):
        library['agents'].update(BUILTIN_AGENT_IDENTITIES)
        library['agents'].update(self.observed_agents)
        with self._lock:
            self.library = library
            self._last_error = None

    def remember_agent(self, name):
        if name not in self.library['agents']:
            self.observed_agents[name] = {'name': name}
            atomic_json(self.folder/'observed-agents.json', self.observed_agents)
            self.replace_library({**self.library, 'agents': {**self.library['agents'], name: {'name': name}}})

    def close(self):
        self._executor.shutdown(wait=True, cancel_futures=True)

    def identify_agent(self, lines: list[str]) -> str | None:
        # Names may move between the top and bottom in controller/keyboard UI.
        # Ignore surrounding icon glyphs, but never fuzzy-match another agent.
        values = {re.sub(r'^[\W_]+|[\W_]+$', '', line.casefold()).strip() for line in lines}
        prompts = r'(?:lb|rb|lt|rt|ls|rs|l1|r1|[abxy])'
        values |= {re.sub(rf'^(?:{prompts}\s+)+|(?:\s+{prompts})+$', '', value).strip()
                   for value in values}
        matches = [name for name in self.library['agents'] if name.casefold() in values]
        if len(matches) == 1:
            return matches[0]
        if matches:
            # The OCR response may contain both "Anby" and the full
            # "Soldier 0 - Anby" label. Prefer the uniquely most-specific
            # identity, but retain the ambiguity guard for unrelated agents.
            longest = max(matches, key=len)
            if all(name.casefold() in longest.casefold() for name in matches):
                return longest
        return None

    def observe(self, agent: str | None, active: bool, observed_since: float | None = None):
        now = time.monotonic()
        with self._lock:
            previous, since, _seen = self._context
            selected = agent if active else None
            # Names are read shortly after the selection animation begins.
            # Retain a small pre-roll so the start of its voice isn't discarded.
            start = min(now, max(now-12, observed_since)) if observed_since is not None else now-(2.0 if previous is None else .6)
            if selected != previous:
                self._selected_at = now
            self._context = (selected, since if selected == previous else start, now)
        if previous and previous != selected and not self.updating and now >= self._replay_until:
            self._submit_snapshot(previous, max(since, now-12., self._consumed_until), now, since)
        if self.updating or not selected or now < self._replay_until or now-self._last_scan < 1.5:
            return
        if now-self._selected_at < 1.1:
            return  # wait for speech, not just the music in the pre-roll
        if self._future is not None and not self._future.done():
            return
        self._last_scan = now
        # Snapshot on the caller thread: a slow index query must not read future
        # audio and attribute it to a character who was selected earlier.
        begin = max(since if selected == previous else start, now - 12., self._consumed_until)
        self._submit_snapshot(selected, begin, now, since if selected == previous else start)

    def _submit_snapshot(self, agent, begin, end, since):
        self._pending = [future for future in self._pending if not future.done()]
        if len(self._pending) >= 8:
            self._last_error = 'Voice recognition is catching up with rapid agent changes'
            return
        samples = self.audio._samples_between(begin, end)
        if len(samples) < int(self.audio.sample_rate*1.6):
            return
        self._future = self._executor.submit(self._recognize, agent, begin, samples, self.audio.sample_rate, since)
        self._pending.append(self._future)

    def status(self, include_database_counts=True):
        try:
            path = self.folder / 'fingerprints.db'
            if include_database_counts and path.exists():
                with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True, timeout=.05)) as db:
                    self.indexed = db.execute('SELECT COUNT(*) FROM clips').fetchone()[0]
        except sqlite3.Error:
            pass
        return {'indexed_clips': self.indexed, 'total_clips': len(self.library['clips']),
                'selected_agent': self._context[0], 'last_match': self._last_match,
                'last_error': self._last_error, 'saved_lines': self.store.count(),
                'recognition': self._diagnostics,
                'update': self.updater.status() if self.updater else None}

    def suppress_playback(self, seconds: float = 35):
        self._replay_until = time.monotonic() + min(max(seconds, 1), 40)
        self._consumed_until = max(self._consumed_until, self._replay_until)

    def _recognize(self, agent, begin, samples, sample_rate, context_since=None):
        try:
            observed = mono_audio(samples, sample_rate)
            self._diagnostics = {'checked_at': time.time(), 'seconds': round(len(observed)/RATE,2),
                                 'level': round(float(np.sqrt(np.mean(observed**2))),5), 'best_score': 0.}
            # Once a voice has been learned, replay recognition avoids querying
            # millions of global landmarks. Still verify its actual waveform.
            known = self._waveform_candidates(self.store.assets_for_agent(agent), observed, begin)
            if known:
                return self._accept_candidates(known, agent, begin, context_since)
            points = landmarks(observed)
            points = points[::max(1, (len(points)+1399)//1400)]
            if len(points) < 10:
                return
            database_path = self.folder / 'fingerprints.db'
            if not database_path.exists():
                return
            votes: Counter = Counter()
            query = {}
            for value, frame in points:
                for delta in (-1, 0, 1):
                    query.setdefault(value+delta, []).append(frame)
            with closing(sqlite3.connect(f'file:{database_path.as_posix()}?mode=ro', uri=True, timeout=.2)) as db:
                self.indexed = db.execute('SELECT COUNT(*) FROM clips').fetchone()[0]
                keys = list(query)
                for start in range(0, len(keys), 400):
                    batch = keys[start:start+400]
                    for value, asset, reference_frame in db.execute(
                        'SELECT hash,asset_id,frame FROM hashes WHERE hash IN ('+','.join('?' for _ in batch)+') AND frame <= ?',
                        [*batch, max(frame for _,frame in points)+2]):
                        for observed_frame in query[value]:
                            offset = observed_frame-reference_frame
                            if offset < -2:
                                continue
                            votes[(asset, round(offset/4))] += 1
            if not votes:
                return
            assets = []
            for (asset, _bucket), count in votes.most_common(20):
                if count < 12 or asset in assets:
                    continue
                assets.append(asset)
            self._accept_candidates(self._waveform_candidates(assets, observed, begin), agent, begin, context_since)
        except Exception as error:
            self._last_error = str(error)

    def _waveform_candidates(self, assets, observed, begin):
        candidates = []
        for asset in assets:
            if asset not in self.library['clips']:
                continue
            path = self.folder / 'pcm' / f'{asset}.npy'
            if not path.exists():
                continue
            reference = np.load(path, allow_pickle=False)
            core = reference[:min(len(reference), int(1.5*RATE))]
            score, start = waveform_score(core, observed)
            self._diagnostics['best_score'] = max(self._diagnostics.get('best_score',0.), round(score,3))
            onset = begin + start / RATE
            if score >= .42 and abs(self._occurrences.get(asset, float('-inf'))-onset) >= 1.:
                candidates.append((score, asset, start))
        return candidates

    def _accept_candidates(self, candidates, agent, begin, context_since=None):
        try:
            candidates.sort(key=lambda item:item[0], reverse=True)
            if not candidates or (len(candidates)>1 and candidates[0][0]-candidates[1][0]<.06):
                return
            score, asset, start = candidates[0]
            onset = begin + start / RATE
            if abs(self._occurrences.get(asset, float('-inf'))-onset) < 1.:
                return
            with self._lock:
                selected, since, seen_at = self._context
            # A snapshot captured on the previous agent remains valid while
            # background matching finishes after the player changes character.
            valid_context = (onset >= context_since-.2 if context_since is not None
                             else selected == agent and onset >= since-.2 and time.monotonic()-seen_at <= 3)
            if not valid_context or time.monotonic() < self._replay_until:
                return
            self._occurrences[asset] = onset
            if self.activity:
                self.activity(agent)
            self._consumed_until = max(self._consumed_until, onset + .45)
            if len(self._occurrences)>200:
                self._occurrences = {k:v for k,v in self._occurrences.items() if v>time.monotonic()-60}
            original, original_rate, target = self._original_audio(asset)
            chinese = self.store.transcript(asset) or self._transcribe(original, original_rate)
            if not re.search('[\u4e00-\u9fff]', chinese):
                return
            line = self.store.record(agent, asset, chinese)
            self._last_match = {'agent':agent,'asset_id':asset,'score':round(score,3)}
            self._last_error = None
            self.publish(line)
        except Exception as error:
            self._last_error = str(error)

    def _original_audio(self, asset):
        entry = self.library['clips'][asset]
        path = Path(entry['package'])
        stat = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (entry['package_size'], entry['package_mtime_ns']):
            raise ValueError('Game voice files changed; automatic refresh is pending')
        target = self.folder / 'audio' / f'{asset}.wav'
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            decoder = self.folder.parent / 'voice-assets/vgmstream/vgmstream-cli.exe'
            with tempfile.TemporaryDirectory(prefix='agent-', dir=self.folder) as scratch:
                wem, wav = Path(scratch)/'voice.wem', Path(scratch)/'voice.wav'
                wem.write_bytes(VoiceEntry(path, entry['offset'], entry['size'], entry['file_id']).read())
                subprocess.run([str(decoder), '-o', str(wav), str(wem)], capture_output=True,
                               check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
                wav.replace(target)
        with wave.open(str(target)) as audio:
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32)/32768
            samples = samples.reshape(-1,audio.getnchannels()).mean(axis=1)
            return samples, audio.getframerate(), target

    def _transcribe(self, reference, rate=RATE):
        # sherpa and FireRedVAD ship incompatible ONNX Runtime DLL versions on
        # Windows. Never import sherpa into the capture process: its native
        # failure cannot be caught by Python and would stop all story capture.
        model = next((self.folder / 'model').rglob('model.int8.onnx'))
        with tempfile.TemporaryDirectory(prefix='zzz-transcribe-') as scratch:
            source = Path(scratch) / 'voice.wav'
            with wave.open(str(source), 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(rate)
                output.writeframes((np.clip(reference,-1,1)*32767).astype('<i2').tobytes())
            result = subprocess.run(
                [sys.executable, '-m', 'backend.agent_transcribe', str(model), str(source)],
                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                text=True, encoding='utf-8', timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError(f'Local transcription failed ({result.returncode}); capture is still running')
            return json.loads(result.stdout)['text']
