from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path

import httpx

from .lexirise import API_BASE, LexiriseError, LexiriseService


class LexiriseReadingService:
    """Read-only analysis for the transcript. The API key stays on the PC."""

    def __init__(self, directory: Path, lexirise: LexiriseService):
        self.path = directory / "reading-cache.db"
        self.lexirise = lexirise
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lexirise-gloss")
        directory.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (kind TEXT, key TEXT, value TEXT, at REAL, PRIMARY KEY(kind,key))")

    def _cached(self, kind: str, key: str, max_age: float):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT value,at FROM cache WHERE kind=? AND key=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row and time.time() - row[1] < max_age else None

    def _save(self, kind: str, key: str, value: dict):
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (kind, key, json.dumps(value), time.time()))

    def _post(self, path: str, payload: dict) -> dict:
        with httpx.Client(base_url=API_BASE, headers={"Authorization": f"Bearer {self.lexirise._key()}"},
                          timeout=25, follow_redirects=False, transport=self.lexirise.transport) as client:
            return LexiriseService._request(client, "POST", path, json=payload)

    def _meaning(self, word: str) -> str:
        cached = self._cached("meaning", word, 30 * 86400)
        if cached is not None:
            return cached.get("meaning", "")
        result = self._post("/v1/dictionary/lookup", {"text": word, "language": "zh"})
        translations = result.get("translations") or []
        meaning = next((item.get("translation", "") for item in translations
                        if item.get("target_lang") == "en" and isinstance(item.get("translation"), str)), "")
        self._save("meaning", word, {"meaning": meaning})
        return meaning

    def analyze(self, text: str) -> dict:
        if not text.strip() or len(text) > 1600:
            raise LexiriseError("This sentence is too long for Lexirise reading analysis.")
        result = self._cached("analysis", text, 10 * 60)
        if result is None:
            result = self._post("/v1/analyze/text", {"text": text, "language": "zh", "fast": True})
            self._save("analysis", text, result)
        states = result.get("stateByEntryId") or {}
        tokens = []
        last_end = 0
        # Lexirise offsets are UTF-16 units, which also match JavaScript slice.
        text_length = len(text.encode("utf-16-le")) // 2
        for item in sorted(result.get("occurrences") or [], key=lambda value: value.get("charStart", 0)):
            start, end = item.get("charStart"), item.get("charEnd")
            if not item.get("isWordLike") or not isinstance(start, int) or not isinstance(end, int):
                continue
            if start < last_end or end <= start or end > text_length:
                continue
            word = item.get("word")
            if not isinstance(word, str) or not word:
                continue
            entry_id = item.get("entryId")
            state = states.get(str(entry_id), {}) if entry_id is not None else {}
            proficiency = state.get("proficiency", 0) if isinstance(state, dict) else 0
            if not isinstance(proficiency, int) or proficiency not in range(5):
                proficiency = 0
            tokens.append({"start": start, "end": end, "word": word,
                           "pinyin": item.get("transliteration") or "",
                           "proficiency": proficiency, "meaning": ""})
            last_end = end
        unknown = list(dict.fromkeys(token["word"] for token in tokens if token["proficiency"] < 4))
        meanings = {}
        futures = {self.pool.submit(self._meaning, word): word for word in unknown}
        for future in as_completed(futures):
            try:
                meanings[futures[future]] = future.result()
            except LexiriseError:
                # Analysis and pinyin remain useful during dictionary outages.
                pass
        for token in tokens:
            token["meaning"] = meanings.get(token["word"], "")
        return {"text": text, "tokens": tokens}
