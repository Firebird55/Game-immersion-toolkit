"""Sanitized exact-byte input attribution, never native or rights approval."""
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit

SHA = re.compile(r'[a-f0-9]{64}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}')
GENERATED = {'ProxyTranscriptRuntime.exe', 'asr/ProxyTranscriptAsr.exe'}


def _require(condition):
    if not condition:
        raise ValueError('Native input attribution needs canonical relative identities and exact hashes.')


def _relative(value):
    from backend.runtime_bundle import RuntimeBundleError, relative_resource
    try:
        result = relative_resource(value)
    except RuntimeBundleError:
        raise ValueError('Native input attribution contains an invalid relative identity.') from None
    _require(not any(ord(c) < 32 for c in result))
    return result


def _sha(value):
    _require(isinstance(value, str) and SHA.fullmatch(value))
    return value


def _label(value):
    _require(isinstance(value, str) and NAME.fullmatch(value))
    return value


def _version(value):
    # Keep PEP 440 local versions and human resource release labels intact.
    # Only bound public text and exclude controls/path spellings, not syntax.
    _require(isinstance(value, str) and 1 <= len(value) <= 240
        and not any(ord(c) < 32 or ord(c) == 127 or c in '/\\:' for c in value))
    return value


def _public_source(value):
    _require(isinstance(value, str) and not any(ord(c) < 32 or ord(c) == 127 for c in value))
    try:
        uri = urlsplit(value)
    except ValueError:
        raise ValueError('Native input attribution contains an invalid public source identity.') from None
    _require(uri.scheme == 'https' and uri.netloc in {'github.com', 'raw.githubusercontent.com', 'pypi.org'}
        and not uri.query and not uri.fragment and re.fullmatch(r'/[A-Za-z0-9._~/-]+', uri.path))
    return value


def native_input_ownership(components, resources, files):
    """Join only verified input records; callers own their byte verification."""
    index = {}
    for component in components:
        name, version = _label(component['name']), _version(component['version'])
        artifact = _sha(component['artifact']['sha256'])
        for entry in component.get('installed_files', []):
            checksum = _sha(entry['sha256'])
            match = {'kind': 'component', 'component': name, 'version': version,
                'artifact_sha256': artifact, 'input_path': _relative(entry['path']), 'input_sha256': checksum}
            if match not in index.setdefault(checksum, []):
                index[checksum].append(match)
    for resource in resources:
        checksum = _sha(resource['sha256'])
        match = {'kind': 'resource', 'version': _version(resource['version']),
            'input_path': _relative(resource['path']), 'input_sha256': checksum,
            'source': _public_source(resource['source'])}
        if match not in index.setdefault(checksum, []):
            index[checksum].append(match)
    records = []
    counts = dict.fromkeys(('exact', 'ambiguous', 'generated', 'unmatched'), 0)
    for entry in sorted(files, key=lambda row: row['path']):
        path = _relative(entry['path'])
        if PurePosixPath(path).suffix.casefold() not in {'.exe', '.dll', '.pyd'}:
            continue
        checksum = _sha(entry['sha256'])
        _require(type(entry['bytes']) is int and entry['bytes'] >= 0)
        matches = sorted(index.get(checksum, []), key=lambda row: (row['kind'], row.get('component', ''),
            row['version'], row['input_path'], row.get('artifact_sha256', '')))
        status = 'ambiguous' if len(matches) > 1 else 'exact' if matches else 'generated' if path in GENERATED else 'unmatched'
        counts[status] += 1
        records.append({'path': path, 'sha256': checksum, 'bytes': entry['bytes'], 'status': status, 'inputs': matches})
    return {'schema': 'proxy-r19-native-input-ownership-v1',
        'scope': 'byte-identical supplier inputs only; generated/transformed code, compiled-in dependencies, loading and rights remain unverified',
        'counts': counts, 'files': records, 'native_closure': 'unverified',
        'rights_review': 'pending-exact-output', 'production_execution_allowed': False}
