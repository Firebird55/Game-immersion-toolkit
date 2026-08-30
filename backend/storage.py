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
    source_ocr TEXT NOT NULL,
    english TEXT NOT NULL,
    chinese TEXT NOT NULL,
    text_id TEXT NOT NULL,
    score REAL NOT NULL,
    match_kind TEXT NOT NULL,
    ambiguous INTEGER NOT NULL DEFAULT 0,
    channel TEXT NOT NULL DEFAULT 'dialogue',
    voiced INTEGER NOT NULL DEFAULT 0,
    audio_path TEXT
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
            if "voiced" not in columns:
                connection.execute(
                    "ALTER TABLE transcript_lines ADD COLUMN voiced INTEGER NOT NULL DEFAULT 0"
                )
            if "audio_path" not in columns:
                connection.execute("ALTER TABLE transcript_lines ADD COLUMN audio_path TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_transcript_created_at "
                "ON transcript_lines(created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_transcript_session_id_created_at "
                "ON transcript_lines(session_id, created_at DESC)"
            )
            connection.execute("PRAGMA optimize")

    @staticmethod
    def _row_to_line(row: sqlite3.Row) -> TranscriptLine:
        return TranscriptLine(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            session_id=row["session_id"],
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
                    created_at, session_id, source_ocr, english, chinese,
                    text_id, score, match_kind, ambiguous, channel, voiced, audio_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp.isoformat(),
                    session_id,
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

    def add_or_upgrade_recent(
        self,
        match: TextMatch,
        session_id: str,
        created_at: datetime | None = None,
        channel: str = "dialogue",
        cooldown_seconds: float = 180.0,
        upgrade_seconds: float = 5.0,
        fragment_seconds: float = 30.0,
    ) -> tuple[TranscriptLine | None, bool]:
        """Store a line, or upgrade a just-captured prefix to its complete form.

        This database check complements the in-memory capture cooldown and keeps
        duplicates out even when two OCR regions race or the companion restarts
        while a subtitle is still visible.
        """
        timestamp = created_at or datetime.now(timezone.utc).astimezone()
        cutoff = timestamp - timedelta(seconds=max(0.0, cooldown_seconds))
        with self._connect() as connection:
            duplicate = connection.execute(
                """
                SELECT 1 FROM transcript_lines
                WHERE text_id = ? AND english = ?
                  AND datetime(created_at) >= datetime(?)
                LIMIT 1
                """,
                (match.text_id, match.english, cutoff.isoformat()),
            ).fetchone()
            if duplicate:
                return None, False

            fragment_cutoff = timestamp - timedelta(seconds=max(0.0, fragment_seconds))
            recent_rows = connection.execute(
                """
                SELECT * FROM transcript_lines
                WHERE session_id = ? AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC LIMIT 8
                """,
                (session_id, fragment_cutoff.isoformat()),
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
                WHERE session_id = ? AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC LIMIT 1
                """,
                (session_id, upgrade_cutoff.isoformat()),
            ).fetchone()
            if previous:
                previous_text = self._prefix_text(previous["english"])
                complete_text = self._prefix_text(match.english)
                is_completion = (
                    len(previous_text) >= 15
                    and len(complete_text) >= len(previous_text) + 10
                    and complete_text.startswith(previous_text)
                )
                if is_completion:
                    connection.execute(
                        """
                        UPDATE transcript_lines
                        SET source_ocr = ?, english = ?, chinese = ?, text_id = ?,
                            score = ?, match_kind = ?, ambiguous = ?, channel = ?,
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

    def audio_path(self, line_id: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT audio_path FROM transcript_lines WHERE id = ?", (line_id,)
            ).fetchone()
        return str(row["audio_path"]) if row and row["audio_path"] else None

    def list(self, limit: int = 250, before_id: int | None = None) -> list[TranscriptLine]:
        limit = max(1, min(limit, 1000))
        query = "SELECT * FROM transcript_lines"
        parameters: list[object] = []
        if before_id is not None:
            query += " WHERE id < ?"
            parameters.append(before_id)
        query += " ORDER BY id DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_line(row) for row in rows]

    def count(self, session_id: str | None = None) -> int:
        with self._connect() as connection:
            if session_id:
                row = connection.execute(
                    "SELECT COUNT(*) AS total FROM transcript_lines WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            else:
                row = connection.execute("SELECT COUNT(*) AS total FROM transcript_lines").fetchone()
        return int(row["total"])
