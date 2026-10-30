"""One verified experimental codec and fixed decode operation; no tool discovery.

This does not approve FFmpeg redistribution or enable the general game/audio
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

PREFIX = 'codecs/ffmpeg-flac/'
SCHEMA = 'proxy-experimental-codec-v1'
ARCHIVE_SHA256 = '02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a'
EXECUTABLE_SHA256 = '2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3'
PINNED_FILES = {
    'ffmpeg.exe': EXECUTABLE_SHA256,
    'notices/IMAGEIO-LICENSE.txt': 'eca73421d0c905a92e952a553d4d58919c5a507c2c2c76e3c0cf9ba408c299e4',
    'notices/FFMPEG-GPLv3.txt': '8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903',
    'notices/FFMPEG-LICENSE.md': 'cb48bf09a11f5fb576cddb0431c8f5ed0a60157a9ec942adffc13907cbe083f2',
}
SOURCE_INPUTS = {'packaging/codecs/ffmpeg-flac.json', 'scripts/prepare-runtime-codec.py', 'backend/prebuilt_codecs.py'}
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
            command = [str(self.executable), '-nostdin', '-hide_banner', '-loglevel', 'error', '-nostats',
                '-xerror', '-err_detect', 'explode', '-y', '-protocol_whitelist', 'file', '-f', 'flac', '-i', str(source),
                '-map', '0:a:0', '-vn', '-sn', '-dn', '-threads', '1', '-filter_threads', '1',
                '-c:a', 'pcm_s16le', '-ac', '1', '-ar', '16000', '-t', '1', '-fs', '32000', '-f', 's16le', str(pending)]
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
        if (value.get('schema') != SCHEMA or value.get('kind') != 'ffmpeg-flac-experiment'
                or value.get('platform') != 'win-x64' or value.get('version') != '7.1'
                or value.get('source_commit') != layout.source_commit or value.get('source_dirty') is not False
                or value.get('archive_sha256') != ARCHIVE_SHA256 or value.get('entry') != 'ffmpeg.exe'
                or value.get('policy') != POLICY or value.get('production_execution_allowed') is not False
                or value.get('redistribution_review') != 'pending-exact-output'
                or value.get('source_delivery_review') != 'open' or value.get('servicing_review') != 'open'
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
        executable = root / 'ffmpeg.exe'
        # The actual executable hash is pinned above; inspect PE architecture too.
        with executable.open('rb') as stream:
            header = stream.read(64); offset = struct.unpack_from('<I', header, 60)[0]
            stream.seek(offset); pe = stream.read(26)
        if header[:2] != b'MZ' or pe[:4] != b'PE\0\0' or pe[4:6] != b'\x64\x86' or pe[24:26] != b'\x0b\x02':
            raise ValueError()
        return FlacDecoder(layout, value, executable)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, struct.error, RuntimeBundleError) as error:
        raise _failure('The experimental codec is missing, changed or incompatible. Re-extract a verified candidate; no PATH, download or development fallback was used.') from error
