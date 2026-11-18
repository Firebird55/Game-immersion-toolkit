"""Verified fixed XXH3 software; original game strings remain private inputs."""
from functools import lru_cache
import hashlib
import importlib
import importlib.metadata
import importlib.util
from pathlib import Path
import platform
import struct
import sys

VERSION = '4.1.0'
NATIVE_SHA256 = 'b93a04ab5bf2fdb05b3d000d56a42c000f4f2353aa78a431bdbed7463957e137'
NOTICE_SHA256 = 'b76e99529f3e47372029e11914a8f4b95d6313463ed5a1a5c9afe96c3e015114'


def check(condition, reason='Unsupported original-parameter hash input.'):
    if not condition:
        raise ValueError(reason)


@lru_cache(maxsize=1)
def implementation():
    check(sys.platform == 'win32' and sys.version_info[:2] == (3, 12) and
          platform.machine().lower() in {'amd64', 'x86_64'} and struct.calcsize('P') == 8,
          'Original Endfield parameter preparation requires a Windows amd64 Python 3.12 runtime.')
    try:
        dist = importlib.metadata.distribution('xxhash')
        spec = importlib.util.find_spec('xxhash')
        check(dist.version == VERSION and spec and spec.origin,
              'The pinned original-parameter hash implementation is unavailable.')
        package = Path(spec.origin).resolve().parent
        native = package / '_xxhash.cp312-win_amd64.pyd'
        notice = Path(dist.locate_file('xxhash-4.1.0.dist-info/licenses/LICENSE'))
        check(native.is_file() and native.stat().st_size <= 2 * 1024**2 and
              hashlib.sha256(native.read_bytes()).hexdigest() == NATIVE_SHA256 and
              notice.is_file() and notice.stat().st_size <= 64 * 1024 and
              hashlib.sha256(notice.read_bytes()).hexdigest() == NOTICE_SHA256,
              'The pinned original-parameter hash library or its notice differs.')
        module = importlib.import_module('xxhash')
        loaded = importlib.import_module('xxhash._xxhash')
        check(Path(loaded.__file__).resolve() == native.resolve() and
              module.VERSION == VERSION and module.xxh3_64_intdigest(b'') == 0x2d06800538d394c2,
              'The loaded original-parameter hash implementation differs.')
        return module.xxh3_64_intdigest
    except (OSError, ImportError, importlib.metadata.PackageNotFoundError) as error:
        raise ValueError('Repair the pinned original-parameter hash dependency.') from error


def hash64(data, *, hashing=None):
    check(isinstance(data, bytes) and len(data) <= 4096)
    if hashing is not None:
        from .android_publisher_hash import AndroidPublisherHash
        check(type(hashing) is AndroidPublisherHash)
        return hashing.xxh3_64(data)
    return implementation()(data)
