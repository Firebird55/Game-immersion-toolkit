from __future__ import annotations

import sqlite3
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import TextMatch, TranscriptLine, is_comic_text_id
from .sqlite_operation_lifetime import SqliteOperationLifetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    game TEXT NOT NULL DEFAULT 'zzz',
    source_ocr TEXT NOT NULL,
    english TEXT NOT NULL,
    chinese TEXT NOT NULL,
    text_id TEXT NOT NULL,
    score REAL NOT NULL,
    match_kind TEXT NOT NULL,
    ambiguous INTEGER NOT NULL DEFAULT 0,
    channel TEXT NOT NULL DEFAULT 'dialogue',
    voiced INTEGER NOT NULL DEFAULT 0,
    audio_path TEXT,
    speaker_english TEXT,
    speaker_chinese TEXT,
    favorite INTEGER NOT NULL DEFAULT 0
)
"""


class TranscriptConnectionCloseError(RuntimeError):
    """Private failed-close ownership; never a store-detach or retry token."""
    def __init__(self, store, connection, body_error, transaction_error, close_error):
        super().__init__('Transcript connection cleanup is unconfirmed.')
        self.store, self.connection = store, connection
        self.body_error, self.transaction_error, self.close_error = body_error, transaction_error, close_error


class TranscriptStorePoisonedError(RuntimeError):
    def __init__(self, failure):
        super().__init__('Transcript store cleanup remains unconfirmed.')
        self.failure = failure


@dataclass(frozen=True, eq=False, repr=False)
class TranscriptConnectionFence:
    """One store's closed operation scopes; no copy or process authority."""
    _store: TranscriptStore
    _epoch: int

    @property
    def _lifetime_subject(self):
        return self._store

    def check(self, store):
        if not isinstance(store, TranscriptStore) or store is not self._store:
            raise ValueError('The transcript connection fence belongs to another store.')
        store._sql_lifetime.check(self)


