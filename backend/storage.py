from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
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
    ambiguous INTEGER NOT NULL DEFAULT 0
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
        )

    def add(self, match: TextMatch, session_id: str, created_at: datetime | None = None) -> TranscriptLine:
        timestamp = created_at or datetime.now(timezone.utc).astimezone()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO transcript_lines (
                    created_at, session_id, source_ocr, english, chinese,
                    text_id, score, match_kind, ambiguous
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            row = connection.execute(
                "SELECT * FROM transcript_lines WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return self._row_to_line(row)

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
