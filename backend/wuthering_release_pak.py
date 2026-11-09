"""Selective reads of released Kuro Windows v12 PAK directories and individual entries."""
import hashlib
import io
import json
from functools import lru_cache
import shutil
import struct
import subprocess
import urllib.request
import zlib

from Crypto.Cipher import AES

from .game_tools import CODE_ROOT, _atomic_file
from .preparation_errors import PreparationFailure

LIMIT = 64 * 1024**2
MEMBER_LIMIT = 512 * 1024**2
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


@lru_cache(maxsize=1)
def _ooz_runtime():
    from .prebuilt_node_reader import require_zzz_reader
    reader = require_zzz_reader()
    if reader is not None:
        return reader.executable, reader.root / 'dependencies/ooz/index.js'
    node = shutil.which('node')
    module = CODE_ROOT / 'node_modules/ooz-wasm'
    policy = json.loads((CODE_ROOT / 'packaging/zzz-reader/inputs.json').read_bytes())
    expected = policy['npm']['ooz-wasm']['runtime_sha256']
    for name in ('package.json', 'index.js', 'build/ooz.js'):
        file = module / name
        if not node or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected[name]:
            raise PreparationFailure('missing_decoder', 'Prepare Node and the pinned ooz-wasm dependency for Wuthering playback.')
    return node, module / 'index.js'


def _oodle(blocks):
    from .prebuilt_node_reader import PrebuiltNodeReader
    node, module = _ooz_runtime()
    # Run the toolkit's source-built decoder outside the desktop process. All
    # input lengths and the total output have been bounded by the PAK reader.
    program = """
        import {readFileSync} from 'node:fs';
        const {decompress} = await import(process.argv[1]);
        const input = readFileSync(0);
        for (let pos = 0; pos < input.length;) {
            const packed = input.readUInt32LE(pos), size = input.readUInt32LE(pos + 4);
            pos += 8;
            process.stdout.write(decompress(input.subarray(pos, pos + packed), size));
            pos += packed;
        }
    """
    data = b''.join(struct.pack('<II', len(part), size) + part for part, size in blocks)
    result = subprocess.run([str(node), '--input-type=module', '-e', program, module.as_uri()],
                            input=data, capture_output=True, timeout=120, env=PrebuiltNodeReader.environment(),
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    check(result.returncode == 0 and len(result.stdout) == sum(size for _, size in blocks))
    return result.stdout


def _decompress(data, header, method, count, block_size, size, stored, encrypted, block_lengths):
    header_size = len(header)
    check(struct.unpack_from('<I', header, 48)[0] == count and block_size > 0
          and (size + block_size - 1) // block_size == count)
    position = 0
    blocks = []
    for index in range(count):
        start, end = struct.unpack_from('<QQ', header, 52 + 16 * index)
        start -= header_size
        end -= header_size
        check(start == position and start < end <= stored)
        if block_lengths:
            check(end - start == block_lengths[index])
        blocks.append((data[start:end], min(block_size, size - index * block_size)))
        position = (end + 15) // 16 * 16 if encrypted else end
    check(position == len(data))
    if method == b'Oodle':
        return _oodle(blocks)
    output = bytearray()
    for packed, expected in blocks:
        decoder = zlib.decompressobj()
        part = decoder.decompress(packed, expected + 1)
        check(decoder.eof and not decoder.unused_data and len(part) == expected)
        output.extend(part)
    return bytes(output)


class Package:
    def __init__(self, url, size, identity, cache, parameters):
        self.url, self.size = url, size
        check(size >= 64)
        self.cache = cache / 'kuro-package-index' / identity
        tail = min(512, size)
        footer = self.range(size - tail, tail)
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

    def locations(self, *, wanted=(), prefix=None):
        reader = io.BytesIO(self.directory)
        directories = number(reader)
        check(0 <= directories <= 2_000_000)
        found = {}
        for _ in range(directories):
            directory = self.mount + string(reader).lstrip('/')
            count = number(reader)
            check(0 <= count <= 2_000_000)
            for _ in range(count):
                name = directory + string(reader)
                position = number(reader)
                if name in wanted or (prefix is not None and name.startswith(prefix)):
                    check(name not in found)
                    found[name] = position
        return found

    def member(self, wanted):
        found = self.locations(wanted={wanted})
        if wanted not in found:
            return None
        check(found[wanted] >= 0)
        return self.extract(found[wanted])

    def extract(self, position):
        # Kuro v12 stores the encoded entry's length and offset in swapped slots.
        reader = io.BytesIO(self.entries)
        reader.seek(position)
        bits = number(reader, 'I')
        flags = ((bits >> 16) & 63 | (bits & 65535) << 6 | (bits & 0x10000000) >> 6 |
                 (bits & 0x0fc00000) << 1 | (bits & 0xc0000000) >> 1 | (bits & 0x20000000) << 2)
        custom = number(reader, 'B')
        block_size = number(reader, 'I') if flags & 63 == 63 else (flags & 63) << 11
        size = number(reader, 'I' if flags & (1 << 31) else 'Q')
        offset = number(reader, 'I' if flags & (1 << 30) else 'Q')
        method = (flags >> 23) & 63
        stored = number(reader, 'I' if flags & (1 << 29) else 'Q') if method else size
        blocks = (flags >> 6) & 65535
        encrypted = bool(flags & (1 << 22))
        check(0 < size <= MEMBER_LIMIT and 0 < stored <= MEMBER_LIMIT and custom in (0, 1, 2, 4))
        check((method == 0 and not blocks) or
              (0 < method < len(self.methods) and self.methods[method] in (b'Zlib', b'Oodle') and blocks > 0))
        block_lengths = [number(reader, 'I') for _ in range(blocks)] if blocks > 1 else []
        header_size = 53 + (4 + 16 * blocks if method else 0)
        header = self.range(offset, header_size)
        check(struct.unpack_from('<QQI', header, 8) == (stored, size, method))
        length = (stored + 15) // 16 * 16 if encrypted else stored
        data = b''.join(self.range(offset + header_size + part, min(LIMIT, length - part))
                        for part in range(0, length, LIMIT))
        protected = min(length, {0: length, 1: 0x200000, 2: 0x800, 4: 0}[custom]) if encrypted else length
        # Compressed entries cover the full stored representation including
        # inter-block padding. Raw entries cover the unpadded encrypted prefix.
        hashed = stored if method else min(stored, protected)
        check(hashlib.sha1(data[:hashed]).digest() == header[28:48])
        if encrypted and protected:
            check(self.cipher is not None)
            data = self.cipher.decrypt(data[:protected]) + data[protected:]
        if method:
            return _decompress(data, header, self.methods[method], blocks, size if blocks == 1 else block_size,
                               size, stored, encrypted, block_lengths)
        return data[:size]
