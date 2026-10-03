from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading

from rapidfuzz import fuzz

from .models import TextMatch


def normalize(value: str) -> str:
    return ''.join(c.casefold() for c in value if c.isalnum())


def sentence_identity(value: str) -> str:
    # Digits are quantities in the generated counterpart, not separate sentences.
    return re.sub(r'\d+(?:\.\d+)?', '<amount>', normalize(value))


class HitoTextIndex:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.ready = False
        self.message = 'Waiting for Hito game files'
        self._records: list[dict] = []
        self._cache: dict[str, TextMatch | None] = {}
        self._archive: Path | None = None
        self._process: subprocess.Popen | None = None
        self._responses: queue.Queue = queue.Queue()
        self._lock = threading.RLock()
        self._preparing = False
        self._closed = False
        self._thread: threading.Thread | None = None
        cached = data_dir / 'textmap.json'
        if cached.exists():
            try:
                self._records = json.loads(cached.read_text(encoding='utf-8'))['records']
                self.ready = bool(self._records)
                self.message = 'Cached Hito game text loaded'
            except (ValueError, OSError, KeyError):
                pass

    def status(self) -> dict:
        return dict(ready=self.ready, state='ready' if self.ready else 'loading',
                    message=self.message, entry_count=len(self._records))

    def ensure_game_files(self, executable: Path | None) -> None:
        if executable is None or self._closed:
            return
        archive = executable.parent / 'resources' / 'app.asar'
        if not archive.is_file():
            self.message = 'Hito resources/app.asar was not found'
            return
        with self._lock:
            if self._preparing or (archive == self._archive and self._process is not None
                                   and self._process.poll() is None):
                return
            self._archive = archive
            self._preparing = True
            self.message = 'Reading Hito dialogue and grammar from game files'
            self._thread = threading.Thread(target=self._prepare, args=(archive,), daemon=True)
            self._thread.start()

    def _prepare(self, archive: Path) -> None:
        process = None
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            node = shutil.which('node')
            if not node:
                raise RuntimeError('Node.js is needed to read Hito grammar')
            env = os.environ.copy()
            installed = Path(env.get('LOCALAPPDATA', '')) / 'Programs/Proxy Transcript/frontend/node_modules'
            project = Path(env.get('PROXY_TRANSCRIPT_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
            env['NODE_PATH'] = os.pathsep.join([str(installed), str(project / 'node_modules')])
            with (self.data_dir / 'grammar.log').open('w', encoding='utf-8') as errors:
                process = subprocess.Popen(
                    [node, str(Path(__file__).with_name('hito-grammar.cjs')), str(archive)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                    text=True, encoding='utf-8', env=env,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                )
            responses: queue.Queue = queue.Queue()

            def read_responses() -> None:
                try:
                    for line in process.stdout:
                        responses.put(json.loads(line))
                except (OSError, ValueError):
                    pass
                finally:
                    responses.put(None)

            threading.Thread(target=read_responses, daemon=True).start()
            catalog = responses.get(timeout=90)
            if not catalog or not catalog.get('records'):
                raise RuntimeError('Unsupported Hito grammar; see data/hito/grammar.log')
            with self._lock:
                if self._closed:
                    process.terminate()
                    return
                previous = self._process
                self._process = process
                self._responses = responses
                self._records = catalog['records']
                self._cache.clear()
                self.ready = True
                self.message = 'Hito game text and generated-sentence validation ready'
                if previous and previous.poll() is None:
                    previous.terminate()
                cached = self.data_dir / 'textmap.json'
                temporary = cached.with_suffix('.tmp')
                temporary.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')
                temporary.replace(cached)
        except Exception as error:
            if process and process.poll() is None:
                process.terminate()
            self.message = f'Hito game-file reader: {error}'
        finally:
            self._preparing = False

    def _generated(self, text: str) -> list[dict]:
        process = self._process
        if process is None or process.poll() is not None:
            return []
        try:
            process.stdin.write(json.dumps({'text': text}, ensure_ascii=False) + '\n')
            process.stdin.flush()
            result = self._responses.get(timeout=3)
            return result.get('records', []) if result else []
        except (OSError, queue.Empty):
            process.terminate()
            self.message = 'Hito grammar validation timed out; fixed game text remains available'
            return []

    @staticmethod
    def _choose(text: str, records: list[dict]) -> TextMatch | None:
        chinese = bool(re.search(r'[\u3400-\u9fff]', text))
        target = normalize(text)
        if not target:
            return None
        ranked = []
        for row in records:
            candidate = normalize(row['chinese' if chinese else 'english'])
            if abs(len(candidate) - len(target)) > 2:
                continue
            score = fuzz.ratio(target, candidate)
            # Short phrases must match exactly. Never complete a typewriter prefix.
            if score < (100 if len(target) < 12 else 94):
                continue
            if candidate.startswith(target) and candidate != target:
                continue
            ranked.append((score, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked:
            return None
        score, row = ranked[0]
        different = next((s for s, r in ranked[1:] if
                          (r['chinese'], r['english']) != (row['chinese'], row['english'])), None)
        if different is not None and score - different < 4:
            return None
        identity = sentence_identity(row.get('identity') or row['english'])
        key = hashlib.sha256(identity.encode()).hexdigest()[:24]
        return TextMatch(game='hito', text_id=f'hito:{key}', english=row['english'],
                         chinese=row['chinese'], source_ocr=text, score=score,
                         kind='exact' if score == 100 else 'fuzzy')

    def match_lines(self, lines: list[str]) -> TextMatch | None:
        with self._lock:
            hanzi = [line.strip() for line in lines if len(normalize(line)) >= 2
                     and re.search(r'[\u3400-\u9fff]', line)]
            selected = hanzi or [line.strip() for line in lines if len(normalize(line)) >= 4]
            if not selected:
                return None
            # Exclude separate pinyin rows; preserve wrapped Mandarin lines.
            text = ' '.join(selected)
            cache_key = normalize(text)
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                return cached.model_copy(update={'source_ocr': text}) if cached else None
            match = self._choose(text, self._records)
            if match is None:
                match = self._choose(text, self._generated(text))
            if len(self._cache) > 1000:
                self._cache.clear()
            self._cache[cache_key] = match
            return match

    def close(self) -> None:
        self._closed = True
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                self._process.wait(timeout=5)
