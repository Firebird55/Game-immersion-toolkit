"""Explicit prototype gate: never build/download unreviewed tools in a bundle.

The source adapter keeps its existing separately acquired tools. R19 has no
accepted helper/native closure yet, so a frozen game action reports unavailable
before it can invoke npm, a compiler, SDK, NuGet or an arbitrary PATH binary.
"""
from .runtime_bundle import discover_layout
from .preparation_errors import PreparationFailure


def require_source_toolchain(component: str) -> None:
    if discover_layout().mode == 'bundle':
        raise PreparationFailure('bundle_toolchain_unavailable',
            f'This R19 diagnostic candidate has no reviewed {component} toolchain. '
            'Keep using the source runtime; a compiler or separate download does not close this bundle gate.')
