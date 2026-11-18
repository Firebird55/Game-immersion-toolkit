"""Original Global launcher metadata, planned artifacts and immutable inputs.

Planning reads bounded metadata only. SDK/configuration payload acquisition is
separate, exposes exact costs and authenticates complete publisher checksums
before parsing. These acquisition receipts are not library approvals.
"""
from dataclasses import asdict, dataclass
import configparser
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.parse import quote, urlsplit
import urllib.request
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .nte_updater_native import check
from .preparation_errors import PreparationFailure
from .private_data_paths import _no_links


VERSION_URL = 'https://ntecdn1.perfectworld.com/hd/publish_PC/launcher/Version.ini'
HOSTS = frozenset(('ntecdn1.perfectworld.com', 'ntecdn2.perfectworld.com'))
MAX_VERSION = 64 * 1024
MAX_MANIFEST = 2 * 1024**2
MAX_PAYLOAD = 32 * 1024**2
MAX_CONFIGURATION = 256 * 1024
FORMAT = 'nte-original-updater-inputs-v1'
APPROVAL = 'nte-original-updater-approval-v1'


class BootstrapRequired(PreparationFailure):
    def __init__(self, inputs, cache):
        self.inputs = inputs
        self.costs = inputs.costs(cache)
        super().__init__('bootstrap_required',
            'Official NTE compatibility data needs downloading. Prepare the game data to continue; the previous library is retained.',
            previous_snapshot_retained=True)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _match(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _url(value):
    check(isinstance(value, str) and len(value) <= 2048)
    parts = urlsplit(value)
    check(parts.scheme == 'https' and parts.hostname in HOSTS and parts.netloc == parts.hostname
          and not parts.query and not parts.fragment and not parts.username
          and '%' not in parts.path and '\\' not in parts.path
          and '..' not in PurePosixPath(parts.path).parts)
    return value


def download(url, *, limit):
    from .publisher_http import download as read
    _url(url)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect())
    return read(url, limit, opener=opener.open)


def _decode_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            check(key not in value)
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


@dataclass(frozen=True)
class Artifact:
    role: str
    url: str
    member: str
    size: int
    md5: str
    packed_size: int
    packed_md5: str

    @property
    def identity(self):
        return _sha(_json(asdict(self)))


@dataclass(frozen=True)
class Plan:
    region: str
    version: str
    manifest_url: str
    version_sha256: str
    manifest_sha256: str
    artifacts: tuple[Artifact, ...]

    def description(self):
        return {**asdict(self), 'artifacts': [asdict(item) for item in self.artifacts]}

    @property
    def identity(self):
        return _sha(_json(self.description()))

    def costs(self, cache):
        missing = [item for item in self.artifacts if retained(cache, item) is None]
        return {'compressed_bytes': sum(item.packed_size for item in missing),
                'decoded_bytes': sum(item.size for item in missing),
                'cached_compressed_bytes': sum(item.packed_size for item in self.artifacts if item not in missing),
                'audio_bytes': 0}


