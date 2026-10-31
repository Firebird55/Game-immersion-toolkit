"""Reproduce PyInstaller's narrow macOS library transformation, without execution.

Supplier programs are never run. Only the pinned build tool's architecture,
install-name and ad-hoc signing operations run, on disposable copies. Acceptance
still requires byte equality with the delivered binary, including its signature.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path, PurePosixPath
import sys
import tempfile

MACHO_MAGICS = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
    b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
    b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}
TOOL_PACKAGES = ('pyinstaller', 'macholib', 'altgraph', 'packaging')
MAX_BINARY = 512 * 1024**2


def collected_destination(name):
    """Recover COLLECT's destination, not a caller-supplied filesystem path."""
    if not isinstance(name, str) or '\\' in name or ':' in name or '\0' in name:
        raise ValueError('Invalid macOS collected destination.')
    parts = name.split('/')
    if any(part in {'', '.', '..'} for part in parts):
        raise ValueError('Invalid macOS collected destination.')
    if parts[:2] == ['asr', '_internal']:
        parts = parts[2:]
    elif parts[:1] == ['_internal']:
        parts = parts[1:]
    else:
        raise ValueError('macOS replay only accepts collected internal libraries.')
    if not parts:
        raise ValueError('Missing macOS collected filename.')
    return '/'.join(parts)


def verify_toolchain(wheels):
    """Check the executing transformation code against already verified wheels."""
    verified = {}
    for name in TOOL_PACKAGES:
        wheel = wheels.get(name)
        if not wheel:
            raise ValueError('macOS replay requires the inspected build-tool wheel: ' + name)
        distribution = importlib.metadata.distribution(name)
        if distribution.version != wheel['version']:
            raise ValueError('macOS replay build-tool version differs: ' + name)
        files = {path: value for path, value in wheel['files'].items() if path.endswith('.py')}
        if not files:
            raise ValueError('macOS replay build-tool source inventory is empty: ' + name)
        for member, expected in files.items():
            if member.startswith('/') or '\\' in member or any(x in {'', '.', '..'} for x in member.split('/')):
                raise ValueError('Invalid build-tool source member.')
            path = Path(distribution.locate_file(member))
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('macOS replay build-tool source differs: ' + name + '/' + member)
        verified[name] = {'version': wheel['version'], 'wheel_sha256': wheel['sha256'],
                          'source_files_verified': len(files)}
    # A loaded module from another path must not substitute for the verified
    # distribution. This also covers a caller that imported it before review.
    for name, module in tuple(sys.modules.items()):
        package = name.split('.')[0]
        distribution_name = 'pyinstaller' if package == 'PyInstaller' else package
        if distribution_name not in TOOL_PACKAGES or not getattr(module, '__file__', None):
            continue
        path = Path(module.__file__)
        wheel = wheels[distribution_name]
        source = path.with_suffix('.py') if path.suffix == '.pyc' else path
        known = {Path(importlib.metadata.distribution(distribution_name).locate_file(member)).resolve()
                 for member in wheel['files'] if member.endswith('.py')}
        if source.resolve() not in known:
            raise ValueError('macOS replay imported build tool outside its verified distribution.')
    return verified


def replay(data, payload_name, target):
    """Return the exact transformed hash; never strip or normalize output bytes."""
    destination = collected_destination(payload_name)
    architecture = {'macos-arm64': 'arm64', 'macos-x64': 'x86_64'}.get(target)
    if not architecture or sys.platform != 'darwin':
        raise ValueError('macOS post-processing replay requires its native build host.')
    if len(data) > MAX_BINARY or data[:4] not in MACHO_MAGICS:
        raise ValueError('macOS replay requires a bounded actual Mach-O supplier member.')
    from PyInstaller.building.utils import process_collected_binary
    from PyInstaller.config import CONF

    # No shared PyInstaller cache is trusted or modified. In particular, cached
    # pickle index files from an earlier build are never deserialized here.
    with tempfile.TemporaryDirectory(prefix='toolkit-macho-review-') as temporary:
        # macOS exposes /var through /private/var. Compare canonical paths on
        # both sides while still rejecting linked or escaped output files.
        root = Path(temporary).resolve()
        source = root / 'supplier' / PurePosixPath(destination).name
        source.parent.mkdir()
        source.write_bytes(data)
        original = dict(CONF)
        try:
            CONF['cachedir'] = str(root / 'cache')
            CONF['upx_dir'] = None
            output = Path(process_collected_binary(str(source), destination,
                use_strip=False, use_upx=False, target_arch=architecture,
                codesign_identity=None, entitlements_file=None, strict_arch_validation=True))
            if root not in output.resolve().parents or output.is_symlink() or not output.is_file():
                raise ValueError('macOS replay output escaped its disposable workspace.')
            return hashlib.sha256(output.read_bytes()).hexdigest()
        finally:
            CONF.clear()
            CONF.update(original)
