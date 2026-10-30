"""Guard the remaining development-only executable acquisition operations.

Packaged capabilities are resolved by their immutable-resource adapters. This
guard is only for a source compiler/downloader with no packaged implementation.
It does not disable unrelated readers or the common audio runtime.
"""
from .runtime_bundle import discover_layout
from .preparation_errors import PreparationFailure


def require_source_toolchain(component: str) -> None:
    if discover_layout().mode == 'bundle':
        raise PreparationFailure('bundle_toolchain_unavailable',
            f'This installation does not include the {component} runtime. '
            'Install a complete toolkit package for this platform, then retry. '
            'No developer compiler or executable download was started.')