def plan(region='nte-global', *, fetch=None):
    """Return exact payload costs after bounded original metadata discovery."""
    check(region == 'nte-global')
    fetch = fetch or download
    raw_version = fetch(VERSION_URL, limit=MAX_VERSION)
    check(isinstance(raw_version, bytes) and 0 < len(raw_version) <= MAX_VERSION)
    version = configparser.ConfigParser(interpolation=None, strict=True)
    version.read_string(raw_version.decode('utf-8-sig'))
    release = version['VERSION']['version']
    check(_match(r'\d+\.\d+\.\d+\.\d+', release))
    manifest_url = _url(version['VERSION']['filelisturl'])
    namespace = urlsplit(VERSION_URL).path.rsplit('/', 1)[0]
    check(urlsplit(manifest_url).path.startswith(namespace + '/') and manifest_url.endswith('/AllFiles.xml'))
    raw_manifest = fetch(manifest_url, limit=MAX_MANIFEST)
    check(isinstance(raw_manifest, bytes) and 0 < len(raw_manifest) <= MAX_MANIFEST
          and b'<!DOCTYPE' not in raw_manifest.upper() and b'<!ENTITY' not in raw_manifest.upper())
    root = ElementTree.fromstring(raw_manifest)
    check(root.tag == 'All_Files' and not root.attrib)
    versions, urls = root.findall('ProductVersion'), root.findall('Url')
    check(len(versions) == len(urls) == 1 and set(versions[0].attrib) == {'Version'}
          and set(urls[0].attrib) == {'BaseUrl'})
    product = versions[0].get('Version')
    check(_match(re.escape(release) + r'(?:_\d+)?', product))
    base = _url(urls[0].get('BaseUrl'))
    check(urlsplit(base).path == namespace and manifest_url == base + '/' + product + '/AllFiles.xml')
    files = root.findall('File')
    check(0 < len(files) <= 100_000)
    paths, selected = set(), {}
    for node in files:
        check(set(node.attrib) == {'Checksum', 'Path', 'Size', 'ZipChecksum', 'ZipSize'} and not list(node))
        path = node.get('Path')
        check(isinstance(path, str) and path.startswith('/') and path == str(PurePosixPath(path))
              and '..' not in PurePosixPath(path).parts and not any(c in path for c in ('\\', '\0', '%', '?', '#'))
              and path.casefold() not in paths)
        paths.add(path.casefold())
        role = ('sdk' if path == '/PatcherSDK_x64.dll' else
                'configuration' if _match(r'/ResFilesM/[0-9]+/PatcherConfig/PatcherConfig\.json', path) else None)
        if role is None:
            continue
        check(role not in selected)
        size, packed = node.get('Size'), node.get('ZipSize')
        check(_match('[0-9]{1,10}', size) and _match('[0-9]{1,10}', packed))
        size, packed = int(size), int(packed)
        check(0 < size <= (MAX_PAYLOAD if role == 'sdk' else MAX_CONFIGURATION) and 0 < packed <= MAX_PAYLOAD)
        digest, packed_digest = node.get('Checksum'), node.get('ZipChecksum')
        check(_match('[a-f0-9]{32}', digest) and _match('[a-f0-9]{32}', packed_digest))
        url = _url(base + '/' + product + quote(path, safe='/') + '.zip')
        selected[role] = Artifact(role, url, PurePosixPath(path).name, size, digest, packed, packed_digest)
    check(set(selected) == {'sdk', 'configuration'})
    return Plan(region, product, manifest_url, _sha(raw_version), _sha(raw_manifest),
                tuple(selected[role] for role in sorted(selected)))


def _root(cache, artifact):
    root = Path(cache) / 'original-updater/artifacts' / artifact.identity
    _no_links(root)
    return root


def retained(cache, artifact):
    """Return immutable authenticated input bytes; never fall back to a key cache."""
    root = _root(cache, artifact)
    try:
        receipt_path, payload_path = root / 'receipt.json', root / 'member.data'
        check(0 < receipt_path.stat().st_size <= 16 * 1024 and payload_path.stat().st_size == artifact.size)
        receipt = _decode_json(receipt_path.read_bytes())
        check(set(receipt) == {'format', 'artifact', 'member_sha256', 'zip_sha256'}
              and receipt['format'] == FORMAT and receipt['artifact'] == asdict(artifact)
              and _match('[a-f0-9]{64}', receipt['member_sha256'])
              and _match('[a-f0-9]{64}', receipt['zip_sha256']))
        data = payload_path.read_bytes()
        check(_sha(data) == receipt['member_sha256'] and hashlib.md5(data).hexdigest() == artifact.md5)
        return data
    except (OSError, ValueError, TypeError, KeyError):
        return None


def acquire(cache, artifact, *, fetch=None):
    fetch = fetch or download
    root = _root(cache, artifact)
    data = retained(cache, artifact)
    if data is not None:
        return data
    raw = fetch(_url(artifact.url), limit=artifact.packed_size)
    check(isinstance(raw, bytes) and len(raw) == artifact.packed_size
          and hashlib.md5(raw).hexdigest() == artifact.packed_md5)
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            check(len(entries) == 1 and entries[0].filename == artifact.member and entries[0].file_size == artifact.size
                  and not entries[0].is_dir() and not entries[0].flag_bits & 1)
            data = archive.read(entries[0])
    except BadZipFile as error:
        raise ValueError('The original NTE updater archive failed verification') from error
    check(len(data) == artifact.size and hashlib.md5(data).hexdigest() == artifact.md5)
    receipt = {'format': FORMAT, 'artifact': asdict(artifact), 'member_sha256': _sha(data), 'zip_sha256': _sha(raw)}
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as folder:
        temporary = Path(folder)
        (temporary / 'member.data').write_bytes(data)
        (temporary / 'receipt.json').write_bytes(_json(receipt))
        (temporary / 'member.data').replace(root / 'member.data')
        (temporary / 'receipt.json').replace(root / 'receipt.json')
    check(retained(cache, artifact) == data)
    return data


