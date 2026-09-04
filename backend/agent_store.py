from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class AgentVoiceStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS agent_lines (
                key TEXT PRIMARY KEY, agent TEXT NOT NULL, asset_id TEXT NOT NULL,
                chinese TEXT NOT NULL, text_source TEXT NOT NULL,
                first_heard TEXT NOT NULL, last_heard TEXT NOT NULL,
                heard_count INTEGER NOT NULL DEFAULT 1,
                UNIQUE(agent, asset_id))''')
            db.execute('CREATE INDEX IF NOT EXISTS idx_agent_lines_recent ON agent_lines(last_heard DESC, key DESC)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_agent_lines_asset ON agent_lines(asset_id)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, agent: str, asset_id: str, chinese: str, now: str | None = None) -> dict:
        now = now or datetime.now(timezone.utc).isoformat()
        key = f'{agent}:{asset_id}'
        with self.connect() as db:
            db.execute('''INSERT INTO agent_lines
                (key,agent,asset_id,chinese,text_source,first_heard,last_heard)
                VALUES (?,?,?,?,'automatic transcription',?,?)
                ON CONFLICT(agent,asset_id) DO UPDATE SET
                last_heard=excluded.last_heard, heard_count=agent_lines.heard_count+1''',
                (key,agent,asset_id,chinese,now,now))
            return dict(db.execute('SELECT * FROM agent_lines WHERE key=?', (key,)).fetchone())

    def list(self, limit=100, offset=0) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM agent_lines ORDER BY last_heard DESC,key DESC LIMIT ? OFFSET ?', (limit, offset))]

    def transcript(self, asset_id: str) -> str | None:
        with self.connect() as db:
            row = db.execute('SELECT chinese FROM agent_lines WHERE asset_id=? LIMIT 1', (asset_id,)).fetchone()
            return row[0] if row else None

    def count(self) -> int:
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM agent_lines').fetchone()[0]

    def has_asset(self, asset_id: str) -> bool:
        return self.transcript(asset_id) is not None

    def assets_for_agent(self, agent: str) -> list[str]:
        with self.connect() as db:
            return [row[0] for row in db.execute('SELECT asset_id FROM agent_lines WHERE agent=?', (agent,))]
