"""Fingerprint the Python implementation available to the original-data reader."""
import hashlib
import importlib.util
import marshal
from types import CodeType


def implementation_identity(names):
    result = hashlib.sha256()
    for name in names:
        module = 'backend.' + name
        try:
            spec = importlib.util.find_spec(module)
            code = spec.loader.get_code(module) if spec is not None and hasattr(spec.loader, 'get_code') else None
        except (ImportError, OSError, SyntaxError, TypeError) as error:
            raise ValueError('The original Genshin reader code is unavailable.') from error
        if not isinstance(code, CodeType):
            raise ValueError('The original Genshin reader code is unavailable.')
        result.update(name.encode())
        result.update(marshal.dumps(code))
    return result.hexdigest()
