from __future__ import annotations

import hashlib
import json
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from .update_workers import start_process, stop_process

from rapidfuzz import fuzz

from .models import TextMatch
from .bilingual import normalize_chinese, simplify_chinese


def normalize(value: str) -> str:
    return normalize_chinese(value)


def sentence_identity(value: str) -> str:
    # Digits are quantities in the generated counterpart, not separate sentences.
    return re.sub(r'\d+(?:\.\d+)?', '<amount>', normalize(value))


class HitoTextIndex:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.ready = False
        self.message = 'Waiting for Hito game files'
        self._records: list[dict] = []
        self._pinyin_words: set[str] = set()
        self._cache: dict[str, TextMatch | None] = {}
        self._archive: Path | None = None
        self._process: subprocess.Popen | None = None
        self._starting_process: subprocess.Popen | None = None
        self._responses: queue.Queue = queue.Queue()
        self._lock = threading.RLock()
        self._preparing = False
        self._closed = False
        self._retry_at = 0.0
        self._signature: tuple | None = None
        self._thread: threading.Thread | None = None
        self._response_threads = []
        self._owned_processes = []
        cached = data_dir / 'textmap.json'
        if cached.exists():
            try:
                catalog = json.loads(cached.read_text(encoding='utf-8'))
                self._records = catalog['records']
                self._load_pinyin(catalog)
                self.ready = bool(self._records)
                self.message = 'Cached Hito game text loaded'
            except (ValueError, OSError, KeyError):
                pass

    def status(self) -> dict:
        return dict(ready=self.ready, state='ready' if self.ready else 'loading',
                    message=self.message, entry_count=len(self._records))

    def _load_pinyin(self, catalog: dict) -> None:
        self._pinyin_words = {word.casefold() for row in catalog.get('vocabulary', [])
                              for word in re.findall(r'[a-z]+', row.get('pinyin', '').lower())}

    def ensure_game_files(self, executable: Path | None) -> None:
        if self._closed:
            return
        from .game_paths import configured_install, discover_install
        root = executable.parent if executable else discover_install('hito')
        if root is None:
            return
        archive = root / 'resources' / 'app.asar'
        if not archive.is_file():
            root = configured_install('hito')
            if root:
                archive = root / 'resources' / 'app.asar'
        self._ensure_archive(archive)

    def refresh(self) -> bool:
        """Re-read the last detected game archive after a Hito update."""
        with self._lock:
            archive = self._archive
            self._retry_at = 0.0
            self._signature = None
        return self._ensure_archive(archive, force=True) if archive else False

    def _ensure_archive(self, archive: Path, force: bool = False) -> bool:
        if self._closed:
            return False
        if not archive.is_file():
            self.message = 'Hito resources/app.asar was not found'
            return False
        with self._lock:
            if self._closed:
                return False
            stat = archive.stat()
            signature = (archive, stat.st_size, stat.st_mtime_ns)
            if self._preparing or (not force and time.monotonic() < self._retry_at) or (not force and signature == self._signature and self._process is not None
                                   and self._process.poll() is None):
                return False
            self._signature = signature
            self._archive = archive
            self._preparing = True
            # Keep the last complete catalog available while probing a newer
            # game bundle. A grammar-format change must not disable known text.
            self.ready = bool(self._records)
            self._cache.clear()
            self.message = 'Reading Hito dialogue and grammar from game files'
            self._thread = threading.Thread(target=self._prepare, args=(archive,), daemon=True)
            self._thread.start()
            return True

    def _prepare(self, archive: Path) -> None:
        process = None
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            from .node_tools import grammar_command
            command, env = grammar_command(archive, self.data_dir / 'textmap.json')
            with self._lock, (self.data_dir / 'grammar.log').open('w', encoding='utf-8') as errors:
                if self._closed:
                    return
                process = start_process(
                    command,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                    text=True, encoding='utf-8', env=env,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                )
                self._starting_process = process
                self._owned_processes.append(process)
            responses: queue.Queue = queue.Queue()

            def read_responses() -> None:
                try:
                    for line in process.stdout:
                        responses.put(json.loads(line))
                except (OSError, ValueError):
                    pass
                finally:
                    responses.put(None)

            reader = threading.Thread(target=read_responses, daemon=True)
            with self._lock:
                self._response_threads.append(reader)
                reader.start()
            catalog = responses.get(timeout=90)
            if not catalog or not catalog.get('records'):
                raise RuntimeError('Unsupported Hito grammar; see data/hito/grammar.log')
            with self._lock:
                if self._closed:
                    stop_process(process)
                    return
                previous = self._process
                self._process = process
                self._responses = responses
                self._records = catalog['records']
                self._load_pinyin(catalog)
                self._cache.clear()
                self.ready = True
                self.message = 'Hito game text and generated-sentence validation ready'
                if previous and previous.poll() is None:
                    stop_process(previous)
                cached = self.data_dir / 'textmap.json'
                temporary = cached.with_suffix('.tmp')
                temporary.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')
                temporary.replace(cached)
        except Exception as error:
            if process and process.poll() is None:
                stop_process(process)
            if self._records:
                self.ready = True
                self.message = f'Cached Hito text ready; game grammar update deferred: {error}'
            else:
                self.ready = False
                self.message = f'Hito game-file reader: {error}'
            self._retry_at = time.monotonic() + 60
        finally:
            self._starting_process = None
            self._preparing = False

    def _generated(self, text: str) -> list[dict]:
        process = self._process
        if process is None or process.poll() is not None:
            return []
        try:
            process.stdin.write(json.dumps({'text': simplify_chinese(text)}, ensure_ascii=False) + '\n')
            process.stdin.flush()
            result = self._responses.get(timeout=3)
            return result.get('records', []) if result else []
        except (OSError, queue.Empty):
            stop_process(process)
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
            if re.findall(r'\d+(?:\.\d+)?', text) != re.findall(
                    r'\d+(?:\.\d+)?', row['chinese' if chinese else 'english']):
                continue
            if chinese and any((word in target) != (word in candidate)
                               for word in ('不', '没', '能', '应该', '正在', '必须')):
                continue
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
                          normalize(r['chinese' if chinese else 'english']) !=
                          normalize(row['chinese' if chinese else 'english'])), None)
        if different is not None and score - different < 4:
            return None
        alternatives = {r['english']: r for s, r in ranked if s == score and
                        normalize(r['chinese' if chinese else 'english']) ==
                        normalize(row['chinese' if chinese else 'english'])}
        counterparts = sorted(alternatives)
        identity = '|'.join(sorted({sentence_identity(r.get('identity') or r['english'])
                                    for r in alternatives.values()}))
        key = hashlib.sha256(identity.encode()).hexdigest()[:24]
        return TextMatch(game='hito', text_id=f'hito:{key}', english=' / '.join(counterparts),
                         chinese=row['chinese'], source_ocr=text, score=score,
                         kind='exact' if score == 100 else 'fuzzy', ambiguous=len(counterparts) > 1)

    def match_lines(self, lines: list[str]) -> TextMatch | None:
        with self._lock:
            hanzi = [line.strip() for line in lines if len(normalize(line)) >= 2
                     and re.search(r'[\u3400-\u9fff]', line)]
            selected = hanzi or [line.strip() for line in lines if len(normalize(line)) >= 4]
            if not selected:
                return None
            # OCR splits mixed-language narrative into several rows. Keep its English
            # fragments, removing only annotation rows composed of game pinyin words.
            narrative = []
            for line in lines:
                words = re.findall(r'[a-z]+', line.casefold())
                annotation = (words and not re.search(r'[\u3400-\u9fff]', line)
                              and all(word in self._pinyin_words for word in words))
                if line.strip() and not annotation:
                    narrative.append(line.strip())
            text = ' '.join(narrative if self._pinyin_words else selected)
            cache_key = normalize(text)
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                return cached.model_copy(update={'source_ocr': text}) if cached else None
            match = self._choose(text, self._records)
            if match is None and text != ' '.join(selected):
                # A noisy pinyin row must not hide an otherwise complete Hanzi line.
                match = self._choose(' '.join(selected), self._records)
            if match is None:
                match = self._choose(text, self._generated(text))
            fallback = ' '.join(selected)
            if match is None and text != fallback and hanzi and not re.search(r'[a-z]', fallback, re.I):
                # Grammar-made annotations (such as yige) are not dictionary words.
                # Validate the complete Hanzi row through the game grammar as well.
                match = self._choose(fallback, self._generated(fallback))
            if len(self._cache) > 1000:
                self._cache.clear()
            self._cache[cache_key] = match
            return match

    def close(self) -> None:
        with self._lock:
            self._closed = True
            processes = list(self._owned_processes)
            worker = self._thread
        for process in processes:
            stop_process(process)
        if worker:
            worker.join(timeout=10)
            if worker.is_alive():
                raise RuntimeError('Game grammar preparation is still stopping.')
        # The preparation worker can register a reader just after close starts.
        for reader in self._response_threads:
            reader.join(timeout=5)
            if reader.is_alive():
                raise RuntimeError('Game grammar responses are still stopping.')
        self._owned_processes.clear()
        self._response_threads.clear()

    def resume(self) -> None:
        with self._lock:
            if (self._thread and self._thread.is_alive()) or any(t.is_alive() for t in self._response_threads):
                raise RuntimeError('Game grammar has not finished stopping.')
            self._closed = False
