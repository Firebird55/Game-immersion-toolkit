"""Retain only verified format inputs in the user's protected tool cache."""
import hashlib
import json
from pathlib import Path
import threading
import uuid

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


def _parameter_record(tools):
    try:
        value = json.loads(_read(_path(tools, 'verified-parameters')) or b'null')
        if (not isinstance(value, dict) or type(value.get('schema')) is not int or value['schema'] != 1
                or not isinstance(value.get('parameters'), list) or len(value['parameters']) > 1024):
            return None
        result = tuple(bytes.fromhex(item) for item in value['parameters'])
        owned = value.get('native_parameters', [])
        if not all(len(item) == 32 for item in result) or not isinstance(owned, list) or len(owned) > 1024:
            return None
        native = []
        for item in owned:
            identity = uuid.UUID(item['uuid'])
            parameter = bytes.fromhex(item['parameter'])
            if not identity.int or str(identity) != item['uuid'] or len(parameter) != 32:
                return None
            native.append((identity, parameter))
        defaults = value.get('default_parameters', [])
        if not isinstance(defaults, list) or len(defaults) > 1024:
            return None
        defaults = tuple(bytes.fromhex(item) for item in defaults)
        if any(len(item) != 32 or item not in result for item in defaults):
            return None
        if (set(result) & {parameter for _, parameter in native}) - set(defaults):
            return None
        if len(result) + len(native) > 1024:
            return None
        return result, tuple(native), defaults
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def baseline_parameters(tools):
    record = _parameter_record(tools)
    return record[0] if record is not None else ()


def native_parameters(tools):
    record = _parameter_record(tools)
    return record[1] if record is not None else ()


def default_parameters(tools):
    record = _parameter_record(tools)
    return record[2] if record is not None else ()


def parameters(tools):
    record = _parameter_record(tools)
    return tuple(dict.fromkeys((*record[0], *(value for _, value in record[1])))) if record is not None else ()


def empty_parameter_cache(tools):
    """Distinguish no legacy inputs from a present, unreadable envelope.

    Only absence or an explicitly protected empty baseline permits the native
    UUID-only route after the legacy metadata source becomes unavailable.
    """
    path = _path(tools, 'verified-parameters')
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    record = _parameter_record(tools)
    return record is not None and not record[0]


def remember_parameter(tools, parameter, *, native_guid=None, default_verified=False):
    """Call only after the original encrypted PAK directories passed SHA checks."""
    if not isinstance(parameter, bytes) or len(parameter) != 32:
        return False
    if native_guid is not None and not isinstance(native_guid, uuid.UUID):
        return False
    if type(default_verified) is not bool or native_guid is not None and (not native_guid.int or default_verified):
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
            record = _parameter_record(tools)
            if record is None and not empty_parameter_cache(tools):
                return False  # Never overwrite a present corrupt provenance record.
            baseline, native, defaults = record if record is not None else ((), (), ())
            if (native_guid is None and not default_verified and parameter not in defaults
                    and any(item == parameter for _, item in native)):
                return False  # Equal bytes cannot turn native ownership into a legacy/default proof.
            if (native_guid is None and parameter in baseline and (not default_verified or parameter in defaults)
                    or native_guid is not None and (native_guid, parameter) in native):
                return True
            if native_guid is None:
                baseline = tuple(dict.fromkeys((*baseline, parameter)))
                if default_verified:
                    defaults = tuple(dict.fromkeys((*defaults, parameter)))
            else:
                native = (*native, (native_guid, parameter))
                if parameter not in defaults:
                    baseline = tuple(item for item in baseline if item != parameter)
            if len(baseline) + len(native) > 1024:
                return False
            value = {'schema': 1, 'parameters': [item.hex() for item in baseline],
                     'native_parameters': [{'uuid': str(identity), 'parameter': item.hex()} for identity, item in native],
                     'default_parameters': [item.hex() for item in defaults]}
            if not _write(path, json.dumps(value, separators=(',', ':')).encode()):
                return False
            return _parameter_record(tools) == (baseline, native, defaults)
        finally:
            lock.close()


def format_source(tools, digest):
    raw = _read(_path(tools, 'catalog-format'))
    return raw if raw and hashlib.sha256(raw).hexdigest() == digest else None


def remember_format(tools, raw, digest):
    if len(raw) > 40 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
        return False
    return _write(_path(tools, 'catalog-format'), raw)
