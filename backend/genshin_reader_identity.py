"""Fingerprint the Python implementation available to the original-data reader."""
import hashlib
import importlib.util
import marshal
from types import CodeType


SEED_IMPLEMENTATION = (
    'genshin_native_dispatch', 'genshin_native_channel', 'genshin_original_excel', 'genshin_native_x64',
    'genshin_native_metadata', 'genshin_native_expression', 'genshin_native_registration',
    'genshin_native_view', 'genshin_native_usage', 'genshin_native_literals',
)
PROFILE_IMPLEMENTATION = (
    'genshin_original_bootstrap', 'genshin_original_containers', 'genshin_blb_native', 'genshin_blb_body',
    'raw_lz4', 'genshin_blb_portable', 'genshin_native_x64', 'hoyo_bootstrap_assets',
)


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
