"""Selective reads of released Kuro Windows v12 PAK directories and individual entries."""
import hashlib
import io
import struct
import urllib.request
import zlib

from Crypto.Cipher import AES

from .game_tools import _atomic_file

LIMIT = 64 * 1024**2
MAGIC = b'\xe1\x12\x6f\x5a'


def check(condition):
    if not condition:
        raise ValueError('Unsupported or inconsistent Kuro publisher package.')


def block(url, total, offset, size):
    check(0 < size <= LIMIT and 0 <= offset <= total - size)
    end = offset + size - 1
    request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-{end}', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(request, timeout=45) as response:
        check(response.status == 206 and response.geturl() == url and
              response.headers.get('Content-Range') == f'bytes {offset}-{end}/{total}')
        data = response.read(size + 1)
    check(len(data) == size)
    return data


def number(reader, layout='i'):
    fmt = '<' + layout
    data = reader.read(struct.calcsize(fmt))
    check(len(data) == struct.calcsize(fmt))
    return struct.unpack(fmt, data)[0]


def string(reader):
    length = number(reader)
    check(-4096 <= length <= 8192)
    if length == 0:
        return ''
    size, terminator, encoding = ((length, b'\0', 'utf8') if length > 0 else
                                   (-2 * length, b'\0\0', 'utf-16le'))
    raw = reader.read(size)
    check(len(raw) == size and raw.endswith(terminator))
    return raw[:-len(terminator)].decode(encoding)


class Package:
    def __init__(self, url, size, identity, cache, parameters):
        self.url, self.size = url, size
        check(size > 512)
        self.cache = cache / 'kuro-package-index' / identity
        footer = self.range(size - 512, 512)
        magic = footer.rfind(MAGIC)
        check(1 <= magic <= len(footer)-108)
        version, offset, length = struct.unpack_from('<IQQ', footer, magic+4)
        check(version == 12 and footer[magic-1] in (0, 1))
        self.cipher = None
        if footer[magic-1]:
            sample = self.range(offset, 16)
            for value in parameters:
                candidate = AES.new(value, AES.MODE_ECB)
                if candidate.decrypt(sample)[4:7] == b'../':
                    self.cipher = candidate
                    break
            check(self.cipher is not None)
        self.methods = [b'None'] + [footer[i:i+32].split(b'\0')[0]
                                    for i in range(magic+44, len(footer)-31, 32)]
        main = io.BytesIO(self.index(offset, length, footer[magic+24:magic+44]))
        mount = string(main)
        check(mount.startswith('../../../'))
        self.mount = mount[9:]
        count = number(main)
        check(0 <= count <= 2_000_000)
        main.seek(8, 1)
        check(number(main) == 1)
        main.seek(36, 1)
        check(number(main) == 1)
        offset, length = number(main, 'q'), number(main, 'q')
        directory_hash = main.read(20)
        encoded_size = number(main)
        check(0 <= encoded_size <= LIMIT)
        self.entries = main.read(encoded_size)
        check(len(self.entries) == encoded_size)
        self.directory = self.index(offset, length, directory_hash)

    def range(self, offset, size):
        return block(self.url, self.size, offset, size)

    def index(self, offset, size, digest):
        check(0 < size <= LIMIT and len(digest) == 20)
        path = self.cache / digest.hex()
        if path.is_file() and path.stat().st_size == size:
            data = path.read_bytes()
            if hashlib.sha1(data).digest() == digest:
                return data
        data = self.range(offset, size)
        if self.cipher:
            data = self.cipher.decrypt(data)
        check(hashlib.sha1(data).digest() == digest)
        _atomic_file(path, data)
        return data

    def member(self, wanted):
        reader = io.BytesIO(self.directory)
        directories = number(reader)
        check(0 <= directories <= 2_000_000)
        found = None
        for _ in range(directories):
            directory = self.mount + string(reader).lstrip('/')
            count = number(reader)
            check(0 <= count <= 2_000_000)
            for _ in range(count):
                name = directory + string(reader)
                position = number(reader)
                if name == wanted:
                    check(found is None and position >= 0)
                    found = position
        if found is None:
            return None
        return self.extract(found)

    def extract(self, position):
        # Kuro v12 stores the encoded entry's length and offset in swapped slots.
        reader = io.BytesIO(self.entries)
        reader.seek(position)
        bits = number(reader, 'I')
        flags = ((bits >> 16) & 63 | (bits & 65535) << 6 | (bits & 0x10000000) >> 6 |
                 (bits & 0x0fc00000) << 1 | (bits & 0xc0000000) >> 1 | (bits & 0x20000000) << 2)
        custom = number(reader, 'B')
        if flags & 63 == 63:
            reader.seek(4, 1)
        size = number(reader, 'I' if flags & (1 << 31) else 'Q')
        offset = number(reader, 'I' if flags & (1 << 30) else 'Q')
        method = (flags >> 23) & 63
        stored = number(reader, 'I' if flags & (1 << 29) else 'Q') if method else size
        blocks = (flags >> 6) & 65535
        encrypted = bool(flags & (1 << 22))
        check(0 < size <= LIMIT and 0 < stored <= LIMIT and custom in (0, 1, 2, 4))
        check((method == 0 and not blocks) or
              (0 < method < len(self.methods) and self.methods[method] == b'Zlib' and blocks == 1))
        header_size = 53 + (4 + 16 * blocks if method else 0)
        header = self.range(offset, header_size)
        check(struct.unpack_from('<QQI', header, 8) == (stored, size, method))
        length = (stored + 15) // 16 * 16 if encrypted else stored
        data = self.range(offset + header_size, length)
        protected = min(length, {0: length, 1: 0x200000, 2: 0x800, 4: 0}[custom]) if encrypted else length
        check(hashlib.sha1(data[:protected]).digest() == header[28:48])
        if encrypted and protected:
            check(self.cipher is not None)
            data = self.cipher.decrypt(data[:protected]) + data[protected:]
        if method:
            count, start, end = struct.unpack_from('<IQQ', header, 48)
            check(count == 1 and start == header_size and 0 < end-start <= stored)
            decoder = zlib.decompressobj()
            data = decoder.decompress(data[:end-start], size + 1)
            check(decoder.eof and len(data) == size)
        return data[:size]
