"""Lazy use of the shared pure private-cache writer, never desktop tool setup."""


def atomic_bytes(path, raw):
    from .game_data import _write_bytes
    return _write_bytes(path, raw)
