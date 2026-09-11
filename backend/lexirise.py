from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx


DECKS = {"zzz": (1950, "Zenless Zone Zero"), "pragmata": (1951, "PRAGMATA")}
API_BASE = "https://api.lexirise.app"


class LexiriseError(Exception):
    """Safe user-facing error; never includes requests, credentials or responses."""


def _protect(value: bytes, decrypt: bool = False) -> bytes:
    """Windows DPAPI, bound to this Windows user's credentials."""
    if os.name != "nt":
        raise LexiriseError("Set LEXIRISE_API_KEY on this non-Windows host.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.windll.crypt32
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise LexiriseError("Cannot access the saved Lexirise key for this Windows user.")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree(result.data)


def save_api_key(directory: Path, key: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    encrypted = _protect(key.strip().encode())
    path = directory / "key.dpapi"
    pending = path.with_suffix(".tmp")
    pending.write_bytes(encrypted)
    pending.replace(path)


class LexiriseService:
    def __init__(self, directory: Path, *, transport=None, api_key: str | None = None):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.db_path = directory / "exports.db"
        self.transport = transport
        self._api_key = api_key
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS exports (key TEXT PRIMARY KEY, state TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS export_refs (ref TEXT PRIMARY KEY, export_key TEXT NOT NULL)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _key(self) -> str:
        key = self._api_key or os.environ.get("LEXIRISE_API_KEY")
        if key:
            return key.strip()
        try:
            return _protect((self.directory / "key.dpapi").read_bytes(), decrypt=True).decode()
        except OSError:
            raise LexiriseError("Lexirise API key is not configured on this computer.") from None

    def status(self) -> dict:
        try:
            configured = bool(self._key())
        except LexiriseError:
            configured = False
        with self._connect() as db:
            rows = db.execute("SELECT ref,state FROM export_refs JOIN exports ON export_key=key").fetchall()
        return {"configured": configured, "decks": {game: {"id": value[0], "title": value[1]} for game, value in DECKS.items()},
                "sent": {ref: json.loads(state)["deck_id"] for ref, state in rows if json.loads(state).get("complete")}}

    @staticmethod
    def _request(client, method, path, **kwargs):
        try:
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("success") is False:
                raise LexiriseError("Lexirise did not confirm the operation. You can retry safely.")
            return result
        except httpx.HTTPStatusError as error:
            code = error.response.status_code
            if code in (401, 403):
                raise LexiriseError("Lexirise rejected the API key or deck access. Check your Pro account and key.") from None
            if code == 429:
                raise LexiriseError("Lexirise's request limit was reached. Please try again later.") from None
            raise LexiriseError(f"Lexirise returned HTTP {code}. Check the deck and audio (maximum 90 seconds), then retry.") from None
        except (httpx.RequestError, ValueError):
            raise LexiriseError("Could not confirm the Lexirise response. Check your connection, then retry.") from None

    @staticmethod
    def _items(client, path, field, **params):
        offset = 0
        while True:
            page = LexiriseService._request(client, "GET", path, params={**params, "limit": 100, "offset": offset})
            items = page.get(field, [])
            yield from items
            more = page.get("hasMore") or page.get("nextOffset") is not None
            if not more or not items:
                return
            offset += len(items)

    @classmethod
    def _deck_contains(cls, client, deck_id: int, vocabulary_id: int, chinese: str) -> bool:
        """Recognize membership by stable ID, with text as an API compatibility fallback."""
        return any(
            item.get("saved_expression_id") == vocabulary_id
            or item.get("id") == vocabulary_id
            or item.get("expression_text") == chinese
            for item in cls._items(client, f"/v1/decks/{deck_id}", "items")
        )

    @staticmethod
    def _confirmed_add_count(result: dict) -> bool:
        """A positive mutation count is authoritative even if a read replica lags."""
        value = result.get("added_count", result.get("addedCount"))
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    def _save(self, db, key, ref, state):
        db.execute("INSERT INTO exports VALUES (?,?) ON CONFLICT(key) DO UPDATE SET state=excluded.state",
                   (key, json.dumps(state)))
        db.execute("INSERT INTO export_refs VALUES (?,?) ON CONFLICT(ref) DO UPDATE SET export_key=excluded.export_key", (ref, key))
        db.commit()

    def send(self, *, ref: str, game: str, chinese: str, english: str, speaker: str,
             audio: Path, audio_source: str = "original") -> dict:
        if game not in DECKS or not chinese.strip():
            raise LexiriseError("This line has no supported game or Mandarin sentence.")
        if not self._lock.acquire(blocking=False):
            raise LexiriseError("Another sentence is being sent. Please try again in a moment.")
        try:
            return self._send(ref, game, chinese.strip(), english, speaker, audio, audio_source)
        finally:
            self._lock.release()

    def _send(self, ref, game, chinese, english, speaker, audio, audio_source):
        deck_id, game_title = DECKS[game]
        key = hashlib.sha256(f"{deck_id}\0{chinese}".encode()).hexdigest()
        with self._connect() as db:
            row = db.execute("SELECT state FROM exports WHERE key=?", (key,)).fetchone()
            state = json.loads(row[0]) if row else {"deck_id": deck_id}
            if state.get("complete"):
                self._save(db, key, ref, state)
                return {"sent": True, "already_sent": True, "deck_id": deck_id}
            if not audio.is_file() or not 0 < audio.stat().st_size <= 25 * 1024 * 1024:
                raise LexiriseError("Voice audio is missing or too large. Wait until the clip is ready.")
            # Read before network work: history pruning may remove the local file
            # while the game continues. No paths or arbitrary URLs come from the browser.
            clip = audio.read_bytes()
            with httpx.Client(base_url=API_BASE, headers={"Authorization": f"Bearer {self._key()}"},
                              timeout=60, follow_redirects=False, transport=self.transport) as client:
                deck = self._request(client, "GET", f"/v1/decks/{deck_id}", params={"limit": 1}).get("deck", {})
                if (deck.get("lang") or deck.get("language")) != "zh" or deck.get("unit_type") != "sentence" or deck.get("deck_type") != "snapshot":
                    raise LexiriseError(f"The {game_title} deck must be a Chinese sentence snapshot deck.")
                if not state.get("audio_url"):
                    result = self._request(client, "POST", "/v1/vocabulary/audio",
                                           files={"file": (f"voice{audio.suffix}", clip, "audio/mpeg" if audio.suffix == ".mp3" else "audio/wav")})
                    url = result.get("publicUrl")
                    if not isinstance(url, str) or not url.startswith("https://"):
                        raise LexiriseError("Lexirise did not return a hosted audio link.")
                    state["audio_url"] = url
                    self._save(db, key, ref, state)
                if not state.get("vocabulary_id"):
                    # Reconcile before creating: a previous request may have succeeded
                    # despite a lost response. Preserve existing study notes/proficiency.
                    item = next((item for item in self._items(client, "/v1/vocabulary", "items", language="zh", mode="sentences", search=chinese)
                                 if item.get("expression_text") == chinese), None)
                    if item:
                        vocabulary_id = item.get("id") or item.get("saved_expression_id")
                        if not vocabulary_id:
                            raise LexiriseError("Lexirise returned a sentence without an item ID.")
                        urls = item.get("audio_urls") or item.get("audioUrls") or []
                        if state["audio_url"] not in urls:
                            self._request(client, "PATCH", f"/v1/vocabulary/{vocabulary_id}", json={"audioUrls": [*urls, state["audio_url"]]})
                    else:
                        payload = {"language": "zh", "text": chinese, "mode": "sentence",
                                   "notes": f"{game_title}{' — ' + speaker if speaker else ''}\nAudio: {audio_source}",
                                   "tags": [game], "audioUrls": [state["audio_url"]]}
                        if english:
                            payload["translation"] = english
                        result = self._request(client, "POST", "/v1/vocabulary", json=payload)
                        item = result.get("item", {})
                        vocabulary_id = item.get("id") or item.get("saved_expression_id")
                        if not vocabulary_id:
                            raise LexiriseError("Lexirise did not return the saved sentence ID. Retry to check it.")
                    state["vocabulary_id"] = int(vocabulary_id)
                    self._save(db, key, ref, state)
                existing = self._deck_contains(
                    client, deck_id, state["vocabulary_id"], chinese
                )
                membership_confirmed = existing
                if not existing:
                    result = self._request(client, "POST", f"/v1/decks/{deck_id}/items", json={
                        "saved_expression_selection": {"mode": "explicit", "ids": [state["vocabulary_id"]]}})
                    membership_confirmed = self._confirmed_add_count(result)
                # Verify membership; a success response alone can contain zero additions.
                # A positive addition count is authoritative. Otherwise read back
                # once, preserving the safety check for a zero-addition response.
                if not membership_confirmed and not self._deck_contains(
                    client, deck_id, state["vocabulary_id"], chinese
                ):
                    raise LexiriseError("Sentence saved, but deck membership is not confirmed. Retry to finish.")
                state["complete"] = True
                self._save(db, key, ref, state)
                return {"sent": True, "already_sent": False, "deck_id": deck_id}
