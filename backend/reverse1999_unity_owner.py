"""Data-only original MonoScript ownership, not a decoder/key trust receipt.

All dependencies are explicitly supplied bytes. Source paths are dictionary
identities, never filesystem paths to open or assemblies/scripts to execute.
"""
from dataclasses import dataclass, field

from .reverse1999_bootstrap import _Reader, _require, asset_index, LIMIT

MAX_FILES = 16
MAX_SOURCE_BYTES = 128 * 1024 * 1024


def _identity(value):
    _require(isinstance(value, str) and 0 < len(value) <= 4096
             and not any(ord(c) < 32 or ord(c) == 127 for c in value), 'Invalid original script-owner identity.')
    # No source-controlled path is opened. Canonical identities still reject
    # ambiguous relative traversal rather than resolving it against host state.
    value = value.replace('\\', '/')
    _require(not value.startswith('/') and ':' not in value
             and all(part not in ('', '.', '..') for part in value.split('/')),
             'Unsupported original script-owner identity.')
    return value


@dataclass(frozen=True)
class MonoBinding:
    asset_name: str
    object_id: int
    instance_name: str
    script_asset: str
    script_object_id: int
    assembly: str
    namespace: str
    class_name: str
    serialized_fields: bytes = field(repr=False)


@dataclass(frozen=True)
class ConfigAssetReference:
    owner: MonoBinding
    encrypted_payload: bytes = field(repr=False)


def mono_bindings(raw, *, asset_name, dependencies):
    """Cross-check both Unity script tables before assigning an owner class."""
    asset_name = _identity(asset_name)
    _require(isinstance(dependencies, dict) and len(dependencies) < MAX_FILES,
             'Original script dependencies exceed their limit.')
    sources = {asset_name: raw}
    for name, data in dependencies.items():
        name = _identity(name)
        _require(name not in sources, 'Duplicate original script-owner identity.')
        sources[name] = data
    _require(all(isinstance(data, bytes) and 48 <= len(data) <= LIMIT for data in sources.values())
             and sum(len(data) for data in sources.values()) <= MAX_SOURCE_BYTES,
             'Original script dependency bytes exceed their limit.')
    indexes = {name: asset_index(data) for name, data in sources.items()}
    by_id = {name: {row.path_id: row for row in index.objects} for name, index in indexes.items()}
    current = indexes[asset_name]
    bindings = []
    for row in current.objects:
        if row.class_id != 114:
            continue
        reader = _Reader(row.data, 16)
        file_id, path_id = reader.number('i'), reader.number('q')
        _require(0 <= row.script_index < len(current.script_references)
                 and current.script_references[row.script_index] == (file_id, path_id),
                 'Original MonoBehaviour and serialized script-table ownership disagree.')
        _require(0 <= file_id <= len(current.external_paths) and path_id != 0,
                 'Original MonoScript reference is missing or outside its owner.')
        owner_name = asset_name if file_id == 0 else _identity(current.external_paths[file_id - 1])
        _require(owner_name in by_id, 'Original MonoScript dependency is missing; supply the publisher owner file.')
        script = by_id[owner_name].get(path_id)
        _require(script is not None and script.class_id == 115,
                 'Original reference does not resolve to a MonoScript object.')
        owner = _Reader(script.data)
        owner.string(4096)  # MonoScript m_Name is not its namespace/class identity.
        owner.number('i'); owner.take(16)  # execution order, properties hash
        class_name = owner.string(4096).decode('utf-8')
        namespace = owner.string(4096).decode('utf-8')
        assembly = owner.string(4096).decode('utf-8')
        _require(owner.position == len(script.data) and class_name and assembly
                 and not any(ord(c) < 32 or ord(c) == 127 for c in class_name + namespace + assembly),
                 'Unsupported original MonoScript owner layout.')
        instance_name = reader.string(4096).decode('utf-8')
        bindings.append(MonoBinding(asset_name, row.path_id, instance_name, owner_name, path_id,
                                    assembly, namespace, class_name, row.data[reader.position:]))
    return tuple(bindings)


def inspect_game_config(raw, *, asset_name='resources.assets', dependencies):
    """Locate the exact authored type, without a fixed instance name/object ID.

    Structural ownership does not authenticate bytes, derive a key, or enable
    preparation. The caller still needs independent publisher integrity proof.
    """
    matches = [owner for owner in mono_bindings(raw, asset_name=asset_name, dependencies=dependencies)
               if (owner.namespace, owner.class_name) == ('SLFramework', 'GameConfigAsset')]
    _require(len(matches) == 1, 'Original GameConfigAsset owner is missing or ambiguous.')
    reader = _Reader(matches[0].serialized_fields)
    payload = reader.take(reader.count(1024 * 1024))
    _require(payload and reader.position == len(reader.raw), 'Unsupported original GameConfigAsset byte-array layout.')
    return ConfigAssetReference(matches[0], payload)
