"""Acquire the pinned original Windows NDK for the Android source build."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile


def prepare(work, sdk):
    if os.name != 'nt':
        raise ValueError('This compiler supplier is the Windows source-build host')
    pin = json.loads((Path(__file__).resolve().parents[1] / 'packaging/android/python-dependencies.json').read_text())
    work, sdk = Path(work).absolute(), Path(sdk).absolute()
    work.mkdir(parents=True, exist_ok=True)
    archive = work / pin['ndk']['source'].rsplit('/', 1)[1]
    if not archive.is_file():
        pending = archive.with_suffix('.pending')
        try:
            with urllib.request.urlopen(pin['ndk']['source'], timeout=60) as source, pending.open('xb') as output:
                total = 0
                while block := source.read(1024 * 1024):
                    total += len(block)
                    if total > pin['ndk']['size']:
                        raise ValueError('NDK supplier exceeds the pinned size')
                    output.write(block)
            pending.replace(archive)
        finally:
            pending.unlink(missing_ok=True)
    with archive.open('rb') as source:
        if archive.stat().st_size != pin['ndk']['size'] or hashlib.file_digest(source, 'sha256').hexdigest() != pin['ndk']['sha256']:
            raise ValueError('NDK supplier checksum mismatch')
    destination = sdk / 'ndk' / pin['ndk_revision']
    if not destination.is_dir():
        parent = sdk / 'ndk';parent.mkdir(parents=True, exist_ok=True)
        staging = parent / ('pending-' + str(os.getpid()))
        with zipfile.ZipFile(archive) as source:
            entries = source.infolist()
            if len(entries) > 50000 or sum(entry.file_size for entry in entries) > 6 * 1024**3:
                raise ValueError('NDK archive is outside the documented inventory')
            for entry in entries:
                name = PurePosixPath(entry.filename)
                if (name.is_absolute() or not name.parts or name.parts[0] != 'android-ndk-r27d'
                        or '\\' in entry.filename or ':' in entry.filename or '..' in name.parts
                        or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError('Unsafe NDK archive member')
            source.extractall(staging)
        (staging / 'android-ndk-r27d').replace(destination)
        staging.rmdir()
    # The builder subsequently compares all compiler/sysroot bytes to this
    # authenticated archive; an installed SDK version label is insufficient.
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--sdk-root', type=Path, required=True)
    arguments = parser.parse_args()
    print(prepare(arguments.work_dir, arguments.sdk_root))
