"""Download and verify an immutable desktop slot; never activate or execute it.

Trust is the canonical repository's HTTPS release API, its asset digests and
tag-to-commit binding. This is not a claim of Sigstore/code-signature verification.
After online verification an OS-protected ticket supports offline restart checks.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

from .runtime_bundle import CHILD_TARGETS, MANIFEST_SCHEMA, RuntimeLayout, relative_resource
from .runtime_payload import digest, executable_target, no_links, validate

REPOSITORY = 'Firebird55/Game-immersion-toolkit'
API = 'https://api.github.com/repos/' + REPOSITORY
DOWNLOAD = 'https://github.com/' + REPOSITORY + '/releases/download/'
MAX_ARCHIVE = 4 * 1024**3
MAX_EXPANDED = 8 * 1024**3
MAX_JSON = 8 * 1024**2
MAX_FILES = 60000


class DesktopReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedCandidate:
    layout: RuntimeLayout
    slot_root: Path
    frontend_root: Path
    receipt_digest: str
    storage_epoch: int
    host_protocol: int


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)', value):
        raise DesktopReleaseError('Desktop release version is invalid.')
    return tuple(map(int, value.split('.')))


def _cancel(stop_event):
    if stop_event is not None and stop_event.is_set():
        raise DesktopReleaseError('Desktop update cancelled before activation.')


def _fetch(url, limit, stop_event, destination=None):
    _cancel(stop_event)
    request = Request(url, headers={'Accept': 'application/vnd.github+json' if url.startswith(API) else 'application/octet-stream',
        'User-Agent': 'Game-immersion-toolkit-desktop'})
    data = bytearray()
    with urlopen(request, timeout=30) as response:
        final = urlsplit(response.geturl())
        allowed = {'api.github.com'} if url.startswith(API) else {'github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com'}
        if final.scheme != 'https' or final.hostname not in allowed or final.username or final.password:
            raise DesktopReleaseError('Desktop release download redirected outside its trusted supplier.')
        length = response.headers.get('Content-Length')
        if length and (not length.isdecimal() or int(length) > limit):
            raise DesktopReleaseError('Desktop release download exceeds its size limit.')
        stream = destination.open('xb') if destination is not None else None
        size = 0
        try:
            while True:
                _cancel(stop_event)
                chunk = response.read(min(1024 * 1024, limit + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise DesktopReleaseError('Desktop release download exceeds its size limit.')
                if stream is not None:
                    stream.write(chunk)
                else:
                    data.extend(chunk)
        finally:
            if stream is not None:
                stream.close()
    return bytes(data)


def _json(url, stop_event):
    value = json.loads(_fetch(url, MAX_JSON, stop_event))
    if not isinstance(value, dict):
        raise DesktopReleaseError('Desktop release metadata is invalid.')
    return value


def _asset(release, name, tag):
    found = [asset for asset in release.get('assets', []) if asset.get('name') == name]
    if len(found) != 1:
        raise DesktopReleaseError('Desktop release asset is missing or ambiguous: ' + name)
    asset = found[0]
    if (asset.get('browser_download_url') != DOWNLOAD + tag + '/' + name
            or type(asset.get('size')) is not int or asset['size'] < 1
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', str(asset.get('digest', '')))):
        raise DesktopReleaseError('Desktop release asset lacks its trusted URL, size or digest.')
    return asset


def _check_asset(path, asset):
    if path.stat().st_size != asset['size'] or digest(path) != asset['digest'][7:]:
        raise DesktopReleaseError('Desktop release asset checksum does not match GitHub.')


def _tag_commit(tag, stop_event):
    obj = _json(API + '/git/ref/tags/' + tag, stop_event).get('object', {})
    for _ in range(5):
        sha = obj.get('sha', '')
        if not re.fullmatch(r'[a-f0-9]{40}', str(sha)):
            break
        if obj.get('type') == 'commit':
            return sha
        if obj.get('type') != 'tag':
            break
        obj = _json(API + '/git/tags/' + sha, stop_event).get('object', {})
    raise DesktopReleaseError('Desktop release tag does not resolve to a commit.')


def _slots(layout):
    if layout.mode != 'bundle':
        raise DesktopReleaseError('Immutable desktop updates require the installed executable.')
    path = layout.settings_root.with_name(layout.settings_root.name + '-runtimes')
    no_links(path)
    return path


def _protect(layout, raw, *, decrypt=False):
    if os.name == 'nt':
        from .lexirise import _protect as windows_protect
        return windows_protect(raw, decrypt=decrypt)
    from .protected_storage import ProtectedBlobs
    return ProtectedBlobs(directory=layout.settings_root / 'update-credentials').protect(raw, decrypt=decrypt)


def _ticket_path(layout, receipt_digest):
    if not re.fullmatch(r'[a-f0-9]{64}', str(receipt_digest)):
        raise DesktopReleaseError('Desktop update receipt digest is invalid.')
    path = layout.state_root / 'desktop-update-trust' / (receipt_digest + '.protected')
    no_links(path)
    return path


def _extract(archive, root, prefix, stop_event):
    """Extract only a portable closed tree, creating native links last."""
    seen, links = set(), []
    expanded = 0
    with zipfile.ZipFile(archive) as stream:
        members = stream.infolist()
        if len(members) > MAX_FILES:
            raise DesktopReleaseError('Desktop runtime contains too many files.')
        for member in members:
            _cancel(stop_event)
            name = member.filename.rstrip('/')
            relative_resource(name)
            if not name.startswith(prefix + '/'):
                raise DesktopReleaseError('Desktop runtime archive has an unexpected root.')
            name = relative_resource(name[len(prefix) + 1:])
            if name.casefold() in seen or member.flag_bits & 1:
                raise DesktopReleaseError('Desktop runtime archive contains duplicate or encrypted files.')
            seen.add(name.casefold())
            expanded += member.file_size
            if expanded > MAX_EXPANDED or member.file_size > MAX_ARCHIVE:
                raise DesktopReleaseError('Desktop runtime exceeds its expanded size limit.')
            path = root / name
            mode = member.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if member.is_dir():
                if kind not in (0, stat.S_IFDIR):
                    raise DesktopReleaseError('Invalid native runtime directory.')
                path.mkdir(parents=True, exist_ok=True)
            elif kind == stat.S_IFLNK:
                if member.file_size > 4096 or os.name == 'nt':
                    raise DesktopReleaseError('Unsupported native runtime link.')
                link = stream.read(member).decode('utf-8')
                if '\\' in link or ':' in link or '\0' in link or Path(link).is_absolute() or root.resolve() not in (path.parent / link).resolve().parents:
                    raise DesktopReleaseError('Native runtime link escapes the runtime.')
                links.append((path, link))
            elif kind not in (0, stat.S_IFREG):
                raise DesktopReleaseError('Desktop runtime archive contains a non-regular entry.')
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with stream.open(member) as source, path.open('xb') as target:
                    while chunk := source.read(1024 * 1024):
                        _cancel(stop_event)
                        target.write(chunk)
                path.chmod(0o755 if mode & 0o111 else 0o644)
        for path, link in links:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(link)


def _candidate(layout, slot, receipt_digest, target):
    no_links(slot)
    receipt_path = slot / 'PROVENANCE.json'
    if not receipt_path.is_file() or receipt_path.stat().st_size > MAX_JSON or digest(receipt_path) != receipt_digest:
        raise DesktopReleaseError('Selected desktop runtime receipt has changed.')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    validate(slot, receipt, target, installed=True)
    manifest = json.loads((slot / '_internal/runtime-manifest.json').read_text(encoding='utf-8'))
    resources, children = manifest.get('resources'), manifest.get('children')
    if (manifest.get('schema') != MANIFEST_SCHEMA or not isinstance(resources, dict)
            or not isinstance(children, list) or any(not isinstance(child, str) or child not in CHILD_TARGETS for child in children)
            or len(set(children)) != len(children) or not {'api', 'frontend', 'gateway'}.issubset(children)):
        raise DesktopReleaseError('Selected desktop runtime manifest is incomplete.')
    for name, sha in resources.items():
        relative_resource(name)
        if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{64}', sha):
            raise DesktopReleaseError('Selected desktop resource checksum is invalid.')
    epochs = [manifest.get('storage_epoch'), manifest.get('host_protocol')]
    if any(type(value) is not int or value != 1 for value in epochs) or epochs != [layout.storage_epoch, layout.host_protocol]:
        raise DesktopReleaseError('Desktop update needs an unsupported storage or host migration.')
    executable = slot / ('GameImmersionToolkit.exe' if target.startswith('windows-') else 'GameImmersionToolkit')
    selected = replace(layout, application_root=slot, resource_root=slot / '_internal', executable=executable,
        version=receipt['version'], source_commit=receipt['source_commit'], build_id=receipt['build_id'], profile='runtime',
        resources=resources, children=tuple(children), storage_epoch=epochs[0], host_protocol=epochs[1])
    for name in resources:
        selected.resource(name)
    from .desktop_frontend import FrontendBuild, MANIFEST
    frontend = selected.resource_root / 'desktop'
    build = FrontendBuild(frontend)
    if ({name for name in resources if name.startswith('desktop/')} != {
            'desktop/' + name for name in (*build.files, MANIFEST)}
            or build.value.get('version') != selected.version or build.value.get('source_commit') != selected.source_commit):
        raise DesktopReleaseError('Selected desktop frontend differs from the runtime release.')
    return VerifiedCandidate(selected, slot, frontend, receipt_digest, *epochs)


def verify_selected(layout, slot_root, receipt_digest):
    """Revalidate an OS-bound accepted release and every byte before restart."""
    try:
        slot = Path(slot_root).absolute()
        if slot.parent != _slots(layout):
            raise DesktopReleaseError('Selected desktop runtime is outside the managed slots.')
        path = _ticket_path(layout, receipt_digest)
        if path.stat().st_size > MAX_JSON:
            raise DesktopReleaseError('Desktop trust ticket is invalid.')
        ticket = json.loads(_protect(layout, path.read_bytes(), decrypt=True))
        if (ticket.get('schema') != 'toolkit-desktop-trust-v1' or ticket.get('repository') != REPOSITORY
                or ticket.get('receipt_digest') != receipt_digest or ticket.get('slot') != slot.name
                or ticket.get('target') != executable_target(layout.executable)):
            raise DesktopReleaseError('Desktop trust ticket does not describe the selected runtime.')
        candidate = _candidate(layout, slot, receipt_digest, ticket['target'])
        if candidate.layout.source_commit != ticket.get('commit') or 'v' + candidate.layout.version != ticket.get('tag'):
            raise DesktopReleaseError('Desktop trust ticket release identity has changed.')
        return candidate
    except DesktopReleaseError:
        raise
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as error:
        raise DesktopReleaseError('Selected desktop runtime failed verification; the previous runtime is retained.') from error


def prepare_update(layout, current_version, progress=None, stop_event=None):
    """Stage the latest eligible release. Caller retains the owner/writer lease."""
    report = progress or (lambda message: None)
    try:
        slots = _slots(layout)
        current = _version(current_version)
        target = executable_target(layout.executable)
        report('Checking the published desktop release.')
        release = _json(API + '/releases/latest', stop_event)
        tag = release.get('tag_name', '')
        if release.get('draft') or release.get('prerelease') or not isinstance(tag, str) or not tag.startswith('v'):
            return None
        version = tag[1:]
        if _version(version) <= current:
            return None
        name = 'DESKTOP-PROVENANCE-' + target + '.json'
        if not any(item.get('name') == name for item in release.get('assets', [])):
            return None  # Historical source-only releases are not desktop updates.
        metadata_asset = _asset(release, name, tag)
        raw = _fetch(metadata_asset['browser_download_url'], MAX_JSON, stop_event)
        if len(raw) != metadata_asset['size'] or hashlib.sha256(raw).hexdigest() != metadata_asset['digest'][7:]:
            raise DesktopReleaseError('Desktop distribution receipt checksum differs from GitHub.')
        metadata = json.loads(raw)
        if metadata.get('release_eligible') is not True or metadata.get('candidate') is not False:
            return None
        commit = _tag_commit(tag, stop_event)
        archive_name = 'Game-immersion-toolkit-' + version + '-' + target + '-runtime.zip'
        if (metadata.get('schema') != 'proxy-desktop-distribution-v1' or metadata.get('repository') != REPOSITORY
                or metadata.get('version') != version or metadata.get('tag') != tag or metadata.get('target') != target
                or metadata.get('source_commit') != commit or metadata.get('update_artifact') != archive_name
                or metadata.get('native_acceptance') != 'approved'
                or type(metadata.get('storage_epoch')) is not int or metadata['storage_epoch'] != layout.storage_epoch
                or type(metadata.get('host_protocol')) is not int or metadata['host_protocol'] != layout.host_protocol):
            raise DesktopReleaseError('Desktop distribution does not match the published release or host protocol.')
        receipt_digest = metadata.get('runtime_receipt_sha256', '')
        ticket_path = _ticket_path(layout, receipt_digest)
        artifact = _asset(release, archive_name, tag)
        declared = [item for item in metadata.get('artifacts', []) if item.get('path') == archive_name]
        if len(declared) != 1 or declared[0].get('bytes') != artifact['size'] or declared[0].get('sha256') != artifact['digest'][7:]:
            raise DesktopReleaseError('Desktop runtime archive is not bound to its distribution receipt.')
        slot = slots / (version + '-' + target + '-' + receipt_digest[:16])
        if slot.exists():
            return verify_selected(layout, slot, receipt_digest)
        slots.mkdir(parents=True, exist_ok=True)
        report('Downloading and checking the complete desktop runtime.')
        with tempfile.TemporaryDirectory(prefix='.incoming-', dir=slots) as staging:
            staging = Path(staging)
            archive = staging / 'runtime.zip'
            _fetch(artifact['browser_download_url'], min(artifact['size'], MAX_ARCHIVE), stop_event, archive)
            _check_asset(archive, artifact)
            tree = staging / 'runtime'
            tree.mkdir()
            _extract(archive, tree, archive_name.removesuffix('-runtime.zip'), stop_event)
            verified = _candidate(layout, tree, receipt_digest, target)
            if (verified.layout.version != version or verified.layout.source_commit != commit
                    or verified.layout.build_id != metadata.get('runtime_build_id')):
                raise DesktopReleaseError('Desktop payload identity differs from the release receipt.')
            _cancel(stop_event)
            ticket = {'schema': 'toolkit-desktop-trust-v1', 'repository': REPOSITORY, 'tag': tag, 'commit': commit,
                'target': target, 'slot': slot.name, 'receipt_digest': receipt_digest,
                'archive_sha256': artifact['digest'][7:], 'metadata_sha256': hashlib.sha256(raw).hexdigest()}
            protected = _protect(layout, json.dumps(ticket, sort_keys=True).encode())
            # Protection must work before publishing an immutable slot. No
            # plaintext fallback or partial activation is permitted.
            from .protected_storage import private_write
            _cancel(stop_event)
            no_links(slot)
            private_write(ticket_path, protected)
            tree.rename(slot)
        report('Desktop update verified; waiting for the host to switch services.')
        return verify_selected(layout, slot, receipt_digest)
    except DesktopReleaseError:
        raise
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError, zipfile.BadZipFile) as error:
        raise DesktopReleaseError('Desktop update could not be verified; the running version is unchanged.') from error
