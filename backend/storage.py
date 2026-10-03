from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import TextMatch, TranscriptLine


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


class TranscriptStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(SCHEMA)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(transcript_lines)")}
            if "channel" not in columns:
                connection.execute(
                    "ALTER TABLE transcript_lines ADD COLUMN channel TEXT NOT NULL DEFAULT 'dialogue'"
                )
            if "game" not in columns:
                connection.execute(
                    "ALTER TABLE transcript_lines ADD COLUMN game TEXT NOT NULL DEFAULT 'zzz'"
                )
            if "voiced" not in columns:
                connection.execute(
                    "ALTER TABLE transcript_lines ADD COLUMN voiced INTEGER NOT NULL DEFAULT 0"
                )
            if "audio_path" not in columns:
                connection.execute("ALTER TABLE transcript_lines ADD COLUMN audio_path TEXT")
            if "favorite" not in columns:
                connection.execute(
                    "ALTER TABLE transcript_lines ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0"
                )
            if "speaker_english" not in columns:
                connection.execute("ALTER TABLE transcript_lines ADD COLUMN speaker_english TEXT")
            if "speaker_chinese" not in columns:
                connection.execute("ALTER TABLE transcript_lines ADD COLUMN speaker_chinese TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_transcript_created_at "
                "ON transcript_lines(created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_transcript_session_id_created_at "
                "ON transcript_lines(session_id, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_transcript_favorites_id "
                "ON transcript_lines(id DESC) WHERE favorite = 1"
            )
            connection.execute("PRAGMA optimize")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_hito_identity "
                "ON transcript_lines(game, text_id) WHERE game = 'hito'"
            )

    @staticmethod
    def _row_to_line(row: sqlite3.Row) -> TranscriptLine:
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
            audio_source="original" if (row["audio_path"] or "").startswith("official-") else "recording",
            speaker_english=row["speaker_english"],
            speaker_chinese=row["speaker_chinese"],
            favorite=bool(row["favorite"]),
        )

    def add(
        self,
        match: TextMatch,
        session_id: str,
        created_at: datetime | None = None,
        channel: str = "dialogue",
    ) -> TranscriptLine:
        timestamp = created_at or datetime.now(timezone.utc).astimezone()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO transcript_lines (
                    created_at, session_id, game, source_ocr, english, chinese,
                    text_id, score, match_kind, ambiguous, channel, voiced, audio_path,
                    speaker_english, speaker_chinese, favorite
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            row = connection.execute(
                "SELECT * FROM transcript_lines WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return self._row_to_line(row)

    @staticmethod
    def _prefix_text(value: str) -> str:
        return "".join(character.casefold() for character in value if character.isalnum())

    def add_or_touch_hito(
        self, match: TextMatch, session_id: str,
        created_at: datetime | None = None, channel: str = "dialogue",
    ) -> TranscriptLine:
        if match.game != "hito":
            raise ValueError("Hito identity handling requires a Hito match")
        timestamp = created_at or datetime.now(timezone.utc).astimezone()
        with self._connect() as connection:
            connection.execute(
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
                    channel = excluded.channel,
                    audio_path = CASE WHEN english = excluded.english THEN audio_path ELSE NULL END,
                    voiced = CASE WHEN english = excluded.english THEN voiced ELSE 0 END
                """,
                (timestamp.isoformat(), session_id, match.source_ocr, match.english,
                 match.chinese, match.text_id, match.score, match.kind,
                 int(match.ambiguous), channel),
            )
            row = connection.execute(
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
        cutoff = timestamp - timedelta(seconds=max(0.0, cooldown_seconds))
        with self._connect() as connection:
            adjacent_cutoff = timestamp - timedelta(seconds=max(0.0, adjacent_seconds))
            adjacent = connection.execute(
                """
                SELECT * FROM transcript_lines
                WHERE game = ? AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC LIMIT 1
                """,
                (match.game, adjacent_cutoff.isoformat()),
            ).fetchone()
            if adjacent and self._prefix_text(adjacent["english"]) == self._prefix_text(
                match.english
            ):
                return None, False

            duplicate = connection.execute(
                """
                SELECT 1 FROM transcript_lines
                WHERE text_id = ? AND english = ?
                  AND game = ?
                  AND datetime(created_at) >= datetime(?)
                LIMIT 1
                """,
                (match.text_id, match.english, match.game, cutoff.isoformat()),
            ).fetchone()
            if duplicate:
                return None, False

            fragment_cutoff = timestamp - timedelta(seconds=max(0.0, fragment_seconds))
            recent_rows = connection.execute(
                """
                SELECT * FROM transcript_lines
                WHERE game = ? AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC LIMIT 8
                """,
                (match.game, fragment_cutoff.isoformat()),
            ).fetchall()
            incoming_text = self._prefix_text(match.english)
            for recent in recent_rows:
                recent_text = self._prefix_text(recent["english"])
                if (
                    len(incoming_text) >= 4
                    and len(incoming_text) + 8 <= len(recent_text)
                    and incoming_text in recent_text
                ):
                    return None, False

            upgrade_cutoff = timestamp - timedelta(seconds=max(0.0, upgrade_seconds))
            previous = connection.execute(
                """
                SELECT * FROM transcript_lines
                WHERE session_id = ? AND game = ? AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC LIMIT 1
                """,
                (session_id, match.game, upgrade_cutoff.isoformat()),
            ).fetchone()
            if previous:
                previous_text = self._prefix_text(previous["english"])
                complete_text = self._prefix_text(match.english)
                is_completion = (
                    len(previous_text) >= 8
                    and len(complete_text) >= len(previous_text) + 10
                    and previous_text in complete_text
                )
                if is_completion:
                    connection.execute(
                        """
                        UPDATE transcript_lines
                        SET source_ocr = ?, english = ?, chinese = ?, text_id = ?,
                            score = ?, match_kind = ?, ambiguous = ?, channel = ?,
                            speaker_english = ?, speaker_chinese = ?,
                            voiced = 0, audio_path = NULL
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
                            previous["id"],
                        ),
                    )
                    row = connection.execute(
                        "SELECT * FROM transcript_lines WHERE id = ?", (previous["id"],)
                    ).fetchone()
                    return self._row_to_line(row), True

        return self.add(match, session_id, created_at=timestamp, channel=channel), False

    def get(self, line_id: int) -> TranscriptLine | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM transcript_lines WHERE id = ?", (line_id,)
            ).fetchone()
        return self._row_to_line(row) if row else None

    def update_audio(self, line_id: int, audio_path: str | None, voiced: bool) -> TranscriptLine | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE transcript_lines SET audio_path = ?, voiced = ? WHERE id = ?",
                (audio_path, int(voiced), line_id),
            )
            row = connection.execute(
                "SELECT * FROM transcript_lines WHERE id = ?", (line_id,)
            ).fetchone()
        return self._row_to_line(row) if row else None

    def set_favorite(self, line_id: int, favorite: bool) -> TranscriptLine | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE transcript_lines SET favorite = ? WHERE id = ?",
                (int(favorite), line_id),
            )
            row = connection.execute(
                "SELECT * FROM transcript_lines WHERE id = ?", (line_id,)
            ).fetchone()
        return self._row_to_line(row) if row else None

    def update_speaker(
        self,
        line_id: int,
        speaker_english: str | None,
        speaker_chinese: str | None,
    ) -> TranscriptLine | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE transcript_lines SET speaker_english = ?, speaker_chinese = ? WHERE id = ?",
                (speaker_english, speaker_chinese, line_id),
            )
            row = connection.execute(
                "SELECT * FROM transcript_lines WHERE id = ?", (line_id,)
            ).fetchone()
        return self._row_to_line(row) if row else None

    def delete(self, line_id: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT audio_path FROM transcript_lines WHERE id = ?", (line_id,)
            ).fetchone()
            connection.execute("DELETE FROM transcript_lines WHERE id = ?", (line_id,))
        return str(row["audio_path"]) if row and row["audio_path"] else None

    def prune(self, keep_nonfavorite: int = 50) -> list[tuple[int, str | None]]:
        """Keep favorites plus the newest non-favorites for each supported game."""
        keep_nonfavorite = max(0, keep_nonfavorite)
        with self._connect() as connection:
            rows = []
            games = [row[0] for row in connection.execute("SELECT DISTINCT game FROM transcript_lines")]
            for game in games:
                # Hito identities must survive beyond the 50-row visible history,
                # so a sentence encountered again next session can reuse its row.
                if game == "hito":
                    continue
                rows.extend(connection.execute(
                    """
                    SELECT id, audio_path FROM transcript_lines
                    WHERE favorite = 0 AND game = ?
                    ORDER BY id DESC LIMIT -1 OFFSET ?
                    """,
                    (game, keep_nonfavorite),
                ).fetchall())
            if rows:
                connection.executemany(
                    "DELETE FROM transcript_lines WHERE id = ?",
                    [(row["id"],) for row in rows],
                )
        return [
            (int(row["id"]), str(row["audio_path"]) if row["audio_path"] else None)
            for row in rows
        ]

    def purge_unvoiced(self) -> list[tuple[int, str | None]]:
        """Remove unconfirmed rows while retaining known voiced cinematic text."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, audio_path FROM transcript_lines
                WHERE game <> 'hito' AND
                    (voiced = 0 OR (audio_path IS NULL AND channel <> 'cinematic'))
                """
            ).fetchall()
            if rows:
                connection.executemany(
                    "DELETE FROM transcript_lines WHERE id = ?",
                    [(row["id"],) for row in rows],
                )
        return [
            (int(row["id"]), str(row["audio_path"]) if row["audio_path"] else None)
            for row in rows
        ]

    def audio_path(self, line_id: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
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
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_line(row) for row in rows]

    def list_favorites(self, game: str | None = None) -> list[TranscriptLine]:
        """Return every saved favorite, newest first."""
        with self._connect() as connection:
            query = "SELECT * FROM transcript_lines WHERE favorite = 1"
            parameters: list[object] = []
            if game is not None:
                query += " AND game = ?"
                parameters.append(game)
            query += " ORDER BY julianday(created_at) DESC, id DESC"
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_line(row) for row in rows]

    def count(self, session_id: str | None = None, game: str | None = None) -> int:
        with self._connect() as connection:
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
            row = connection.execute(query, parameters).fetchone()
        return int(row["total"])
