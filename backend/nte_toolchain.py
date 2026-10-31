"""Verified NTE archive operations using a self-contained application helper.

The managed bridge and its separately supplied managed dependencies have
different inventories. Neither an authored probe nor a review-status string can
substitute for the actual supplier bytes. Build/distribution provenance is kept
by the resource collector; this module only resolves an already installed chain.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .node_tools import host_platform
from .prebuilt_readers import _no_links, prebuilt_reader, reader_environment
from .preparation_errors import PreparationFailure
from .runtime_bundle import discover_layout, RuntimeBundleError, relative_resource

PREFIX = 'toolchains/nte/'
SCHEMA = 'toolkit-nte-dependencies-v2'
DEPENDENCIES = {
    'UEExtractor.dll': '0076582a3edf2a3b0114b2788a8fc4814a49db2d3e6f0995713a72f915a7c1e2',
}
MODES = frozenset({'inventory', 'index', 'voice', 'voices'})


def _failure():
    return PreparationFailure('bundle_toolchain_unavailable',
        'The bundled NTE archive reader or its dependencies are missing or incompatible. '
        'Repair the application; no system SDK, compiler or executable download was started.')


def dependencies(layout) -> Path:
    """Resolve a closed, outer-inventoried dependency directory without writes."""
    try:
        root = layout.resource_root / PREFIX
        _no_links(root)
        manifest = layout.resource(PREFIX + 'dependencies.json')
        if manifest.stat().st_size > 64 * 1024:
            raise ValueError()
        value = json.loads(manifest.read_text(encoding='utf-8'))
        files = value.get('files')
        if (value.get('schema') != SCHEMA or value.get('platform') != host_platform()
                or value.get('platform') != 'win-x64' or not isinstance(files, dict)
                or not DEPENDENCIES.keys() <= files.keys() or len(files) > 128):
            raise ValueError()
        # Executables/assemblies must be exactly known. Additional source and
        # license material can only reside in the inert notices directory.
        for name, digest in files.items():
            relative_resource(name)
            if name not in DEPENDENCIES and not (name.startswith('notices/') and name.endswith(('.txt', '.md', '.json'))):
                raise ValueError()
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError()
            raw = root / name
            _no_links(raw)
            path = layout.resource(PREFIX + name)
            if path.stat().st_size > 32 * 1024 * 1024 or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError()
        if any(files.get(name) != digest for name, digest in DEPENDENCIES.items()):
            raise ValueError()
        if not {'notices/UEEXTRACTOR-LICENSE.txt', 'notices/DEPENDENCIES.md'} <= files.keys():
            raise ValueError()
        expected = {*files, 'dependencies.json'}
        if {name.removeprefix(PREFIX) for name in layout.resources if name.startswith(PREFIX)} != expected:
            raise ValueError()
        actual = set()
        for path in root.rglob('*'):
            _no_links(path)
            if path.is_file():
                actual.add(path.relative_to(root).as_posix())
            elif not path.is_dir() or path.relative_to(root).as_posix() != 'notices':
                raise ValueError()
        if actual != expected:
            raise ValueError()
        return root
    except (OSError, ValueError, KeyError, TypeError, RuntimeBundleError) as error:
        raise _failure() from error


@dataclass(frozen=True)
class NteToolchain:
    executable: Path
    dependencies: Path
    work_root: Path
    application_root: Path

    def command(self, mode, install, destination):
        """Only fixed read operations with a separate owned output directory."""
        if mode not in MODES:
            raise ValueError('Unsupported archive reader operation')
        install, destination = Path(install), Path(destination)
        for path in (install, destination):
            if not path.is_absolute() or path != path.resolve():
                raise ValueError('Archive reader paths must be explicit and normalized')
            _no_links(path)
        if not install.is_dir():
            raise ValueError('The selected game installation is unavailable')
        # Index callers write a temporary child of the game's private data root;
        # voice callers write a temporary child of the work root. The resolver
        # supplies their common private parent, never the application directory.
        if destination == self.work_root or not destination.is_relative_to(self.work_root):
            raise ValueError('Archive reader output must stay inside private application storage')
        for immutable in (install, self.dependencies, self.application_root):
            if destination == immutable or destination.is_relative_to(immutable) or immutable.is_relative_to(destination):
                raise ValueError('Archive reader output must stay separate from game and runtime files')
        return [str(self.executable), mode, str(install), str(self.dependencies), str(destination)]


def resolve(*, layout=None) -> NteToolchain:
    layout = layout or discover_layout()
    if layout.mode != 'bundle':
        raise _failure()
    helper = prebuilt_reader('nte', layout=layout)
    tools = dependencies(layout)
    # Runtime roots are independently selected; permit only explicit data/work
    # descendants in the caller, not an assumed shared filesystem ancestor.
    return NteToolchain(helper.executable, tools, layout.data_root, layout.application_root)


def command(install, destination, mode, *, layout=None):
    layout = layout or discover_layout()
    chain = resolve(layout=layout)
    destination = Path(destination)
    allowed = next((root for root in (layout.data_root, layout.work_root, layout.cache_root)
                    if destination != root and destination.is_relative_to(root)), None)
    if allowed is None:
        raise ValueError('Archive reader output must stay inside private application storage')
    chain = NteToolchain(chain.executable, chain.dependencies, allowed, chain.application_root)
    return chain.command(mode, install, destination), reader_environment(), chain.dependencies
