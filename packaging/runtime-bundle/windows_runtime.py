"""Keep native Windows runtime dependencies inside the observed suppliers."""
import base64
import hashlib
from importlib import metadata
from pathlib import Path


def supplier_msvc(distribution=None):
    distribution = distribution or metadata.distribution('PySide6-Essentials')
    records = [entry for entry in distribution.files or [] if str(entry).replace('\\', '/') == 'PySide6/msvcp140.dll']
    if len(records) != 1 or records[0].hash is None or records[0].hash.mode != 'sha256':
        raise ValueError('The locked Qt supplier has no exact MSVC runtime RECORD entry.')
    path = Path(distribution.locate_file(records[0])).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('The supplier MSVC runtime cannot traverse links.')
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').digest()
    if base64.urlsafe_b64encode(actual).decode().rstrip('=') != records[0].hash.value:
        raise ValueError('The supplier MSVC runtime differs from the observed wheel.')
    return path


def select_msvc(binaries, *, distribution=None):
    """Replace host-discovered copies with the verified Qt wheel copy.

    PyInstaller can select System32's newer DLL during dependency analysis.
    Every destination remains the same; both isolated process trees use one
    recorded supplier instead of depending on the build PC's redist version.
    The actual Qt and ASR frozen startup probes remain required.
    """
    if not any(Path(entry[0]).name.casefold() == 'msvcp140.dll' for entry in binaries):
        return binaries
    source = str(supplier_msvc(distribution))
    return [(entry[0], source, *entry[2:]) if Path(entry[0]).name.casefold() == 'msvcp140.dll' else entry
            for entry in binaries]