class TranscriptStore:
    def __init__(self, path: Path):
        self.path = path
        self._sql_lifetime = SqliteOperationLifetime(self, close_error=TranscriptConnectionCloseError,
            poisoned_error=TranscriptStorePoisonedError, fence_type=TranscriptConnectionFence,
            label='Transcript connection')
        self._connection_failures = self._sql_lifetime.failures  # Existing failed-owner observation hook.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection_scope(self):
        with self._sql_lifetime.operation():
            connection = self._connect()  # Keep the existing raw/configurable factory hook.
            with self._sql_lifetime.transaction(connection):
                yield connection

    def freeze_connections(self, timeout):
        """Close this store's admitted operation scopes, not physical handles."""
        return self._sql_lifetime.freeze(timeout)

    def resume_connections(self, fence):
        """Invalidate the exact local token before admitting another operation."""
        self._sql_lifetime.resume(fence)

    def _initialize(self) -> None:
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute("PRAGMA journal_mode=WAL")
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(SCHEMA)
            with self._sql_lifetime.cursor(connection) as statement:
                columns = {row[1] for row in statement.execute("PRAGMA table_info(transcript_lines)")}
            if 'language_context' not in columns:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.execute("ALTER TABLE transcript_lines ADD COLUMN language_context TEXT NOT NULL DEFAULT '{}'")
            if "channel" not in columns:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.execute(
                        "ALTER TABLE transcript_lines ADD COLUMN channel TEXT NOT NULL DEFAULT 'dialogue'"
                    )
            if "game" not in columns:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.execute(
                        "ALTER TABLE transcript_lines ADD COLUMN game TEXT NOT NULL DEFAULT 'zzz'"
                    )
            if "voiced" not in columns:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.execute(
                        "ALTER TABLE transcript_lines ADD COLUMN voiced INTEGER NOT NULL DEFAULT 0"
                    )
            if "audio_path" not in columns:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.execute("ALTER TABLE transcript_lines ADD COLUMN audio_path TEXT")
            if "favorite" not in columns:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.execute(
                        "ALTER TABLE transcript_lines ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0"
                    )
            if "speaker_english" not in columns:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.execute("ALTER TABLE transcript_lines ADD COLUMN speaker_english TEXT")
            if "speaker_chinese" not in columns:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.execute("ALTER TABLE transcript_lines ADD COLUMN speaker_chinese TEXT")
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    "CREATE INDEX IF NOT EXISTS idx_transcript_created_at "
                    "ON transcript_lines(created_at DESC)"
                )
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    "CREATE INDEX IF NOT EXISTS idx_transcript_session_id_created_at "
                    "ON transcript_lines(session_id, created_at DESC)"
                )
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    "CREATE INDEX IF NOT EXISTS idx_transcript_favorites_id "
                    "ON transcript_lines(id DESC) WHERE favorite = 1"
                )
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_hito_identity "
                    "ON transcript_lines(game, text_id) WHERE game = 'hito'"
                )
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute("PRAGMA optimize")

    @staticmethod
    def _row_to_line(row: sqlite3.Row) -> TranscriptLine:
        context = json.loads(row['language_context'])
        # Historic BEYOND fallback rows contained the entire recording. Do not
        # mislabel their cached audio as one page after upgrading the reader.
        if row['game'] == 'beyond' and row['text_id'].endswith(':complete') and row['voiced']:
            context.setdefault('audio_scope', 'paragraph')
        if row['voiced'] and (context.get('dialogue_kind') or '').endswith('_full_track'):
            context['audio_scope'] = 'paragraph'
        return TranscriptLine(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            session_id=row["session_id"],
            game=row["game"],
            source_ocr=row["source_ocr"],
            english=row["english"],
            chinese=row["chinese"],
            text_id=row["text_id"],
            score=row["score"],
            match_kind=row["match_kind"],
            ambiguous=bool(row["ambiguous"]),
            channel=row["channel"],
            voiced=bool(row["voiced"]),
            has_audio=bool(row["audio_path"]),
            audio_source="original" if not row["audio_path"] or row["audio_path"].startswith("official-") else "recording",
            speaker_english=row["speaker_english"],
            speaker_chinese=row["speaker_chinese"],
            favorite=bool(row["favorite"]),
            **context,
        )

    def add(
        self,
        match: TextMatch,
        session_id: str,
        created_at: datetime | None = None,
        channel: str = "dialogue",
    ) -> TranscriptLine:
        timestamp = created_at or datetime.now(timezone.utc).astimezone()
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    """
                INSERT INTO transcript_lines (
                    created_at, session_id, game, source_ocr, english, chinese,
                    text_id, score, match_kind, ambiguous, channel, voiced, audio_path,
                    speaker_english, speaker_chinese, favorite, language_context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        timestamp.isoformat(),
                        session_id,
                        match.game,
                        match.source_ocr,
                        match.english,
                        match.chinese,
                        match.text_id,
                        match.score,
                        match.kind,
                        int(match.ambiguous),
                        channel,
                        0,
                        None,
                        match.speaker_english,
                        match.speaker_chinese,
                        0,
                        json.dumps({key: getattr(match, key) for key in ('source_language', 'source_locale',
                            'source_text', 'translation_locale', 'translation_text', 'audio_locale', 'texts',
                            'voice_status', 'dialogue_kind', 'audio_scope')}, ensure_ascii=False),
                    ),
                )
                row_id = statement.lastrowid
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(
                    "SELECT * FROM transcript_lines WHERE id = ?",
                    (row_id,),
                ).fetchone()
        return self._row_to_line(row)

    @staticmethod
    def _prefix_text(value: str) -> str:
        return "".join(character.casefold() for character in value if character.isalnum())

    def add_or_touch_hito(
        self,
        match: TextMatch,
        session_id: str,
        created_at: datetime | None = None,
        channel: str = "dialogue",
    ) -> TranscriptLine:
        if match.game != "hito":
            raise ValueError("Hito identity handling requires a Hito match")
        timestamp = created_at or datetime.now(timezone.utc).astimezone()
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    """
                INSERT INTO transcript_lines (
                    created_at, session_id, game, source_ocr, english, chinese,
                    text_id, score, match_kind, ambiguous, channel
                ) VALUES (?, ?, 'hito', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game, text_id) WHERE game = 'hito' DO UPDATE SET
                    created_at = excluded.created_at, session_id = excluded.session_id,
                    source_ocr = excluded.source_ocr, english = excluded.english,
                    chinese = excluded.chinese, score = excluded.score,
                    match_kind = excluded.match_kind, ambiguous = excluded.ambiguous,
                    channel = excluded.channel
                """,
                    (
                        timestamp.isoformat(), session_id, match.source_ocr, match.english,
                        match.chinese, match.text_id, match.score, match.kind,
                        int(match.ambiguous), channel,
                    ),
                )
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(
                    "SELECT * FROM transcript_lines WHERE game = 'hito' AND text_id = ?",
                    (match.text_id,),
                ).fetchone()
        return self._row_to_line(row)

    def add_or_upgrade_recent(
        self,
        match: TextMatch,
        session_id: str,
        created_at: datetime | None = None,
        channel: str = "dialogue",
        cooldown_seconds: float = 180.0,
        upgrade_seconds: float = 5.0,
        fragment_seconds: float = 30.0,
        adjacent_seconds: float = 20.0,
    ) -> tuple[TranscriptLine | None, bool]:
        """Store a line, or upgrade a just-captured prefix to its complete form.

        This database check complements the in-memory capture cooldown and keeps
        duplicates out even when two OCR regions race or the companion restarts
        while a subtitle is still visible.
        """
        timestamp = created_at or datetime.now(timezone.utc).astimezone()
        if match.source_locale != 'zh-Hans' or match.audio_scope == 'paragraph':
            with self._connection_scope() as connection:
                with self._sql_lifetime.cursor(connection) as statement:
                    duplicate = statement.execute("""SELECT 1 FROM transcript_lines
                    WHERE game=? AND text_id=? AND json_extract(language_context, '$.source_locale')=?
                    AND json_extract(language_context, '$.source_text')=? AND datetime(created_at)>=datetime(?) LIMIT 1""",
                        (match.game, match.text_id, match.source_locale, match.source_text,
                         (timestamp-timedelta(seconds=max(0.0,cooldown_seconds))).isoformat())).fetchone()
            if duplicate:
                return None, False
            return self.add(match, session_id, created_at=timestamp, channel=channel), False
        cutoff = timestamp - timedelta(seconds=max(0.0, cooldown_seconds))
        is_comic = match.game == "zzz" and channel == "cinematic" and is_comic_text_id(match.text_id)
        with self._connection_scope() as connection:
            adjacent_cutoff = timestamp - timedelta(seconds=max(0.0, adjacent_seconds))
            with self._sql_lifetime.cursor(connection) as statement:
                adjacent = statement.execute(
                    """
                SELECT * FROM transcript_lines
                WHERE game = ? AND COALESCE(json_extract(language_context, '$.source_locale'), 'zh-Hans')='zh-Hans' AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC LIMIT 1
                """,
                    (match.game, adjacent_cutoff.isoformat()),
                ).fetchone()
            if (
                adjacent
                and not (is_comic or self._row_to_line(adjacent).is_comic
                         or self._row_to_line(adjacent).audio_scope == 'paragraph')
                and self._prefix_text(adjacent["english"]) == self._prefix_text(match.english)
            ):
                return None, False

            with self._sql_lifetime.cursor(connection) as statement:
                duplicate = statement.execute(
                    """
                SELECT 1 FROM transcript_lines
                WHERE text_id = ? AND english = ?
                  AND game = ? AND COALESCE(json_extract(language_context, '$.source_locale'), 'zh-Hans')='zh-Hans'
                  AND datetime(created_at) >= datetime(?)
                LIMIT 1
                """,
                    (match.text_id, match.english, match.game, cutoff.isoformat()),
                ).fetchone()
            if duplicate:
                return None, False

            fragment_cutoff = timestamp - timedelta(seconds=max(0.0, fragment_seconds))
            with self._sql_lifetime.cursor(connection) as statement:
                recent_rows = statement.execute(
                    """
                SELECT * FROM transcript_lines
                WHERE game = ? AND COALESCE(json_extract(language_context, '$.source_locale'), 'zh-Hans')='zh-Hans' AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC LIMIT 8
                """,
                    (match.game, fragment_cutoff.isoformat()),
                ).fetchall()
            incoming_text = self._prefix_text(match.english)
            for recent in recent_rows:
                # Each official comic ID is already a complete utterance.
                # Similar wording in another bubble is not an OCR fragment.
                if is_comic or self._row_to_line(recent).is_comic or self._row_to_line(recent).audio_scope == 'paragraph':
                    continue
                recent_text = self._prefix_text(recent["english"])
                if (
                    len(incoming_text) >= 4
                    and len(incoming_text) + 8 <= len(recent_text)
                    and incoming_text in recent_text
                ):
                    return None, False

            upgrade_cutoff = timestamp - timedelta(seconds=max(0.0, upgrade_seconds))
            with self._sql_lifetime.cursor(connection) as statement:
                previous = statement.execute(
                    """
                SELECT * FROM transcript_lines
                WHERE session_id = ? AND game = ? AND COALESCE(json_extract(language_context, '$.source_locale'), 'zh-Hans')='zh-Hans' AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC LIMIT 1
                """,
                    (session_id, match.game, upgrade_cutoff.isoformat()),
                ).fetchone()
            if previous and not (is_comic or self._row_to_line(previous).is_comic
                                 or self._row_to_line(previous).audio_scope == 'paragraph'):
                previous_text = self._prefix_text(previous["english"])
                complete_text = self._prefix_text(match.english)
                is_completion = (
                    len(previous_text) >= 8
                    and len(complete_text) >= len(previous_text) + 10
                    and previous_text in complete_text
                )
                if is_completion:
                    with self._sql_lifetime.cursor(connection) as statement:
                        statement.execute(
                            """
                        UPDATE transcript_lines
                        SET source_ocr = ?, english = ?, chinese = ?, text_id = ?,
                            score = ?, match_kind = ?, ambiguous = ?, channel = ?,
                            speaker_english = ?, speaker_chinese = ?,
                            voiced = 0, audio_path = NULL, language_context = ?
                        WHERE id = ?
                        """,
                            (
                                match.source_ocr,
                                match.english,
                                match.chinese,
                                match.text_id,
                                match.score,
                                match.kind,
                                int(match.ambiguous),
                                channel,
                                match.speaker_english,
                                match.speaker_chinese,
                                json.dumps({key: getattr(match, key) for key in ('source_language', 'source_locale',
                                    'source_text', 'translation_locale', 'translation_text', 'audio_locale', 'texts',
                                    'voice_status', 'dialogue_kind', 'audio_scope')}, ensure_ascii=False),
                                previous["id"],
                            ),
                        )
                    with self._sql_lifetime.cursor(connection) as statement:
                        row = statement.execute(
                            "SELECT * FROM transcript_lines WHERE id = ?", (previous["id"],)
                        ).fetchone()
                    return self._row_to_line(row), True

        return self.add(match, session_id, created_at=timestamp, channel=channel), False

    def get(self, line_id: int) -> TranscriptLine | None:
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(
                    "SELECT * FROM transcript_lines WHERE id = ?", (line_id,)
                ).fetchone()
        return self._row_to_line(row) if row else None

    def update_audio(self, line_id: int, audio_path: str | None, voiced: bool) -> TranscriptLine | None:
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    "UPDATE transcript_lines SET audio_path = ?, voiced = ? WHERE id = ?",
                    (audio_path, int(voiced), line_id),
                )
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(
                    "SELECT * FROM transcript_lines WHERE id = ?", (line_id,)
                ).fetchone()
        return self._row_to_line(row) if row else None

    def set_favorite(self, line_id: int, favorite: bool) -> TranscriptLine | None:
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    "UPDATE transcript_lines SET favorite = ? WHERE id = ?",
                    (int(favorite), line_id),
                )
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(
                    "SELECT * FROM transcript_lines WHERE id = ?", (line_id,)
                ).fetchone()
        return self._row_to_line(row) if row else None

    def update_speaker(
        self,
        line_id: int,
        speaker_english: str | None,
        speaker_chinese: str | None,
    ) -> TranscriptLine | None:
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute(
                    "UPDATE transcript_lines SET speaker_english = ?, speaker_chinese = ? WHERE id = ?",
                    (speaker_english, speaker_chinese, line_id),
                )
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(
                    "SELECT * FROM transcript_lines WHERE id = ?", (line_id,)
                ).fetchone()
        return self._row_to_line(row) if row else None

    def delete(self, line_id: int) -> str | None:
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(
                    "SELECT audio_path FROM transcript_lines WHERE id = ?", (line_id,)
                ).fetchone()
            with self._sql_lifetime.cursor(connection) as statement:
                statement.execute("DELETE FROM transcript_lines WHERE id = ?", (line_id,))
        return str(row["audio_path"]) if row and row["audio_path"] else None

    def prune(self, keep_nonfavorite: int = 50) -> list[tuple[int, str | None]]:
        """Keep favorites plus the newest non-favorites for each supported game."""
        keep_nonfavorite = max(0, keep_nonfavorite)
        with self._connection_scope() as connection:
            rows = []
            with self._sql_lifetime.cursor(connection) as statement:
                games = [row[0] for row in statement.execute("SELECT DISTINCT game FROM transcript_lines")]
            for game in games:
                if game == "hito":
                    continue
                with self._sql_lifetime.cursor(connection) as statement:
                    rows.extend(statement.execute(
                        """
                    SELECT id, audio_path FROM transcript_lines
                    WHERE favorite = 0 AND game = ?
                    ORDER BY id DESC LIMIT -1 OFFSET ?
                    """,
                        (game, keep_nonfavorite),
                    ).fetchall())
            if rows:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.executemany(
                        "DELETE FROM transcript_lines WHERE id = ?",
                        [(row["id"],) for row in rows],
                    )
        return [
            (int(row["id"]), str(row["audio_path"]) if row["audio_path"] else None)
            for row in rows
        ]

    def purge_unvoiced(self) -> list[tuple[int, str | None]]:
        """Keep favorites, confirmed voices and certified unvoiced dialogue."""
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                rows = statement.execute(
                    """
                SELECT * FROM transcript_lines
                WHERE game <> 'hito' AND voiced = 0 AND favorite = 0
                """
                ).fetchall()
            rows = [row for row in rows if not (self._row_to_line(row).is_comic
                                               or self._row_to_line(row).voice_status == 'unvoiced')]
            if rows:
                with self._sql_lifetime.cursor(connection) as statement:
                    statement.executemany(
                        "DELETE FROM transcript_lines WHERE id = ?",
                        [(row["id"],) for row in rows],
                    )
        return [
            (int(row["id"]), str(row["audio_path"]) if row["audio_path"] else None)
            for row in rows
        ]

    def audio_path(self, line_id: int) -> str | None:
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(
                    "SELECT audio_path FROM transcript_lines WHERE id = ?", (line_id,)
                ).fetchone()
        return str(row["audio_path"]) if row and row["audio_path"] else None

    def list(
        self, limit: int = 250, before_id: int | None = None, game: str | None = None
    ) -> list[TranscriptLine]:
        limit = max(1, min(limit, 1000))
        query = "SELECT * FROM transcript_lines"
        parameters: list[object] = []
        conditions: list[str] = []
        if before_id is not None:
            conditions.append("id < ?")
            parameters.append(before_id)
        if game is not None:
            conditions.append("game = ?")
            parameters.append(game)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY julianday(created_at) DESC, id DESC LIMIT ?"
        parameters.append(limit)
        with self._connection_scope() as connection:
            with self._sql_lifetime.cursor(connection) as statement:
                rows = statement.execute(query, parameters).fetchall()
        return [self._row_to_line(row) for row in rows]

    def list_favorites(self, game: str | None = None) -> list[TranscriptLine]:
        """Return every saved favorite, newest first."""
        with self._connection_scope() as connection:
            query = "SELECT * FROM transcript_lines WHERE favorite = 1"
            parameters: list[object] = []
            if game is not None:
                query += " AND game = ?"
                parameters.append(game)
            query += " ORDER BY julianday(created_at) DESC, id DESC"
            with self._sql_lifetime.cursor(connection) as statement:
                rows = statement.execute(query, parameters).fetchall()
        return [self._row_to_line(row) for row in rows]

    def count(self, session_id: str | None = None, game: str | None = None) -> int:
        with self._connection_scope() as connection:
            query = "SELECT COUNT(*) AS total FROM transcript_lines"
            conditions: list[str] = []
            parameters: list[object] = []
            if session_id:
                conditions.append("session_id = ?")
                parameters.append(session_id)
            if game:
                conditions.append("game = ?")
                parameters.append(game)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            with self._sql_lifetime.cursor(connection) as statement:
                row = statement.execute(query, parameters).fetchone()
        return int(row["total"])
