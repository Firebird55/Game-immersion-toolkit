"""Retain only verified format inputs in the user's protected tool cache."""
import hashlib
import json
from pathlib import Path
import threading

from .export_lock import ExportLock

_GATE = threading.Lock()
_LIMIT = 128 * 1024


def _path(tools, name):
    return Path(tools).resolve() / 'wuwa-publisher' / (name + '.dpapi')


def _read(path):
    from .lexirise import _protect
    try:
        if not path.is_file() or path.stat().st_size > _LIMIT:
            return None
        value = _protect(path.read_bytes(), decrypt=True)
        return value if len(value) <= _LIMIT else None
    except Exception:
        # A different host/user or a corrupt envelope cannot authorize metadata.
        return None


def _write(path, data):
    from .lexirise import _protect
    from .protected_storage import private_write
    try:
        protected = _protect(data)
        if len(protected) > _LIMIT:
            return False
        private_write(path, protected)
        return True
    except Exception:
        # Optional recovery state must never destroy a valid prepared snapshot.
        return False


def parameters(tools):
    try:
        value = json.loads(_read(_path(tools, 'verified-parameters')) or b'null')
        if (not isinstance(value, dict) or value.get('schema') != 1
                or not isinstance(value.get('parameters'), list) or len(value['parameters']) > 1024):
            return ()
        result = tuple(bytes.fromhex(item) for item in value['parameters'])
        return result if all(len(item) == 32 for item in result) else ()
    except (ValueError, TypeError):
        return ()


def remember_parameter(tools, parameter):
    """Call only after the original encrypted PAK directories passed SHA checks."""
    if not isinstance(parameter, bytes) or len(parameter) != 32:
        return False
    path = _path(tools, 'verified-parameters')
    with _GATE:
        lock = ExportLock(path.with_suffix('.lock'))
        try:
            acquired = lock.acquire()
        except OSError:
            return False
        if not acquired:
            return False
        try:
            previous = parameters(tools)
            if parameter in previous:
                return True
            if len(previous) >= 1024:
                return False
            value = {'schema': 1, 'parameters': [item.hex() for item in (*previous, parameter)]}
            return _write(path, json.dumps(value, separators=(',', ':')).encode())
        finally:
            lock.close()


def format_source(tools, digest):
    raw = _read(_path(tools, 'catalog-format'))
    return raw if raw and hashlib.sha256(raw).hexdigest() == digest else None


def remember_format(tools, raw, digest):
    if len(raw) > 40 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
        return False
    return _write(_path(tools, 'catalog-format'), raw)