def resolve(inputs, cache, *, fetch=None):
    """Materialize a previously planned SDK/config pair and derive a candidate."""
    from .nte_original_updater import derive
    check(isinstance(inputs, Plan) and inputs.region == 'nte-global')
    artifacts = {item.role: item for item in inputs.artifacts}
    check(set(artifacts) == {'sdk', 'configuration'})
    sdk = acquire(cache, artifacts['sdk'], fetch=fetch)
    configuration = _decode_json(acquire(cache, artifacts['configuration'], fetch=fetch))
    check(isinstance(configuration, dict) and isinstance(configuration.get('gameResUrl'), list)
          and 0 < len(configuration['gameResUrl']) <= 16)
    for url in configuration['gameResUrl']:
        _url(url)
        check(urlsplit(url).path == '/clientRes')
    check(isinstance(configuration.get('branchName'), str)
          and _match(r'PC_[0-9]+', configuration['branchName']))
    return derive(sdk, configuration)


def recheck(inputs, *, fetch=None):
    check(isinstance(inputs, Plan))
    if plan(inputs.region, fetch=fetch) != inputs:
        raise PreparationFailure('game_files_changed',
            'NTE update information changed during preparation. Retry; the previous library is retained.',
            game_files_changed=True, previous_snapshot_retained=True)


def resolve_retained(inputs, cache):
    """Background discovery never implicitly downloads an SDK/config payload."""
    check(isinstance(inputs, Plan))
    if any(retained(cache, item) is None for item in inputs.artifacts):
        raise BootstrapRequired(inputs, cache)
    def forbidden(*args, **kwargs):
        raise ValueError('Missing retained original NTE updater input')
    return resolve(inputs, cache, fetch=forbidden)


def release_origin(inputs, cache):
    """Use the current original launcher's declared game branch/CDN owner."""
    resolve_retained(inputs, cache)
    artifact = next(item for item in inputs.artifacts if item.role == 'configuration')
    value = _decode_json(retained(cache, artifact))
    return urlsplit(value['gameResUrl'][0]).hostname, value['branchName']


def _publish(path, raw):
    _no_links(path)
    if path.exists():
        check(path.is_file() and path.read_bytes() == raw)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        pending = Path(folder) / 'complete.json'
        pending.write_bytes(raw)
        pending.replace(path)


def approve(inputs, cache, archive, region, branch, version, sections, checksum, *, fetch=None,
            crypto=None, retain_approval=True):
    """Bind original input provenance to a complete declared resource list.

    Payload acquisition must already have been separately planned/authorized.
    This method only reads retained source artifacts, then rechecks original
    metadata pointers before computing the immutable approval receipt. A caller
    without an available content reader can verify the identity without persisting it.
    """
    from . import nte_release as release
    check(isinstance(inputs, Plan) and region == inputs.region)
    parameters = resolve_retained(inputs, cache)
    configuration = next(item for item in inputs.artifacts if item.role == 'configuration')
    configuration_body = retained(cache, configuration)
    check(_decode_json(configuration_body)['branchName'] == branch)
    result = release.files(archive, region, version, sections, checksum,
                           parameters=(parameters.key, parameters.iv), crypto=crypto)
    original = {'region': region, 'branch': branch, 'version': version, 'sha256': result[1][1]}
    receipt = {'format': APPROVAL, 'inputs': inputs.description(), 'inputs_sha256': inputs.identity,
        'original': original, 'declared_xml_md5': checksum, 'manifest_sha256': _sha(archive),
        'inventory_sha256': _sha(release._json_manifest(result)), 'sdk_sha256': parameters.sdk_sha256,
        'configuration_sha256': _sha(configuration_body),
        'native_evidence_sha256': _sha(_json(parameters.evidence))}
    recheck(inputs, fetch=fetch)
    raw = _json(receipt)
    identity = _sha(raw)
    if retain_approval:
        _publish(Path(cache)/'original-updater/approvals'/(identity+'.json'), raw)
    reference = {'kind': APPROVAL, 'proof_sha256': identity, 'original': original}
    return result, reference


