"""Explicit offline Windows reader capability for context-owned NTE preparation.

This is the existing owned apphost/dependency contract, not a compiler or a
download callback. Original publisher executables remain input data only.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import secrets
import subprocess
import tempfile
import time

from .game_data_protocol import GameDataError
from .private_data_paths import _no_links


OPERATIONS = frozenset(('publisher-dialogue-inventory', 'publisher-tables', '--decode-oodle'))


def _failure():
    return GameDataError('nte_reader_unavailable',
        'This application does not include a compatible NTE data reader. Your previous library is retained.', 409)


@dataclass(frozen=True)
class WindowsNteRuntime:
    """Explicit host selection of the existing immutable application resources."""
    layout: object

    def reader(self, context):
        return resolve('windows', context, layout=self.layout)


@dataclass(frozen=True)
class NteGameDataReader:
    context: object
    layout: object
    executable: Path
    source_identity: str
    dependency_identity: str

    @property
    def identity(self):
        return {'kind': 'nte-owned-windows-reader-v1', 'source_sha256': self.source_identity,
                'dependencies_sha256': self.dependency_identity}

    def invocation(self, source, destination, operation):
        """Return the verified owned command, confined to this preparation."""
        if operation not in OPERATIONS:
            raise _failure()
        ctx = self.context
        ctx.check()
        source, destination = Path(source), Path(destination)
        cache, working = Path(ctx.cache_directory), Path(ctx.directory)
        for path in (source, destination, cache, working):
            _no_links(path)
            if not path.is_absolute() or path != path.resolve():
                raise _failure()
        if (source == cache or not source.is_relative_to(cache)
                or destination == working or not destination.is_relative_to(working)):
            raise _failure()
        # Resolve the whole closed chain again immediately before invocation.
        # Missing/changed native or managed dependencies do not start a download.
        refreshed = resolve('windows', ctx, layout=self.layout)
        if refreshed.identity != self.identity or refreshed.executable != self.executable:
            raise _failure()
        from .nte_toolchain import command
        result = command(source, destination, operation, layout=self.layout)
        if result[0][0] != str(self.executable):
            raise _failure()
        ctx.check()
        return result

    def codec_specification(self):
        from .runtime_bundle import RuntimeBundleError
        try:
            return self._codec_specification()
        except (OSError, ValueError, KeyError, TypeError, RuntimeBundleError) as error:
            raise _failure() from error

    def _codec_specification(self):
        from .nte_toolchain import PREFIX, DEPENDENCIES
        path = self.layout.resource(PREFIX+'notices/MANAGED-COMPONENTS.json')
        if path.stat().st_size > 256*1024:
            raise _failure()
        packet = json.loads(path.read_bytes())
        if (not isinstance(packet, dict) or packet.get('supplier_sha256') != DEPENDENCIES['UEExtractor.dll']
                or not isinstance(packet.get('components'), list) or len(packet['components']) > 128):
            raise _failure()
        components = [value for value in packet['components'] if isinstance(value, dict) and value.get('name') == 'OodleSharp']
        if (len(components) != 1 or not isinstance(components[0].get('sha256'), str)
                or len(components[0]['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in components[0]['sha256'])):
            raise _failure()
        return {'supplier_sha256': packet['supplier_sha256'], 'codec_sha256': components[0]['sha256']}

    def oodle(self, blocks):
        """Decode already authenticated bytes; no tools, game or network reads."""
        if (not isinstance(blocks, (list, tuple)) or not 0 < len(blocks) <= 65535):
            raise _failure()
        result, batch, packed, raw, total = [], [], 0, 0, 0
        for item in blocks:
            if (not isinstance(item, (list, tuple)) or len(item) != 2 or not isinstance(item[0], bytes)
                    or not 0 < len(item[0]) <= 4*1024**2 or type(item[1]) is not int or not 0 < item[1] <= 128*1024**2):
                raise _failure()
            total += item[1]
            if total > 512*1024**2:
                raise _failure()
            if batch and (len(batch) == 512 or packed+len(item[0]) > 8*1024**2 or raw+item[1] > 128*1024**2):
                result.append(self._oodle_batch(batch)); batch, packed, raw = [], 0, 0
            batch.append(item); packed += len(item[0]); raw += item[1]
        if batch:
            result.append(self._oodle_batch(batch))
        return b''.join(result)

    def _oodle_batch(self, blocks):
        ctx = self.context; ctx.check()
        specification = self.codec_specification()
        cache, work = Path(ctx.cache_directory), Path(ctx.directory)
        _no_links(cache); _no_links(work)
        with tempfile.TemporaryDirectory(prefix='nte-oodle-input-', dir=cache) as input_name, \
                tempfile.TemporaryDirectory(prefix='nte-oodle-output-', dir=work) as output_name:
            source, destination = Path(input_name), Path(output_name)
            data = b''.join(data for data, _ in blocks)
            (source/'block.bin').write_bytes(data)
            packet = {'schema': 'nte-managed-oodle-v1', 'nonce': secrets.token_hex(16),
                'stored_bytes': len(data), 'raw_bytes': sum(size for _, size in blocks),
                'stored_sha256': hashlib.sha256(data).hexdigest(), **specification,
                'blocks': [{'stored_bytes': len(data), 'raw_bytes': size} for data, size in blocks]}
            command, environment, working = self.invocation(source, destination, '--decode-oodle')
            ctx.check()
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=working, env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            request = json.dumps(packet, separators=(',', ':')).encode('ascii')
            started = time.monotonic()
            try:
                while True:
                    ctx.check()
                    if time.monotonic()-started > 60:
                        raise GameDataError('nte_decoder_timeout', 'The NTE package decoder did not finish. Your previous library is retained.', 409)
                    try:
                        process.communicate(input=request, timeout=.1)
                        break
                    except subprocess.TimeoutExpired:
                        request = None
                ctx.check()
                marker, raw = destination/'complete.json', destination/'decoded.bin'
                if (process.returncode or not marker.is_file() or marker.stat().st_size > 4096
                        or not raw.is_file() or raw.stat().st_size != packet['raw_bytes']):
                    raise _failure()
                _no_links(marker); _no_links(raw)
                receipt = json.loads(marker.read_bytes())
                expected = {key: packet[key] for key in ('schema', 'nonce', 'stored_bytes', 'raw_bytes', 'stored_sha256', 'codec_sha256')}
                expected['blocks'] = len(blocks)
                if not isinstance(receipt, dict) or set(receipt) != {*expected, 'raw_sha256'}:
                    raise _failure()
                result = raw.read_bytes()
                expected['raw_sha256'] = hashlib.sha256(result).hexdigest()
                if receipt != expected:
                    raise _failure()
                ctx.check()
                return result
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)


def resolve(platform, context, *, layout=None):
    """No Windows helper fallback on Android, and no implicit preparation."""
    context.check()
    if platform != 'windows':
        raise _failure()
    from .nte_toolchain import resolve as resolve_chain
    from .prebuilt_readers import prebuilt_reader
    from .preparation_errors import PreparationFailure
    from .runtime_bundle import discover_layout, RuntimeBundleError
    try:
        layout = layout or discover_layout()
        chain = resolve_chain(layout=layout)
        helper = prebuilt_reader('nte', layout=layout)
        if helper.executable != chain.executable or helper.manifest.get('platform') != 'win-x64':
            raise _failure()
        receipt = chain.dependencies/'dependencies.json'
        return NteGameDataReader(context, layout, chain.executable, helper.source_identity,
                                 hashlib.sha256(receipt.read_bytes()).hexdigest())
    except (PreparationFailure, RuntimeBundleError, OSError, ValueError) as error:
        raise _failure() from error
