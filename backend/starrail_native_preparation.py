"""Complete original-native description generation used by Star Rail preparation."""
from dataclasses import dataclass
import json
from pathlib import Path

from . import sophon_assets as sophon, starrail_metadata as metadata
from . import starrail_native_routes as routes, starrail_native_tables as tables
from .starrail_native_index import NativeIndex
from .starrail_original_discovery import _description as route_description
from .starrail_original_tables import _description as table_description
from .runtime_bundle import discover_layout
from .game_tools import _atomic_file

SCHEMA = 'proxy-starrail-original-native-descriptions-v1'
LOGIC = ('starrail_metadata.py', 'starrail_native_index.py', 'starrail_native_routes.py',
         'starrail_native_tables.py', 'starrail_native_description.py', 'starrail_native_preparation.py')


def _logic_identity():
    layout = discover_layout()
    if layout.mode == 'bundle':
        return layout.source_commit
    return metadata._identity({name: metadata._hash(Path(__file__).with_name(name)) for name in LOGIC})


def _validate(value, identity, names):
    metadata._check(isinstance(value, dict) and set(value) == {'schema', 'identity', 'routes', 'tables'}
                    and value['schema'] == SCHEMA and value['identity'] == identity
                    and isinstance(value['tables'], dict) and set(value['tables']) == names)
    route_description(value['routes'])
    metadata._check(value['routes']['native_file_md5'] == identity['native']['identity']['files']['native']['md5'])
    for description in value['tables'].values():
        table_description(description)
    return value


@dataclass(frozen=True)
class Generation:
    native: metadata.Prepared
    routes: dict
    tables: dict
    identity: str


def prepare(directory, build, names):
    """Regenerate every needed description without newer third-party game data.

    Descriptor cache publication happens only after complete native ownership,
    schema and bounds checks. Failure preserves the previous descriptor receipt
    and all complete input/output generations. Request seeds never enter it.
    """
    directory = Path(directory).absolute()
    metadata._check(isinstance(names, (set, frozenset)) and 0 < len(names) <= 256)
    native = metadata.prepare(directory, build)
    identity = {'native': native.receipt, 'logic': _logic_identity(), 'tables': sorted(names)}
    receipt = directory / 'native-descriptions.json'
    try:
        metadata._check(receipt.stat().st_size <= 4 * 1024**2)
        metadata._no_links(receipt)
        value = _validate(json.loads(receipt.read_text()), identity, names)
        return Generation(native, value['routes'], value['tables'], metadata._identity(value))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    index = NativeIndex(native)
    files = sophon.manifest(directory / 'sophon', build['channel'], tuple(build['manifests']['game']), ('.bytes',))
    value = {'schema': SCHEMA, 'identity': identity, 'routes': routes.derive(index, files),
             'tables': tables.descriptions(index, tables.bindings(index, names))}
    # JSON roundtrip normalizes enum number keys before deriving a cache identity.
    value = _validate(json.loads(json.dumps(value)), identity, names)
    _atomic_file(receipt, json.dumps(value, sort_keys=True, separators=(',', ':')).encode())
    return Generation(native, value['routes'], value['tables'], metadata._identity(value))
