from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from html.parser import HTMLParser
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import httpx
from pypinyin import Style, lazy_pinyin

from .lexirise import API_BASE, LexiriseError, LexiriseService
from .grammar import normalize_grammar
from .lexirise_settings import STUDY_LANGUAGES


ZHUYIN_TONE_MARKS = {1: "", 2: "ˊ", 3: "ˇ", 4: "ˋ", 5: "˙"}


class _DefinitionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items: list[str] = []
        self.inside = False
        self.parts: list[str] = []
        self.headword = ""
        self.in_headword = False
        self.headword_parts: list[str] = []
        self.plain_lines: list[str] = []
        self.plain_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.inside = True
            self.parts = []
        if tag == "div" and dict(attrs).get("data-sc-cccedict") == "headword":
            self.in_headword = True
            self.headword_parts = []

    def handle_endtag(self, tag):
        if tag == "li" and self.inside:
            value = "".join(self.parts).strip()
            if value:
                self.items.append(value)
            self.inside = False
        if tag == "div" and self.in_headword:
            self.headword = "".join(self.headword_parts).strip()
            self.in_headword = False
        if tag in ("p", "div", "br") and not self.inside and not self.in_headword:
            line = " ".join("".join(self.plain_parts).split())
            if line and line != self.headword and line not in self.plain_lines:
                self.plain_lines.append(line)
            self.plain_parts = []

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)
        if self.in_headword:
            self.headword_parts.append(data)
        elif not self.inside:
            self.plain_parts.append(data)


def word_zhuyin(word: str, tones: list[int]) -> str:
    """Use local phonetic spelling with the tones supplied by Lexirise."""
    if not any("\u3400" <= character <= "\u9fff" for character in word):
        return ""
    syllables = lazy_pinyin(word, style=Style.BOPOMOFO)
    if len(syllables) != len(word):
        return ""
    result = []
    for index, syllable in enumerate(syllables):
        base = syllable.rstrip("ˊˇˋ˙")
        tone = tones[index] if index < len(tones) else 0
        result.append(base + ZHUYIN_TONE_MARKS.get(tone, ""))
    return " ".join(result)


