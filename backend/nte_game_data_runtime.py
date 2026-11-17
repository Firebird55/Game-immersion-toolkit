"""Explicit offline Windows reader capability for context-owned NTE preparation.

This is the existing owned apphost/dependency contract, not a compiler or a
download callback. Original publisher executables remain input data only.
"""
from dataclasses import dataclass
from pathlib import Path

from .game_data_protocol import GameDataError
from .private_data_paths import _no_links


OPERATIONS = frozenset(('publisher-dialogue-inventory', 'publisher-tables'))


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


def resolve(platform, context, *, layout=None):
    """No Windows helper fallback on Android, and no implicit preparation."""
    context.check()
    if platform != 'windows':
        raise _failure()
    from .nte_toolchain import resolve as resolve_chain
    from .prebuilt_readers import prebuilt_reader
    from .preparation_errors import PreparationFailure
    from .runtime_bundle import discover_layout, RuntimeBundleError
    import hashlib
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
