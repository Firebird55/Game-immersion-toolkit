"""Passive original Wuthering source identity and selected-module readers.

No network, protected storage, source registry or desktop discovery is used here.
Callers authenticate the complete APK before accepting a selected module, then
validate complete original PAK indices before authorizing a derived candidate.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
from urllib.parse import unquote, urlsplit
import zlib

from .wuthering_elf_bootstrap import MAX_MODULE, default_output


POLICY = 'kuro-official-arm64-default/1'


CATALOGUE = ('https://download.kurogames.com/'
             'mc_WnGtDn85y8lJB4mTmYHYuNjIl9n6YGVm/official/cn/zh-Hans/android_app.json')


MAX_METADATA = 2 * 1024**2


def _check(value):
    if not value:
        raise ValueError('Unsupported or inconsistent original Wuthering bootstrap source.')


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _file_hash(path, *, check=lambda: None):
    check()
    _check(not path.is_symlink())
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024**2), b''):
            check()
            digest.update(part)
    return digest.hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _url(value):
    _check(isinstance(value, str) and len(value) <= 4096)
    u = urlsplit(value)
    _check(u.scheme == 'https' and u.netloc == u.hostname and not u.fragment and not u.query and
           re.fullmatch(r'[a-z0-9-]+\.aki-game\.com', u.hostname or '') and
           u.path.startswith('/client/download/') and unquote(u.path).endswith('.apk') and
           '..' not in unquote(u.path).split('/'))
    return value


def reference(value):
    _check(isinstance(value, dict) and set(value) == {
        'policy', 'catalogue', 'catalogue_sha256', 'version', 'url', 'bytes', 'etag', 'apk_sha256', 'v2_digest', 'signers', 'module'})
    _check(value['policy'] == POLICY and value['catalogue'] == CATALOGUE and
           re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value['version']) and
           type(value['bytes']) is int and 0 < value['bytes'] <= 4 * 1024**3 and
           isinstance(value['etag'], str) and 0 < len(value['etag']) <= 256)
    _url(value['url'])
    for name in ('apk_sha256', 'v2_digest', 'catalogue_sha256'):
        _check(isinstance(value[name], str) and re.fullmatch('[0-9a-f]{64}', value[name]))
    _check(isinstance(value['signers'], list) and 1 <= len(value['signers']) <= 8 and
           all(isinstance(x, str) and re.fullmatch('[0-9a-f]{64}', x) for x in value['signers']))
    m = value['module']
    _check(isinstance(m, dict) and set(m) == {'name', 'sha256', 'compressed_sha256', 'compressed_bytes', 'plain_bytes', 'crc32'} and
           re.fullmatch(r'lib/arm64-v8a/lib[A-Za-z0-9_]+\.so', m['name']) and
           type(m['plain_bytes']) is int and 0 < m['plain_bytes'] <= MAX_MODULE and
           type(m['compressed_bytes']) is int and 0 < m['compressed_bytes'] < value['bytes'] and
           re.fullmatch('[0-9a-f]{8}', m['crc32']) and
           all(isinstance(m[k], str) and re.fullmatch('[0-9a-f]{64}', m[k]) for k in ('sha256', 'compressed_sha256')))
    return json.loads(_canonical(value))


def identity(value):
    return _hash(_canonical(reference(value)))


def _root(tools):
    return Path(tools) / 'wuwa-publisher' / 'native-bootstrap'


def _module(tools, source):
    return _root(tools) / 'modules' / source['module']['sha256'] / 'module.so'


def _library(axml):
    _check(len(axml) >= 8 and struct.unpack_from('<HHI', axml) == (3, 8, len(axml)))
    strings, stack, libraries = [], [], []
    package = None

    def text(index):
        _check(0 <= index < len(strings))
        return strings[index]

    def length(at, wide):
        x = struct.unpack_from('<H' if wide else '<B', axml, at)[0]
        bit, width = (32768, 2) if wide else (128, 1)
        if x & bit:
            y = struct.unpack_from('<H' if wide else '<B', axml, at + width)[0]
            return ((x & (bit - 1)) << (16 if wide else 8)) | y, at + width * 2
        return x, at + width

    at = 8
    while at < len(axml):
        kind, header, size = struct.unpack_from('<HHI', axml, at)
        _check(8 <= header <= size and at + size <= len(axml))
        if kind == 1:
            count, _, flags, start, _ = struct.unpack_from('<5I', axml, at + 8)
            _check(not strings and 0 < count <= 65536 and header >= 28 and header + count * 4 <= size)
            for i in range(count):
                pos = at + start + struct.unpack_from('<I', axml, at + header + i * 4)[0]
                _, pos = length(pos, not bool(flags & 256))
                if flags & 256:
                    n, pos = length(pos, False)
                    strings.append(axml[pos:pos + n].decode('utf8'))
                    _check(pos + n < at + size and axml[pos + n] == 0)
                else:
                    n, _ = length(at + start + struct.unpack_from('<I', axml, at + header + i * 4)[0], True)
                    strings.append(axml[pos:pos + n * 2].decode('utf-16le'))
                    _check(pos + n * 2 + 2 <= at + size and axml[pos + n * 2:pos + n * 2 + 2] == b'\0\0')
        elif kind == 0x102:
            _, name, attr_start, attr_size, count = struct.unpack_from('<IIHHH', axml, at + 16)
            name, attrs = text(name), {}
            _check(attr_size == 20)
            for i in range(count):
                pos = at + 16 + attr_start + i * 20
                _check(pos + 20 <= at + size)
                namespace, key, raw = struct.unpack_from('<III', axml, pos)
                value_size, zero, typ, value = struct.unpack_from('<HBBI', axml, pos + 12)
                _check(value_size == 8 and zero == 0)
                namespace = None if namespace == 0xffffffff else text(namespace)
                key = ('android:' if namespace == 'http://schemas.android.com/apk/res/android' else
                       namespace + ':' if namespace is not None else '') + text(key)
                _check(key not in attrs)
                attrs[key] = text(raw) if raw != 0xffffffff else text(value) if typ == 3 else None
            if name == 'manifest':
                _check(package is None)
                package = attrs.get('package')
            if name == 'meta-data' and attrs.get('android:name') == 'android.app.lib_name':
                _check(any(x[0] == 'activity' and x[1].get('android:name') == 'com.epicgames.ue4.GameActivity' for x in stack))
                libraries.append(attrs.get('android:value'))
            stack.append((name, attrs))
        elif kind == 0x103:
            name, = struct.unpack_from('<I', axml, at + 20)
            _check(stack and stack.pop()[0] == text(name))
        at += size
    _check(at == len(axml) and not stack and package == 'com.kurogame.mingchao' and len(libraries) == 1 and
           isinstance(libraries[0], str) and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,127}', libraries[0]))
    return 'lib/arm64-v8a/lib' + libraries[0] + '.so'


def _decode_module(compressed, decoded, entry, *, check=lambda: None):
    """The same bounded passive Deflate/CRC loop for ordinary and staged IO."""
    _check(type(entry['plain']) is int and 0 < entry['plain'] <= MAX_MODULE and
           type(entry['packed']) is int and 0 < entry['packed'] <= 4 * 1024**3 and
           compressed.stat().st_size == entry['packed'])
    decoder, size, crc, digest, stored = zlib.decompressobj(-15), 0, 0, hashlib.sha256(), hashlib.sha256()
    with compressed.open('rb') as src, decoded.open('xb') as dst:
        for part in iter(lambda: src.read(65536), b''):
            check()
            stored.update(part)
            pending = part
            while pending:
                check()
                value = decoder.decompress(pending, min(1024**2, entry['plain'] - size + 1))
                previous, pending = len(pending), decoder.unconsumed_tail
                _check(value or len(pending) < previous)
                size += len(value)
                _check(size <= entry['plain'] and not decoder.unused_data)
                dst.write(value)
                crc = zlib.crc32(value, crc)
                digest.update(value)
        _check(not decoder.flush() and decoder.eof and not decoder.unused_data and size == entry['plain'] and
               crc & 0xffffffff == entry['crc'])
    return size, crc & 0xffffffff, digest.hexdigest(), stored.hexdigest()
