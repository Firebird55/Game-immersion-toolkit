from __future__ import annotations

import ctypes
import copy
from contextvars import ContextVar
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx


GAME_TITLES = {"zzz": "Zenless Zone Zero", "pragmata": "PRAGMATA", "wwm": "Where Winds Meet", "cyberpunk": "Cyberpunk 2077",
                  "wuwa": "Wuthering Waves", "witcher3": "The Witcher 3",
                  "nte": "Neverness to Everness", "beyond": "BEYOND: Two Souls", "heavyrain": "HEAVY RAIN"}
GAME_TITLES.update(starrail="Honkai: Star Rail", genshin="Genshin Impact", endfield="Arknights: Endfield")
API_BASE = "https://api.lexirise.app"
REQUEST_KEY = ContextVar('lexirise_request_key', default=None)


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
    def __init__(self, directory: Path, *, transport=None, api_key: str | None = None, accounts=None, source_language: str = "zh"):
        self.accounts = accounts
        self.source_language = source_language
        self._settings_cache = {}
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.db_path = directory / "exports-v2.db"
        self.transport = transport
        self._api_key = api_key
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS exports (key TEXT PRIMARY KEY, state TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS export_refs (ref TEXT PRIMARY KEY, export_key TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS scoped_exports (scope TEXT, key TEXT, state TEXT NOT NULL, PRIMARY KEY(scope,key))")
            db.execute("CREATE TABLE IF NOT EXISTS scoped_export_refs (scope TEXT, ref TEXT, export_key TEXT NOT NULL, PRIMARY KEY(scope,ref))")
            db.execute("CREATE TABLE IF NOT EXISTS game_decks (scope TEXT, game TEXT, deck_id INTEGER, title TEXT, PRIMARY KEY(scope,game))")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _key(self) -> str:
        key = self._api_key or REQUEST_KEY.get() or (self.accounts.active_key() if self.accounts else None) or os.environ.get("LEXIRISE_API_KEY")
        if key:
            return key.strip()
        # A synced project can be used on several Windows PCs, but a DPAPI
        # blob can only be decrypted on the PC/user that created it.
        local_app_data = os.environ.get("LOCALAPPDATA")
        if os.name == "nt" and local_app_data:
            local_key = Path(local_app_data) / "Programs" / "Proxy Transcript" / "key.dpapi"
            if local_key.is_file():
                return _protect(local_key.read_bytes(), decrypt=True).decode()
        try:
            return _protect((self.directory / "key.dpapi").read_bytes(), decrypt=True).decode()
        except OSError:
            raise LexiriseError("Lexirise API key is not configured on this computer.") from None

    def status(self) -> dict:
        try:
            configured = bool(self._key())
        except LexiriseError:
            configured = False
        scope = self._scope() if configured else ''
        with self._connect() as db:
            rows = db.execute("SELECT ref,state FROM scoped_export_refs r JOIN scoped_exports e ON r.scope=e.scope AND r.export_key=e.key WHERE r.scope=?", (scope,)).fetchall()
        decks = self._decks() if configured else {}
        return {"configured": configured, "decks": {game: {"id": value[0], "title": value[1]} for game, value in decks.items()},
                "sent": {ref: json.loads(state)["deck_id"] for ref, state in rows if json.loads(state).get("complete")}}

    def pin(self, source_language: str | None = None):
        """Pin credentials and language before network work or background jobs."""
        from .lexirise_settings import STUDY_LANGUAGES
        session = copy.copy(self)
        session._api_key = self._key()
        session.accounts = None
        session.source_language = source_language or self.source_language
        if session.source_language not in STUDY_LANGUAGES:
            raise LexiriseError('Unsupported study language.')
        session.__dict__.pop('_settings_payload', None)
        session.__dict__.pop('_settings_scope', None)
        cached = self._settings_cache.get(hashlib.sha256(session._api_key.encode()).hexdigest())
        if cached:
            session._settings_payload, session._settings_scope = cached
        return session

    def _scope(self):
        scope = hashlib.sha256(self._key().encode()).hexdigest()
        return scope if self.source_language == 'zh' else scope + ':' + self.source_language

    def _decks(self) -> dict:
        with self._connect() as db:
            rows = db.execute("SELECT game,deck_id,title FROM game_decks WHERE scope=?", (self._scope(),)).fetchall()
        return {game: (deck_id, title) for game, deck_id, title in rows}

    def _client(self):
        return httpx.Client(base_url=API_BASE, headers={"Authorization": f"Bearer {self._key()}"},
                            transport=self.transport, timeout=30, follow_redirects=False)

    def _account(self, client):
        account = self._request(client, "GET", "/v1/me").get("user", {}).get("id")
        if account is None:
            raise LexiriseError("Could not verify deck ownership.")
        return account

    def _owned(self, deck, account):
        return (deck.get("owner_user_id") == account and (deck.get("language") or deck.get("lang")) == self.source_language
                and deck.get("unit_type") == "sentence" and deck.get("deck_type") == "snapshot")

    def available_decks(self):
        with self._client() as client:
            account = self._account(client)
            return [{"id":d["id"],"title":d.get("title", "Untitled deck")} for d in self._items(client, "/v1/decks", "decks", language=self.source_language) if self._owned(d, account)]

    def configure_game_deck(self, game, deck_id=None):
        """Only called by an explicit destination selection or create action."""
        if game not in GAME_TITLES or (deck_id is not None and (type(deck_id) is not int or deck_id <= 0)):
            raise LexiriseError("Choose a supported game and valid deck.")
        with self._lock, self._client() as client, self._connect() as db:
            account = self._account(client)
            if deck_id is None:
                matches=[d for d in self._items(client,"/v1/decks","decks",language=self.source_language) if self._owned(d,account) and d.get("title")==GAME_TITLES[game]]
                if len(matches)>1:
                    raise LexiriseError("Several matching decks exist. Select a destination from the list.")
                deck = matches[0] if matches else self._request(client, "POST", "/v1/decks", json={"title":GAME_TITLES[game],"language":self.source_language,"unit_type":"sentence","deck_type":"snapshot","import_items":[]}).get("deck", {})
                deck_id = deck.get("id")
                if type(deck_id) is not int or deck_id <= 0:
                    raise LexiriseError("Lexirise did not confirm the new deck ID.")
            # Read back even newly created destinations before storing them.
            deck = self._request(client, "GET", f"/v1/decks/{deck_id}", params={"limit":1}).get("deck", {})
            if not self._owned(deck, account):
                raise LexiriseError("Choose your own sentence snapshot deck for the selected study language.")
            title = deck.get("title") or GAME_TITLES[game]
            db.execute("INSERT OR REPLACE INTO game_decks VALUES (?,?,?,?)", (self._scope(),game,deck_id,title))
            return {"id":deck_id,"title":title}

    def ensure_game_decks(self) -> dict:
        """Explicit provisioning only; startup and status never create account data."""
        key = self._key()
        scope = self._scope()
        with self._lock, self._connect() as db, httpx.Client(
                base_url=API_BASE, headers={"Authorization": f"Bearer {key}"},
                transport=self.transport, timeout=30) as client:
            account_id = self._request(client, "GET", "/v1/me").get("user", {}).get("id")
            if account_id is None:
                raise LexiriseError("Could not verify ownership of existing game decks.")
            available = self._request(client, "GET", "/v1/decks", params={"language": self.source_language}).get("decks", [])
            result = {}
            for game, title in GAME_TITLES.items():
                saved = db.execute("SELECT deck_id FROM game_decks WHERE scope=? AND game=?", (scope, game)).fetchone()
                candidates = [d for d in available if d.get("title") == title
                              and d.get("unit_type") == "sentence" and d.get("deck_type") == "snapshot"
                              and (d.get("language") or d.get("lang")) == self.source_language
                              and d.get("owner_user_id") == account_id]
                chosen = next((d for d in candidates if saved and d.get("id") == saved[0]), None)
                if chosen is None:
                    if len(candidates) > 1:
                        raise LexiriseError(f"Several {title} decks already exist; choose a destination before provisioning.")
                    chosen = candidates[0] if candidates else None
                if chosen is None:
                    chosen = self._request(client, "POST", "/v1/decks", json={
                        "title": title, "language": self.source_language, "unit_type": "sentence", "deck_type": "snapshot",
                        "import_items": []}).get("deck", {})
                deck_id = chosen.get("id")
                if not isinstance(deck_id, int) or isinstance(deck_id, bool):
                    raise LexiriseError("Lexirise did not confirm the new deck ID.")
                db.execute("INSERT OR REPLACE INTO game_decks VALUES (?,?,?,?)", (scope, game, deck_id, title))
                db.commit()
                result[game] = {"id": deck_id, "title": title}
            return result

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
        scope = self._scope()
        db.execute("INSERT INTO scoped_exports VALUES (?,?,?) ON CONFLICT(scope,key) DO UPDATE SET state=excluded.state",
                   (scope, key, json.dumps(state)))
        db.execute("INSERT INTO scoped_export_refs VALUES (?,?,?) ON CONFLICT(scope,ref) DO UPDATE SET export_key=excluded.export_key", (scope, ref, key))
        db.commit()

    def send(self, *, ref: str, game: str, chinese: str, english: str, speaker: str,
             audio: Path, audio_source: str = "original") -> dict:
        if game not in GAME_TITLES or not chinese.strip():
            raise LexiriseError("This line has no supported game or study sentence.")
        if not self._lock.acquire(blocking=False):
            raise LexiriseError("Another sentence is being sent. Please try again in a moment.")
        try:
            return self._send(ref, game, chinese.strip(), english, speaker, audio, audio_source)
        finally:
            self._lock.release()

    def _send(self, ref, game, chinese, english, speaker, audio, audio_source):
        decks = self._decks()
        if game not in decks:
            raise LexiriseError("This game's Lexirise deck has not been configured yet.")
        deck_id, game_title = decks[game]
        key = hashlib.sha256(f"{deck_id}\0{chinese}".encode()).hexdigest()
        with self._connect() as db:
            row = db.execute("SELECT state FROM scoped_exports WHERE scope=? AND key=?", (self._scope(),key)).fetchone()
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
                account = self._account(client)
                deck = self._request(client, "GET", f"/v1/decks/{deck_id}", params={"limit": 1}).get("deck", {})
                if (deck.get("lang") or deck.get("language")) != self.source_language or deck.get("unit_type") != "sentence" or deck.get("deck_type") != "snapshot":
                    raise LexiriseError(f"The {game_title} deck must be a sentence snapshot deck for the selected study language.")
                if not self._owned(deck, account):
                    raise LexiriseError("This destination is not owned by the current account. Select your own deck.")
                # Legacy ledger stays intact. Adopt completion only after read-only
                # ownership AND membership checks, never reuse legacy upload URLs.
                legacy = db.execute("SELECT state FROM exports WHERE key=?", (key,)).fetchone()
                old = json.loads(legacy[0]) if legacy else {}
                if old.get("complete") and old.get("vocabulary_id") and self._deck_contains(client, deck_id, old["vocabulary_id"], chinese):
                    self._save(db, key, ref, old)
                    return {"sent":True,"already_sent":True,"deck_id":deck_id}
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
                    item = next((item for item in self._items(client, "/v1/vocabulary", "items", language=self.source_language, mode="sentences", search=chinese)
                                 if item.get("expression_text") == chinese), None)
                    if item:
                        vocabulary_id = item.get("id") or item.get("saved_expression_id")
                        if not vocabulary_id:
                            raise LexiriseError("Lexirise returned a sentence without an item ID.")
                        urls = item.get("audio_urls") or item.get("audioUrls") or []
                        if state["audio_url"] not in urls:
                            self._request(client, "PATCH", f"/v1/vocabulary/{vocabulary_id}", json={"audioUrls": [*urls, state["audio_url"]]})
                    else:
                        payload = {"language": self.source_language, "text": chinese, "mode": "sentence",
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
