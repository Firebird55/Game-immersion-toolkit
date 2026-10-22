"""Process-local ordering for HTTP snapshots and WebSocket publications.

A request counter only orders requests. This clock orders backend publications;
a snapshot must take its stamp BEFORE reading any payload data.
"""
from __future__ import annotations

import threading
from uuid import uuid4


class StateVersion:
    def __init__(self):
        self.runtime_id = uuid4().hex
        self._revision = 0
        self._lock = threading.RLock()

    def snapshot(self, account_generation: int) -> dict:
        with self._lock:
            return {"runtime_id": self.runtime_id, "state_version": self._revision,
                    "account_generation": account_generation}

    def publish(self, account_generation: int) -> dict:
        with self._lock:
            self._revision += 1
            return self.snapshot(account_generation)
