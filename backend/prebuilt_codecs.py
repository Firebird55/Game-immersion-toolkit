"""One verified experimental codec and fixed decode operation; no tool discovery.

This does not approve production redistribution or enable the general game/audio
adapter. The production profile and all unprobed codec capabilities stay closed.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace

from .prebuilt_readers import _no_links, _unique_json, reader_environment
from .preparation_errors import PreparationFailure
from .preparation_worker import PreparationJob
from .runtime_bundle import RuntimeBundleError, discover_layout, relative_resource

PREFIX = 'codecs/xiph-flac/'
SCHEMA = 'proxy-experimental-codec-v2'
ARCHIVE_SHA256 = 'f2c1c76592a82ffff8413ba3c4a1299b6c7ab06c734dee03fd88630485c2b920'
EXECUTABLE_SHA256 = '959b7871c00598360734b3792e24b369de6a08f91c02d18abaa7678488b9a355'
SOURCE_KIT_SHA256 = '7dc11c7fc0c87c6304b0d09af81d76a4d6229c15ce8590681a74e14ca85d2f6b'
PINNED_FILES = {
    'flac.exe': EXECUTABLE_SHA256,
    'FLAC.dll': '29c4c88bc8cb17e30aaef2d9af50455abeeccc59bda18d1189dfb7568d9e27d8',
    'codec-sources.zip': SOURCE_KIT_SHA256,
    'notices/COPYING.GPL': '8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643',
    'notices/COPYING.LGPL': '5df07007198989c622f5d41de8d703e7bef3d0e79d62e24332ee739a452af62a',
    'notices/COPYING.Xiph': '7866ee98760fc1f0156b4fe6bf530257e02be487ab3fd94e2b63799dd32d6b2c',
    'notices/COPYING.FDL': 'c5d2b95c2538d2e41d8eedd9ecc750cd5fee085c7bb2bc3e2f95f4e59cc0b10d',
    'notices/AUTHORS': '89d44b9c876a8a5cbfc886348a151abd74eeb49e4b690b0cfe96d44a9afe8118',
    'notices/README.md': '60f6958863c656e55017928edfda20ec26f60b06d673a68cc0030fd24f27f544',
    'notices/SOURCE-COPYRIGHTS.txt': 'b80a97d5c805983929421d3d91d6d39a9393994825004f11d5a9ed356efba767',
}
SOURCE_INPUTS = {'packaging/codecs/flac-reference.json', 'scripts/build-reference-codec.ps1',
    'scripts/reference-codec.py', 'LICENSE', 'scripts/prepare-runtime-codec.py', 'backend/prebuilt_codecs.py'}
SOURCE_REVIEW = 'verified-source-kit;production-hosting-open'
SERVICING_REVIEW = 'current-stable-bounded-scope;postrelease-review-required'
POLICY = {'operation': 'flac-to-pcm-s16le', 'rate': 16000, 'channels': 1, 'max_samples': 16000}


def _failure(message):
    return PreparationFailure('bundle_codec_unavailable', message)


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _work_file(path, work_root):
    path = Path(path)
    _no_links(path.absolute())
    relative_resource(path.name)
    if not path.is_absolute() or path != path.resolve() or work_root not in path.parents or path.parent == work_root:
        raise _failure('Experimental codec input/output need canonical files in a private work subdirectory.')
    return path


@dataclass(frozen=True)
class FlacDecoder:
    layout: object
    manifest: dict
    executable: Path

    def _command(self, source, destination, samples):
        return [str(self.executable), '--decode', '--silent', '--force-raw-format',
            '--endian=little', '--sign=signed', '--until='+str(samples),
            '--output-name='+str(destination), '--', str(source)]

    def decode(self, source, destination, *, cancelled=None, timeout=10):
        """Publish PCM atomically after owned child cleanup; failed attempts retain old bytes."""
        cancelled = threading.Event() if cancelled is None else cancelled
        owner = SimpleNamespace(stop_event=cancelled, _publication_lock=threading.RLock())
        job = PreparationJob(owner, cancelled)
        job.checkpoint()
        # Revalidate bytes immediately before invocation, not only at resolution.
        current = prebuilt_flac_decoder(layout=self.layout)
        if current.executable != self.executable or current.manifest != self.manifest:
            raise _failure('The selected codec changed before execution.')
        source = _work_file(source, self.layout.work_root)
        destination = _work_file(destination, self.layout.work_root)
        if (source == destination or source.parent != destination.parent or not destination.parent.is_dir()
                or destination.exists() and not destination.is_file()):
            raise _failure('Codec input and output must be separate files in one owned work directory.')
        if not source.is_file() or not 42 <= source.stat().st_size <= 1024 * 1024:
            raise _failure('Experimental FLAC input is missing or exceeds its bound.')
        with source.open('rb') as stream:
            header = stream.read(42)
        if header[:4] != b'fLaC' or header[4] & 0x7f or header[5:8] != b'\0\0\x22':
            raise _failure('Expected a native FLAC stream with STREAMINFO first.')
        audio = int.from_bytes(header[18:26], 'big')
        rate, channels, bits, samples = audio >> 44, ((audio >> 41) & 7) + 1, ((audio >> 36) & 31) + 1, audio & ((1 << 36) - 1)
        if (rate, channels, bits) != (16000, 1, 16) or not 1 <= samples <= POLICY['max_samples']:
            raise _failure('Experimental FLAC scope is at most one second of 16 kHz mono 16-bit audio.')
        if not 0 < timeout <= 30:
            raise _failure('Codec execution needs a bounded deadline of at most 30 seconds.')
        with tempfile.TemporaryDirectory(prefix='codec-attempt-', dir=destination.parent) as temporary:
            pending = Path(temporary) / 'decoded.pcm'
            command = self._command(source, pending, samples)
            # The owned Windows bootstrap needs these explicit roots before it
            # joins its Job Object; no inherited loader/account state is retained.
            environment = self.layout.child_environment('windows-bootstrap', reader_environment())
            status = job.run(command, cwd=Path(temporary), timeout=timeout, env=environment)
            if status or not pending.is_file() or pending.stat().st_size != samples * 2:
                raise _failure('The verified codec could not decode this bounded FLAC input; previous output was retained.')
            checksum = hashlib.sha256(pending.read_bytes()).hexdigest()
            with job.publication():
                _no_links(destination)
                pending.replace(destination)
        return {'operation': POLICY['operation'], 'rate': rate, 'channels': channels,
            'samples': samples, 'pcm_bytes': samples * 2, 'pcm_sha256': checksum, 'owned_cleanup': 'passed'}


def prebuilt_flac_decoder(*, layout=None):
    layout = layout or discover_layout()
    if layout.mode != 'bundle' or layout.profile != 'runtime-experiment':
        raise _failure('The codec is available only in the quarantined runtime experiment; production rights/native gates remain open.')
    try:
        root = layout.resource_root / PREFIX
        _no_links(root)
        path = layout.resource(PREFIX + 'codec-manifest.json')
        if path.stat().st_size > 128 * 1024:
            raise ValueError()
        value = json.loads(path.read_bytes(), object_pairs_hook=_unique_json)
        if (value.get('schema') != SCHEMA or value.get('kind') != 'xiph-flac-experiment'
                or value.get('platform') != 'win-x64' or value.get('version') != '1.5.0'
                or value.get('source_commit') != layout.source_commit or value.get('source_dirty') is not False
                or value.get('archive_sha256') != ARCHIVE_SHA256 or value.get('entry') != 'flac.exe'
                or value.get('policy') != POLICY or value.get('production_execution_allowed') is not False
                or value.get('redistribution_review') != 'pending-exact-output'
                or value.get('source_delivery_review') != SOURCE_REVIEW or value.get('servicing_review') != SERVICING_REVIEW
                or value.get('native_windows_11_acceptance') != 'unavailable' or value.get('r19_complete') is not False):
            raise ValueError()
        files = value['files']
        if (not isinstance(files, dict) or set(files) != set(PINNED_FILES) or value.get('build_id') != identity(files)
                or {name for name in layout.resources if name.startswith(PREFIX)} != {PREFIX + name for name in (*files, 'codec-manifest.json')}):
            raise ValueError()
        actual, directories = set(), set()
        for item in root.rglob('*'):
            _no_links(item)
            if item.is_file(): actual.add(item.relative_to(root).as_posix())
            elif item.is_dir(): directories.add(item.relative_to(root).as_posix())
            else: raise ValueError()
        if actual != {*files, 'codec-manifest.json'} or directories != {'notices'}:
            raise ValueError()
        for name, expected in PINNED_FILES.items():
            entry = files[name]
            if (not isinstance(entry, dict) or set(entry) != {'bytes', 'sha256'} or entry['sha256'] != expected
                    or type(entry['bytes']) is not int or not 1 <= entry['bytes'] <= 100 * 1024 * 1024):
                raise ValueError()
            item = layout.resource(PREFIX + name)
            if item.stat().st_size != entry['bytes'] or hashlib.sha256(item.read_bytes()).hexdigest() != expected:
                raise ValueError()
        sources = value['source_inputs']
        if (not isinstance(sources, dict) or set(sources) != SOURCE_INPUTS
                or any(not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha) for sha in sources.values())):
            raise ValueError()
        executable = root / 'flac.exe'
        for name in ('flac.exe', 'FLAC.dll'):
            with (root / name).open('rb') as stream:
                header = stream.read(64); offset = struct.unpack_from('<I', header, 60)[0]
                stream.seek(offset); pe = stream.read(26)
            if header[:2] != b'MZ' or pe[:4] != b'PE\0\0' or pe[4:6] != b'\x64\x86' or pe[24:26] != b'\x0b\x02':
                raise ValueError()
        return FlacDecoder(layout, value, executable)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, struct.error, RuntimeBundleError) as error:
        raise _failure('The experimental codec is missing, changed or incompatible. Re-extract a verified candidate; no PATH, download or development fallback was used.') from error
