"""Retrievable original provenance for a frozen native format baseline.

This is an original publisher resource identity, not a bundled client or a new
third-party description per game update. Files are never loaded as executable
code. Publisher preparation verifies this baseline before required-schema checks.
"""
from dataclasses import dataclass, field
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

from . import nte_native_metadata as metadata, nte_release as release
from .game_tools import _atomic_file
from .nte_native_schema import _check

BASELINE = {
    'region': 'nte-global', 'branch': 'PC_140', 'version': '1.4.9',
    'manifest_url': 'https://ntecdn1.perfectworld.com/clientRes/PC_140/Version/Windows/version/1.4.9/ResList.bin.zip',
    'manifest_sha256': '900a04e2f9f75b4e970f6d76d033a942b4ab8f559d770409c0901ed3333f949e',
    'inventory_sha256': 'afe8b6622e2cb58470061b0bbe25f0b93d9a99d5de6e112a4db5a61a66725fa6',
    'xml_md5': 'ede1d11136e3a02e1923c4198af58461',
    'native_md5': '0738829127eb7547245a60d6be7bb6f9', 'native_size': 273277288,
    'native_sha256': 'a575f2685526dc69e33e289a334c9ba638c27e5dc9c0f4c243e1d338c57e2ff4',
}


@dataclass(frozen=True)
class AuthenticatedNative:
    data: bytes = field(repr=False)
    identity: dict


def discover(cache, *, fetch=None, parameters=None):
    """Authenticate the original baseline inventory without acquiring a PE.

    A cold installation-free cache reads only the small original resource list.
    Existing research paths, game folders and current community indices are not
    inputs. The original entry is selected by fixed publisher identity, never
    by executable or project filename. Selected native acquisition is separate
    and retains its exact publisher package range.
    """
    cache = Path(cache)
    reference = BASELINE
    manifest = cache / (reference['manifest_sha256'] + '.manifest.zip')
    if manifest.exists():
        _check(manifest.is_file() and manifest.stat().st_size <= release.LIMIT)
        raw = manifest.read_bytes()
    else:
        raw = (fetch or release.download)(reference['manifest_url'], limit=release.LIMIT)
    _check(isinstance(raw, bytes) and len(raw) <= release.LIMIT
           and hashlib.sha256(raw).hexdigest() == reference['manifest_sha256'])
    normalized = cache / (reference['inventory_sha256'] + '.inventory.json')
    if normalized.exists():
        _check(normalized.is_file() and normalized.stat().st_size <= metadata.MAX_RECEIPT)
        decoded = normalized.read_bytes()
        _check(hashlib.sha256(decoded).hexdigest() == reference['inventory_sha256'])
        discovery = metadata.inventory(json.loads(decoded))
    else:
        with ZipFile(io.BytesIO(raw)) as archive:
            members = [row for row in archive.infolist() if row.filename == 'ResList.bin']
            _check(len(members) == 1 and 0 < members[0].file_size <= release.LIMIT)
            xml = release._xml(archive.read(members[0]), reference['region'], reference['xml_md5'],
                               **({'parameters': parameters} if parameters is not None else {}))
        _check(xml.get('version') == reference['version'] and xml.get('tag') == 'baseTag')
        sections = {'baseTag': reference['version']}
        for section in xml.findall('BaseVersion'):
            tag, version = section.get('tag'), section.get('version')
            _check(tag not in sections)
            sections[tag] = version
        files, _ = release.files(raw, reference['region'], reference['version'], sections, reference['xml_md5'],
                                 **({'parameters': parameters} if parameters is not None else {}))
        discovery = metadata.inventory({key: reference[key] for key in ('region', 'branch', 'version')}
                                       | {'files': files, 'sections': sections})
        decoded = metadata._json(discovery)
        _check(hashlib.sha256(decoded).hexdigest() == reference['inventory_sha256'])
        _atomic_file(normalized, decoded)
    if not manifest.exists():
        _atomic_file(manifest, raw)
    return discovery


def load(cache, *, fetch=None, save=None, parameters=None) -> AuthenticatedNative:
    """Authenticate the fixed manifest and whole original native data file."""
    cache, reference = Path(cache), BASELINE
    discovery = discover(cache, fetch=fetch, parameters=parameters)
    selected = [(name, item) for name, item in metadata.sources(discovery).items()
                if item.digest == reference['native_md5'] and item.size == reference['native_size']]
    _check(len(selected) == 1)
    name, descriptor = selected[0]
    source = metadata.stage_original(discovery, name, cache / 'originals', save=save)
    data = metadata._original(source, descriptor)
    _check(hashlib.sha256(data).hexdigest() == reference['native_sha256'])
    return AuthenticatedNative(data, {**reference, 'native_path': name,
        'native_file': discovery['files'][name],
        'source_manifest_sha256': hashlib.sha256(metadata._json(discovery)).hexdigest()})
