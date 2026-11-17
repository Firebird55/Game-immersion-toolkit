"""Bounded, passive APK ZIP metadata using the one shared APK-v2 verifier.

The caller supplies same-owner/generation range reads. This classic, single-disk
APK profile excludes ZIP64; selected members exclude encryption and descriptors. No network,
filesystem extraction, installation or original-library execution occurs here.
Signing metadata alone is not verification of the whole original carrier; use
publisher_apk.verify_stream before accepting a selected native source owner.
"""
import struct
import zlib

from .publisher_apk import ApkLayout, MAX_METADATA as MAX_SIGNED_METADATA


DEFAULT_METADATA = 2 * 1024**2
MAX_OWNER = 4 * 1024**3


def _check(condition):
    if not condition:
        raise ValueError('Could not verify the original APK directory or selected member metadata.')


class ApkMetadata:
    """Locate original members without fetching a large member body.

    read_range(offset,size) must return exact immutable bytes under the caller's
    transport budget. The optional signed-zero-tail dialect is strict by default
    and forwarded only to canonical ApkLayout; no second signer parser exists.
    """
    def __init__(self, read_range, total, *, allow_signed_zero_tail=False,
                 maximum_metadata=DEFAULT_METADATA, crypto=None):
        _check(callable(read_range) and type(total) is int and 22 <= total <= MAX_OWNER and
               type(maximum_metadata) is int and 0 < maximum_metadata <= 8 * 1024**2 and
               type(allow_signed_zero_tail) is bool)
        self._read_range, self.total = read_range, total
        self.maximum_metadata, self.metadata_bytes = maximum_metadata, 0
        self.witnesses = []
        tail = self.range(max(0, total - 65557), min(65557, total))
        at = len(tail)
        while True:
            at = tail.rfind(b'PK\x05\x06', 0, at)
            _check(at >= 0)
            if at + 22 <= len(tail) and struct.unpack_from('<H', tail, at + 20)[0] == len(tail) - at - 22:
                break
        self.eocd = tail[at:]
        disk, cd_disk, on_disk, count, size, offset, comment = struct.unpack_from('<4H2IH', self.eocd, 4)
        _check(disk == cd_disk == 0 and 0 < count == on_disk < 65535 and
               comment == len(self.eocd) - 22 and 0 < size <= MAX_SIGNED_METADATA and
               offset + size + len(self.eocd) == total and offset >= 24)
        tail_start = total - len(tail)
        missing = max(0, min(offset + size, tail_start) - offset)
        self.cd = self.range(offset, missing) if missing else b''
        self.cd += tail[max(offset, tail_start) - tail_start:offset + size - tail_start]
        _check(len(self.cd) == size)
        self.entries, self._raw_names = {}, {}
        position = 0
        try:
            for _ in range(count):
                _check(position + 46 <= len(self.cd) and self.cd[position:position + 4] == b'PK\x01\x02')
                flags, method = struct.unpack_from('<HH', self.cd, position + 8)
                crc, packed, plain = struct.unpack_from('<III', self.cd, position + 16)
                name_size, extra_size, comment_size, start_disk = struct.unpack_from('<4H', self.cd, position + 28)
                local, = struct.unpack_from('<I', self.cd, position + 42)
                end = position + 46 + name_size + extra_size + comment_size
                _check(end <= len(self.cd) and start_disk == 0 and
                       packed != 0xffffffff and plain != 0xffffffff and local != 0xffffffff and
                       local + 30 + packed <= offset)
                raw_name = self.cd[position + 46:position + 46 + name_size]
                name = raw_name.decode('utf-8' if flags & 2048 else 'cp437')
                _check(0 < len(raw_name) <= 4096 and name not in self.entries and
                       not name.startswith('/') and not any(c in name for c in '\0\\:') and
                       '..' not in name.split('/'))
                self.entries[name] = dict(flags=flags, method=method, crc=crc, packed=packed, plain=plain, local=local)
                self._raw_names[name] = raw_name
                position = end
            _check(position == len(self.cd))
            footer = self.range(offset - 24, 24)
            block_size, = struct.unpack_from('<Q', footer)
            _check(footer[8:] == b'APK Sig Block 42' and 24 <= block_size <= MAX_SIGNED_METADATA and
                   block_size + 8 <= offset)
            signing = offset - block_size - 8
            block = self.range(signing, block_size - 16) + footer
            self.layout = ApkLayout(total, signing, block, self.cd, self.eocd,
                                    allow_signed_zero_tail=allow_signed_zero_tail)
            self.layout.validate(crypto=crypto)
            _check(all(e['local'] + 30 + e['packed'] <= signing for e in self.entries.values()))
        except (UnicodeError, struct.error) as error:
            raise ValueError('Could not read the original APK directory fields.') from error

    def range(self, start, count):
        _check(type(start) is int and type(count) is int and 0 < count <= self.maximum_metadata and
               0 <= start <= self.total - count and self.metadata_bytes + count <= self.maximum_metadata)
        raw = self._read_range(start, count)
        _check(isinstance(raw, bytes) and len(raw) == count)
        self.metadata_bytes += count
        return raw

    def member(self, name, *, read=False, maximum=MAX_OWNER):
        _check(isinstance(name, str) and name in self.entries and type(read) is bool and
               type(maximum) is int and 0 < maximum <= MAX_OWNER)
        entry = self.entries[name]
        _check(entry['flags'] & ~2048 == 0 and entry['method'] in (0, 8) and
               0 < entry['plain'] <= maximum and (not read or entry['plain'] <= self.maximum_metadata))
        try:
            header = self.range(entry['local'], 30)
            _check(header[:4] == b'PK\x03\x04')
            flags, method = struct.unpack_from('<HH', header, 6)
            crc, packed, plain, name_size, extra_size = struct.unpack_from('<IIIHH', header, 14)
            _check((flags, method, crc, packed, plain) ==
                   (entry['flags'], entry['method'], entry['crc'], entry['packed'], entry['plain']) and
                   name_size == len(self._raw_names[name]))
            offset = entry['local'] + 30 + name_size + extra_size
            _check(offset <= self.layout.signing_offset - packed)
            extra = self.range(entry['local'] + 30, name_size + extra_size + (packed if read else 0))
            _check(extra[:name_size] == self._raw_names[name])
            self.witnesses.append((entry['local'], header + extra))
            if not read:
                return offset, packed
            raw = extra[name_size + extra_size:]
            if method == 8:
                decoder = zlib.decompressobj(-15)
                value = decoder.decompress(raw, plain + 1)
                _check(len(value) == plain and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail)
            else:
                value = raw
            _check(len(value) == plain and zlib.crc32(value) & 0xffffffff == crc)
            return value
        except (UnicodeError, struct.error, zlib.error) as error:
            raise ValueError('Could not read the selected original APK member fields or data.') from error
