"""Offline publisher-signature gate using Windows system software only.

The original DLL is never loaded. Windows verifies a locked data-file handle;
cache-only verification does not claim fresh online revocation information.
Other hosts need an independently reviewed signature-verification capability.
"""
from __future__ import annotations

from pathlib import Path
import sys

from .preparation_errors import PreparationFailure

PUBLISHERS = frozenset({'GRYPH FRONTIER PTE. LTD.'})
MAX_NATIVE_MEMBER = 16 * 1024**2


def source_runtime():
    if sys.platform != 'win32':
        raise PreparationFailure('missing_toolkit_runtime',
            'Endfield original audio-parameter preparation needs a reviewed publisher-signature verifier. '
            'This toolkit currently supplies Windows offline Authenticode verification. '
            'Existing prepared data is retained.', previous_snapshot_retained=True)


def verify(path):
    source_runtime()
    return _windows(Path(path))


def _windows(path):
    from .publisher_pe_signature import verify as verify_original
    return verify_original(path, publishers=PUBLISHERS, maximum_bytes=MAX_NATIVE_MEMBER)