class LexiriseReadingService:
    """Analyze transcript words and update explicit learner choices server-side."""

    def __init__(self, directory: Path, lexirise: LexiriseService, *, source_language: str = 'zh', translation_language: str = 'en'):
        if source_language not in STUDY_LANGUAGES:
            raise ValueError('Unsupported source language')
        self.source_language = source_language
        self.translation_language = translation_language
        self.path = directory / "reading-cache-v2.db"
        self.lexirise = lexirise
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lexirise-gloss")
        self.pending_meanings: set[str] = set()
        directory.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (kind TEXT, key TEXT, value TEXT, at REAL, PRIMARY KEY(kind,key))")
            db.execute("CREATE TABLE IF NOT EXISTS grammar_choices (slug TEXT PRIMARY KEY, proficiency INTEGER NOT NULL CHECK(proficiency IN (0,4)))")

    def _scope(self, kind: str) -> str:
        account = hashlib.sha256(self.lexirise._key().encode()).hexdigest()
        settings = getattr(self.lexirise, '_settings_scope', 'unloaded')
        return f'{account}:{self.source_language}:{self.translation_language}:{settings}:{kind}'

    def _cached(self, kind: str, key: str, max_age: float):
        kind = self._scope(kind)
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT value,at FROM cache WHERE kind=? AND key=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row and time.time() - row[1] < max_age else None

    def _save(self, kind: str, key: str, value: dict):
        kind = self._scope(kind)
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)", (kind, key, json.dumps(value), time.time()))

    def _post(self, path: str, payload: dict, timeout: float = 25) -> dict:
        with httpx.Client(base_url=API_BASE, headers={"Authorization": f"Bearer {self.lexirise._key()}"},
                          timeout=timeout, follow_redirects=False, transport=self.lexirise.transport) as client:
            return LexiriseService._request(client, "POST", path, json=payload)

    def _patch(self, path: str, payload: dict) -> dict:
        with httpx.Client(base_url=API_BASE, headers={"Authorization": f"Bearer {self.lexirise._key()}"},
                          timeout=25, follow_redirects=False, transport=self.lexirise.transport) as client:
            return LexiriseService._request(client, "PATCH", path, json=payload)

    def _translations(self, response: dict) -> list[dict]:
        items = [item for item in response.get("translations") or [] if isinstance(item, dict) and isinstance(item.get("translation"), str) and item["translation"].strip()]
        preferred = [item for item in items if item.get("target_lang") == self.translation_language]
        return preferred

    def _meaning(self, word: str) -> str:
        cached = self._cached("meaning", word, 30 * 86400)
        if cached is not None:
            return cached.get("meaning", "")
        if self._cached("meaning-pending", word, 60) is not None:
            return ""
        result = self._post("/v1/dictionary/lookup", {"text": word, "language": self.source_language})
        translations = self._translations(result)
        meaning = translations[0]["translation"] if translations else ""
        self._save("meaning" if meaning else "meaning-pending", word, {"meaning": meaning})
        return meaning

    def _finish_meaning(self, word: str, future: Future) -> None:
        try:
            future.result()
        except Exception:
            # A failed dictionary lookup must not delay sentence analysis or
            # start another request on every browser refresh.
            self._save("meaning-pending", word, {"meaning": ""})
        finally:
            with self.lock:
                self.pending_meanings.discard(word)

    def _schedule_meaning(self, word: str) -> bool:
        if self._cached("meaning-pending", word, 60) is not None:
            return False
        with self.lock:
            if word in self.pending_meanings:
                return True
            self.pending_meanings.add(word)
            future = self.pool.submit(self._meaning, word)
            future.add_done_callback(lambda completed: self._finish_meaning(word, completed))
            return True

    def analyze(self, text: str) -> dict:
        if not text.strip() or len(text) > 1600:
            raise LexiriseError("This sentence is too long for Lexirise reading analysis.")
        result = self._cached("analysis-full", text, 10 * 60)
        if result and result.get("morphoPending") and self._cached("analysis-full", text, 1) is None:
            result = None
        if result is None:
            result = self._post("/v1/analyze/text", {"text": text, "language": self.source_language, "fast": False})
            self._save("analysis-full", text, result)
        states = result.get("stateByEntryId") or {}
        entry_meta = result.get("entryMetaById") or {}
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
            override = self._cached("state", str(entry_id), 10 * 60) if isinstance(entry_id, int) else None
            if override is not None:
                state = override
            meta = entry_meta.get(str(entry_id), {}) if entry_id is not None else {}
            if not isinstance(meta, dict):
                meta = {}
            proficiency = state.get("proficiency", 0) if isinstance(state, dict) else 0
            if not isinstance(proficiency, int) or proficiency not in range(5):
                proficiency = 0
            raw_tones = item.get("tones") or meta.get("tones") or []
            tones = [tone if isinstance(tone, int) and tone in range(1, 7 if self.source_language == 'yue' else 6) else 0
                     for tone in raw_tones] if isinstance(raw_tones, list) else []
            gloss = meta.get("gloss") if isinstance(meta.get("gloss"), str) else ""
            tokens.append({"start": start, "end": end, "word": word,
                           "entryId": entry_id if isinstance(entry_id, int) else None,
                           "savedExpressionId": state.get("saved_expression_id") if isinstance(state, dict) else None,
                           "pinyin": item.get("transliteration") or meta.get("transliteration") or "",
                           "zhuyin": word_zhuyin(word, tones) if self.source_language == "zh" else "", "tones": tones,
                           "proficiency": proficiency, "meaning": gloss})
            last_end = end
        unknown = list(dict.fromkeys(token["word"] for token in tokens
                                     if token["proficiency"] < 4 and not token["meaning"]))
        meanings = {}
        pending = False
        for word in unknown:
            saved = self._cached("meaning", word, 30 * 86400)
            if saved is not None:
                meanings[word] = saved.get("meaning", "")
            else:
                pending = self._schedule_meaning(word) or pending
        for token in tokens:
            token["meaning"] = token["meaning"] or meanings.get(token["word"], "")
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            grammar_choices = {slug.rsplit(":", 1)[-1]: level for slug, level in db.execute("SELECT slug,proficiency FROM grammar_choices")
                               if slug.startswith(self.lexirise._scope() + ":" + self.source_language + ":")}
        return {"text": text, "tokens": tokens, "pendingMeanings": pending,
                "analysisPending": bool(result.get("morphoPending")),
                "grammar": normalize_grammar(text, result, grammar_choices)}

    def set_grammar_known(self, text: str, slug: str, known: bool) -> dict | None:
        # Preserve the existing app-local grammar override. Remote grammar state
        # writes are a separate API operation, not implied by this local control.
        rule = next((rule for rule in self.analyze(text)["grammar"] if rule["slug"] == slug), None)
        if rule is None:
            return None
        proficiency = 4 if known else 0
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO grammar_choices VALUES (?,?)", (self.lexirise._scope() + ":" + self.source_language + ":" + slug, proficiency))
        return {"slug": slug, "proficiency": proficiency, "localOverride": True}

    def lookup(self, text: str, start: int) -> dict | None:
        """Look up one token from an official saved line after a user presses it."""
        token = next((item for item in self.analyze(text)["tokens"] if item["start"] == start), None)
        if token is None:
            return None
        word = token["word"]
        cached = self._cached("lookup-v4", word, 30 * 86400)
        if cached is None:
            response = self._post("/v1/dictionary/lookup", {"text": word, "language": self.source_language})
            translations = []
            all_examples = []
            example_texts = set()
            for item in self._translations(response):
                if not isinstance(item, dict):
                    continue
                meaning = item.get("translation")
                if not isinstance(meaning, str) or not meaning.strip():
                    continue
                examples = []
                for example in (item.get("examples") or [])[:6]:
                    if not isinstance(example, dict) or not isinstance(example.get("text"), str):
                        continue
                    entry = {"text": example["text"], "translation": example.get("translation") or ""}
                    examples.append(entry)
                    if entry["text"] not in example_texts:
                        example_texts.add(entry["text"])
                        all_examples.append(entry)
                pos = item.get("part_of_speech") or []
                translations.append({"meaning": meaning.strip(), "examples": examples,
                                     "partOfSpeech": [value for value in pos if isinstance(value, str)] if isinstance(pos, list) else []})
            dictionaries = []
            for entry in response.get("supplementalEntries") or []:
                if not isinstance(entry, dict):
                    continue
                parser = _DefinitionParser()
                parser.feed(entry.get("html") if isinstance(entry.get("html"), str) else "")
                dictionaries.append({"name": entry.get("dictionary_name", "Dictionary"),
                                     "headword": parser.headword or entry.get("headword", ""), "reading": entry.get("reading", ""),
                                     "definitions": parser.items or parser.plain_lines})
            character = response.get("characterInfo")
            if not isinstance(character, dict):
                character = {}
            if len(word) == 1 and character:
                self._save("character", word, character)
            components = [{"character": part.get("character", ""),
                           "type": [value for value in part.get("type", []) if isinstance(value, str)]
                           if isinstance(part.get("type"), list) else [],
                           "hint": part.get("hint", "")}
                          for part in character.get("components") or [] if isinstance(part, dict)]
            stats = character.get("statistics") if isinstance(character.get("statistics"), dict) else {}
            tags = response.get("system_tags") or []
            hsk = stats.get("hskLevel") or next((int(tag[4:]) for tag in tags
                if isinstance(tag, str) and tag.startswith("HSK-") and tag[4:].isdigit()), None)
            alternate = response.get("multipleReadings") or {}
            cached = {"sourceLanguage": self.source_language,
                      "translationLanguage": self._translations(response)[0].get("target_lang") if self._translations(response) else self.translation_language,
                      "translations": translations, "examples": all_examples[:8],
                      "dictionaries": dictionaries,
                      "hskLevel": hsk, "rank": response.get("rank"),
                      "frequencyScore": response.get("frequency_score"),
                      "alternateReadings": alternate.get("alternatives") or [] if isinstance(alternate, dict) else [],
                      "components": components, "characterHint": character.get("hint", ""),
                      "strokeCount": character.get("strokeCount"),
                      "character": character.get("char", ""),
                      "topWords": [{"word": item["word"], "trad": item.get("trad", ""),
                                    "gloss": item.get("gloss", ""), "share": item.get("share")}
                                   for item in (character.get("statistics") or {}).get("topWords", [])
                                   if isinstance(item, dict) and isinstance(item.get("word"), str)]}
            self._save("lookup-v4", word, cached)
        return {"word": word, "pinyin": token["pinyin"], "zhuyin": token["zhuyin"],
                "tones": token["tones"], "proficiency": token["proficiency"],
                "meaning": token["meaning"], **cached}

    def context(self, text: str, start: int, question: str | None = None) -> dict | None:
        token = next((item for item in self.analyze(text)["tokens"] if item["start"] == start), None)
        if token is None:
            return None
        key = f"{text}:{start}:{question or ''}"
        cached = self._cached("context", key, 30 * 86400)
        if not cached or not cached.get("meaning"):
            payload = {"language": self.source_language, "text": text,
                       "charStart": token["start"], "charEnd": token["end"]}
            if question:
                payload["question"] = question
            response = self._post("/v1/analyze/context", payload, timeout=120)
            cached = {name: response.get(name) or "" for name in ("meaning", "conciseMeaning", "reading")}
            if not isinstance(cached["meaning"], str) or not cached["meaning"].strip():
                raise LexiriseError("Lexirise returned no answer. Please ask again.")
            self._save("context", key, cached)
        return cached

    def notes(self, text: str, start: int) -> dict | None:
        token = next((item for item in self.analyze(text)["tokens"] if item["start"] == start), None)
        if token is None:
            return None
        saved_id = token.get("savedExpressionId")
        if not isinstance(saved_id, int) or saved_id <= 0:
            return {"notes": ""}
        with httpx.Client(base_url=API_BASE, headers={"Authorization": f"Bearer {self.lexirise._key()}"},
                          timeout=25, follow_redirects=False, transport=self.lexirise.transport) as client:
            result = LexiriseService._request(client, "GET", f"/v1/vocabulary/{saved_id}")
        return {"notes": result.get("notes") if isinstance(result.get("notes"), str) else ""}

    def characters(self, text: str, start: int) -> dict | None:
        token = next((item for item in self.analyze(text)["tokens"] if item["start"] == start), None)
        if token is None:
            return None
        letters = [char for char in dict.fromkeys(token["word"])
                   if "\u3400" <= char <= "\u9fff"][:8]
        cached_info = {char: self._cached("character", char, 30 * 86400) for char in letters}
        pending = {char: self.pool.submit(self._post, "/v1/dictionary/lookup",
                   {"text": char, "language": self.source_language}) for char in letters if cached_info[char] is None}
        characters = []
        partial = False
        failed: set[str] = set()
        for char in letters:
            info = cached_info[char]
            if info is None:
                try:
                    response = pending[char].result()
                    raw = response.get("characterInfo")
                    info = raw if isinstance(raw, dict) else {}
                    self._save("character", char, info)
                except LexiriseError:
                    info = {}
                    partial = True
                    failed.add(char)
            components = [{"character": part.get("character", ""),
                           "type": [value for value in part.get("type", []) if isinstance(value, str)]
                           if isinstance(part.get("type"), list) else [],
                           "hint": part.get("hint", "")}
                          for part in info.get("components") or [] if isinstance(part, dict)]
            characters.append({"character": char, "hint": info.get("hint", ""),
                               "strokeCount": info.get("strokeCount"), "components": components,
                               "pinyin": info.get("pinyin") or [], "gloss": info.get("gloss") or "",
                               "unavailable": char in failed})
        # Fetch only direct Chinese components, without recursively expanding
        # their components. Definitions can render before this enrichment.
        component_letters = list(dict.fromkeys(part["character"] for character in characters
            for part in character["components"] if isinstance(part["character"], str)
            and len(part["character"]) == 1 and "\u3400" <= part["character"] <= "\u9fff"))
        component_info = {char: self._cached("character", char, 30 * 86400) for char in component_letters}
        component_pending = {char: self.pool.submit(self._post, "/v1/dictionary/lookup",
            {"text": char, "language": self.source_language}) for char in component_letters if component_info[char] is None}
        for char, future in component_pending.items():
            try:
                response = future.result()
                raw = response.get("characterInfo")
                component_info[char] = raw if isinstance(raw, dict) else {}
                self._save("character", char, component_info[char])
            except LexiriseError:
                partial = True
        for character in characters:
            for part in character["components"]:
                info = component_info.get(part["character"]) or {}
                raw_pinyin = info.get("pinyin")
                part["pinyin"] = [value for value in raw_pinyin if isinstance(value, str)] if isinstance(raw_pinyin, list) else []
                part["gloss"] = info.get("gloss") or ""
                part["characterHint"] = info.get("hint") or ""
        return {"characters": characters, "partial": partial}

    def examples(self, text: str, start: int) -> dict | None:
        details = self.lookup(text, start)
        if details is None:
            return None
        examples = details.get("examples") or []
        pending = {index: self.pool.submit(self.analyze, item["text"])
                   for index, item in enumerate(examples[:5])}
        result = []
        for index, item in enumerate(examples[:5]):
            try:
                reading = pending[index].result()
                tokens = reading["tokens"]
            except (LexiriseError, ValueError):
                tokens = []
            result.append({**item, "tokens": tokens})
        return {"examples": result}

    def save_example(self, text: str, start: int, example_index: int) -> dict | None:
        details = self.lookup(text, start)
        if details is None:
            return None
        examples = details.get("examples") or []
        if not 0 <= example_index < len(examples):
            return None
        example = examples[example_index]
        payload = {"language": self.source_language, "text": example["text"], "mode": "sentence"}
        if example.get("translation"):
            payload["translation"] = example["translation"]
        response = self._post("/v1/vocabulary", payload)
        item = response.get("item") if isinstance(response.get("item"), dict) else response
        saved_id = item.get("id") or item.get("saved_expression_id")
        if not isinstance(saved_id, int) or saved_id <= 0:
            raise LexiriseError("Lexirise did not confirm this example was saved. Try again.")
        return {"saved": True, "savedExpressionId": saved_id}

    def similar(self, text: str, start: int) -> dict | None:
        token = next((item for item in self.analyze(text)["tokens"] if item["start"] == start), None)
        if token is None:
            return None
        key = f"{text}:{start}"
        cached = self._cached("similar", key, 7 * 86400)
        if cached is not None:
            return cached
        question = (f"Suggest exactly three close {self.source_language} alternatives to {token['word']} in this context. "
                    f"For each, give the source-language word, short {self.translation_language} meaning, and one short usage distinction. "
                    "Use one line per alternative, formatted WORD | MEANING | USAGE. No introduction or markdown.")
        response = self._post("/v1/analyze/context", {"language": self.source_language, "text": text,
            "charStart": token["start"], "charEnd": token["end"], "question": question}, timeout=60)
        suggestions = []
        for line in (response.get("meaning") or "").splitlines():
            clean = line.strip().lstrip("-• ")
            match = re.match(r"(?:\*\*)?([^|\n]{1,80}?)(?:\*\*)?\s*(?:\||[—–-])\s*(.+)", clean)
            if not match:
                continue
            word, rest = match.groups()
            if word == token["word"] or word in (item["word"] for item in suggestions):
                continue
            parts = [part.strip() for part in rest.split("|", 1)]
            suggestions.append({"word": word, "meaning": parts[0],
                                "usage": parts[1] if len(parts) > 1 else ""})
            if len(suggestions) == 4:
                break
        pending = {item["word"]: self.pool.submit(self._post, "/v1/dictionary/lookup",
                   {"text": item["word"], "language": self.source_language}) for item in suggestions}
        confirmed = []
        for item in suggestions:
            try:
                dictionary = pending[item["word"]].result()
            except LexiriseError:
                continue
            if dictionary.get("word") != item["word"] or not dictionary.get("entry_id"):
                continue
            translations = [entry.get("translation") for entry in dictionary.get("translations") or []
                            if isinstance(entry, dict) and entry.get("target_lang") == self.translation_language
                            and isinstance(entry.get("translation"), str)]
            confirmed.append({**item, "meaning": translations[0] if translations else item["meaning"],
                              "pinyin": dictionary.get("transliteration") or "",
                              "tones": dictionary.get("tones") or []})
        result = {"suggestions": confirmed, "generated": True}
        if confirmed:
            self._save("similar", key, result)
        return result

    def set_proficiency(self, text: str, start: int, proficiency: int) -> dict | None:
        if proficiency not in (1, 2, 3, 4):
            raise ValueError("Invalid proficiency")
        token = next((item for item in self.analyze(text)["tokens"] if item["start"] == start), None)
        if token is None or not isinstance(token["entryId"], int):
            return None
        saved_id = token.get("savedExpressionId")
        if isinstance(saved_id, int) and saved_id > 0:
            response = self._patch(f"/v1/vocabulary/{saved_id}", {"proficiency": proficiency})
        else:
            response = self._post("/v1/vocabulary", {"language": self.source_language, "text": token["word"],
                "mode": "word", "proficiency": proficiency})
            item = response.get("item") if isinstance(response.get("item"), dict) else response
            saved_id = item.get("saved_expression_id") or item.get("id")
        state = {"proficiency": proficiency, "saved_expression_id": saved_id}
        self._save("state", str(token["entryId"]), state)
        return {"word": token["word"], "entryId": token["entryId"],
                "proficiency": proficiency, "savedExpressionId": saved_id}