def _inputs(value):
    check(isinstance(value, dict) and set(value) == {'region', 'version', 'manifest_url',
          'version_sha256', 'manifest_sha256', 'artifacts'} and value['region'] == 'nte-global'
          and _match(r'\d+\.\d+\.\d+\.\d+(?:_\d+)?', value['version'])
          and _match('[a-f0-9]{64}', value['version_sha256'])
          and _match('[a-f0-9]{64}', value['manifest_sha256'])
          and isinstance(value['artifacts'], list) and len(value['artifacts']) == 2)
    _url(value['manifest_url'])
    artifacts = []
    for row in value['artifacts']:
        check(isinstance(row, dict) and set(row) == set(Artifact.__dataclass_fields__))
        artifact = Artifact(**row)
        check(artifact.role in ('sdk', 'configuration')
              and artifact.member == ('PatcherSDK_x64.dll' if artifact.role == 'sdk' else 'PatcherConfig.json')
              and type(artifact.size) is int and 0 < artifact.size <= MAX_PAYLOAD
              and type(artifact.packed_size) is int and 0 < artifact.packed_size <= MAX_PAYLOAD
              and _match('[a-f0-9]{32}', artifact.md5) and _match('[a-f0-9]{32}', artifact.packed_md5))
        _url(artifact.url)
        check(artifact.url.startswith(value['manifest_url'].rsplit('/', 1)[0] + '/'))
        artifacts.append(artifact)
    check({item.role for item in artifacts} == {'sdk', 'configuration'})
    return Plan(**{**value, 'artifacts': tuple(artifacts)})


def check_reference(reference, cache, *, original=None, result=None):
    """Historical verification is local and never consults latest metadata."""
    from . import nte_release as release
    check(isinstance(reference, dict) and set(reference) == {'kind', 'proof_sha256', 'original'}
          and reference['kind'] == APPROVAL and _match('[a-f0-9]{64}', reference['proof_sha256']))
    path = Path(cache)/'original-updater/approvals'/(reference['proof_sha256']+'.json')
    _no_links(path)
    check(path.is_file() and 0 < path.stat().st_size <= MAX_CONFIGURATION)
    raw = path.read_bytes()
    check(_sha(raw) == reference['proof_sha256'])
    receipt = _decode_json(raw)
    check(set(receipt) == {'format', 'inputs', 'inputs_sha256', 'original', 'declared_xml_md5',
          'manifest_sha256', 'inventory_sha256', 'sdk_sha256', 'configuration_sha256', 'native_evidence_sha256'}
          and receipt['format'] == APPROVAL and receipt['original'] == reference['original'])
    identity = receipt['original']
    check(isinstance(identity, dict) and set(identity) == {'region', 'branch', 'version', 'sha256'}
          and identity['region'] == 'nte-global' and _match(r'PC_[0-9]+', identity['branch'])
          and _match(r'\d+\.\d+\.\d+', identity['version']) and _match('[a-f0-9]{64}', identity['sha256']))
    for key in ('inputs_sha256', 'manifest_sha256', 'inventory_sha256', 'sdk_sha256',
                'configuration_sha256', 'native_evidence_sha256'):
        check(isinstance(receipt[key], str) and _match('[a-f0-9]{64}', receipt[key]))
    check(_match('[a-f0-9]{32}', receipt['declared_xml_md5']))
    inputs = _inputs(receipt['inputs'])
    check(inputs.identity == receipt['inputs_sha256'])
    for artifact in inputs.artifacts:
        data = retained(cache, artifact)
        check(data is not None and _sha(data) == receipt['sdk_sha256' if artifact.role == 'sdk' else 'configuration_sha256'])
    if original is not None:
        check(identity == original)
    if result is not None:
        check(result[1][1] == identity['sha256'] and _sha(release._json_manifest(result)) == receipt['inventory_sha256'])
    return receipt


def parameters_for_reference(reference, cache):
    receipt = check_reference(reference, cache)
    parameters = resolve_retained(_inputs(receipt['inputs']), cache)
    check(parameters.sdk_sha256 == receipt['sdk_sha256']
          and _sha(_json(parameters.evidence)) == receipt['native_evidence_sha256'])
    return parameters.key, parameters.iv
