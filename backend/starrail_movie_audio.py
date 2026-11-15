"""Read a named original dub from a verified Star Rail CRI movie.

Format parameters are private data inputs. No downloaded code is executed and
no video decoding is needed to recover the original audio packets.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile

from .game_tools import _atomic_file
from .persona_cri import utf

LOCALES = {'en': 'EN', 'ja': 'JP', 'ko': 'KR', 'zh-Hans': 'CN', 'zh-Hant': 'CN'}
MAX_TRACK = 64 * 1024**2


def check(value):
    if not value:
        raise ValueError('Unsupported or incomplete Star Rail movie audio. Refresh game data and format metadata.')


@dataclass(frozen=True)
class Track:
    data: bytes
    samples: int
    rate: int
    channels: int

    @property
    def duration_ms(self):
        return self.samples * 1000 / self.rate


def _mask(key):
    check(type(key) is int and 0 <= key < 2**64)
    if not key:
        return bytes(32)
    k = key.to_bytes(8, 'little')
    m = [k[0], k[1], k[2], k[3] - 52, k[4] + 249, k[5] ^ 19, k[6] + 97]
    m = [x & 255 for x in m]
    expressions = (
        lambda: m[0] ^ 255, lambda: m[2] + m[1], lambda: m[1] - m[7],
        lambda: m[2] ^ 255, lambda: m[1] ^ 255, lambda: m[11] + m[9],
        lambda: m[8] - m[3], lambda: m[13] ^ 255, lambda: m[10] - m[11],
        lambda: m[8] - m[15], lambda: m[16] ^ m[7], lambda: m[15] ^ 255,
        lambda: m[3] ^ 16, lambda: m[4] - 50, lambda: m[5] + 237,
        lambda: m[6] ^ 243, lambda: m[19] - m[15], lambda: m[21] + m[7],
        lambda: 33 - m[19], lambda: m[20] ^ m[23], lambda: m[22] * 2,
        lambda: m[23] + 68, lambda: m[3] + m[4], lambda: m[5] - m[22],
        lambda: m[29] ^ m[19],
    )
    for expression in expressions:
        m.append(expression() & 255)
    return bytes(b'URUC'[(i // 2) % 4] if i % 2 else m[i] ^ 255 for i in range(32))


def _adx(data):
    check(len(data) >= 32 and data[:2] == b'\x80\0')
    begin = int.from_bytes(data[2:4], 'big') + 4
    codec, block, bits, channels, rate, samples, cutoff = struct.unpack_from('>BBBBIIH', data, 4)
    check(codec == 3 and block == 18 and bits == 4 and 1 <= channels <= 8
          and 8000 <= rate <= 192000 and 0 < samples <= rate * 3600
          and 0 < cutoff < rate / 2 and 20 <= begin < len(data)
          and data[begin - 6:begin] == b'(c)CRI')
    end = begin + ((samples + 31) // 32) * block * channels
    check(end <= len(data) <= end + block * channels)
    # A wrong packet mask commonly produces an immediate ADX EOF. Require
    # every declared sample block, rather than accepting a decoder exit of 0.
    check(all(not data[at] & 128 for at in range(begin, end, block)))
    check(end == len(data) or data[end:end + 2] == b'\x80\x01')
    return Track(bytes(data), samples, rate, channels)


def read_track(path: Path, locale: str, key: int) -> Track:
    check(locale in LOCALES)
    mask, output, channel, offset = _mask(key), bytearray(), None, 0
    size = path.stat().st_size
    check(32 <= size <= 2 * 1024**3)
    with path.open('rb') as stream:
        while offset < size:
            stream.seek(offset)
            header = stream.read(32)
            check(len(header) == 32)
            end = offset + 8 + int.from_bytes(header[4:8], 'big')
            start = offset + 8 + header[9]
            stop = end - int.from_bytes(header[10:12], 'big')
            check(offset + 32 <= start <= stop <= end <= size)
            kind, content, track = header[:4], header[15] & 3, header[12]
            if offset == 0:
                check(kind == b'CRID' and content == 1 and stop - start <= 1024**2)
                stream.seek(start)
                try:
                    directory = utf(stream.read(stop - start))
                except ValueError as error:
                    raise ValueError('Invalid Star Rail movie stream directory.') from error
                found, channels = {}, set()
                for row in directory:
                    if row.get('stmid') != int.from_bytes(b'@SFA', 'big'):
                        continue
                    name = row.get('filename', '').replace('\\', '/').rsplit('/', 1)[-1]
                    match = re.search(r'_(CN|EN|JP|KR)#([0-9]{2})\.sfa$', name)
                    index = row.get('chno')
                    check(match and type(index) is int and 0 <= index < 16
                          and int(match[2]) == index and match[1] not in found and index not in channels)
                    found[match[1]] = index
                    channels.add(index)
                channel = found.get(LOCALES[locale])
                check(channel is not None)
            elif kind == b'@SFA' and content == 0 and track == channel:
                check(stop - start <= 8 * 1024**2 and len(output) + stop - start <= MAX_TRACK)
                stream.seek(start)
                packet = stream.read(stop - start)
                check(len(packet) == stop - start)
                output.extend(packet[:320])
                # CRI audio masking starts at byte 320 of each packet, not
                # byte 320 of the concatenated stream. Zero denotes plaintext.
                output.extend(value ^ mask[i % 32] for i, value in enumerate(packet[320:]))
            offset = end
    return _adx(output)


def recording(directory, asset, locale, catalog, expected=None):
    """Fetch only the selected immutable movie and retain its original ADX."""
    check(locale in LOCALES and type(asset.size) is int and 32 <= asset.size <= 2 * 1024**3
          and isinstance(asset.digest, str) and re.fullmatch('[0-9a-f]{32}', asset.digest))
    key = catalog.key_for(asset)
    identity = hashlib.sha256((asset.name + '/' + LOCALES[locale]).encode() + key.to_bytes(8, 'little')).hexdigest()
    path = directory / 'starrail-movie-audio' / asset.digest / identity
    if path.is_file() and 32 < path.stat().st_size <= MAX_TRACK + 32:
        raw = path.read_bytes()
        if hashlib.sha256(raw[32:]).digest() == raw[:32] and (expected is None or raw[:32].hex() == expected):
            return _adx(raw[32:])
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='starrail-movie-', dir=directory) as folder:
        movie = Path(folder) / 'source.usm'
        digest = hashlib.md5()
        with movie.open('wb') as target:
            for start in range(0, asset.size, 16 * 1024**2):
                length = min(16 * 1024**2, asset.size - start)
                data = asset.read(directory, start, length)
                check(len(data) == length)
                digest.update(data)
                target.write(data)
        check(digest.hexdigest() == asset.digest)
        track = read_track(movie, locale, key)
    checksum = hashlib.sha256(track.data).digest()
    check(expected is None or checksum.hex() == expected)
    _atomic_file(path, checksum + track.data)
    return track


def binding(directory, stamp, asset, locale, catalog):
    track = recording(directory, asset, locale, catalog)
    return {'publisher': stamp, 'movie': asset.name, 'movie_md5': asset.digest,
            'movie_size': asset.size, 'locale': locale,
            'format_revision': catalog.revision, 'format_digest': catalog.digest,
            'recording_sha256': hashlib.sha256(track.data).hexdigest()}, track.duration_ms


def extract(audio, tools):
    from . import hoyo_publisher_voice as voices, starrail_hotfix, starrail_movie_metadata
    stamp = audio['publisher']
    check(voices.snapshot_available(tools, stamp, 'starrail') and audio['locale'] in LOCALES)
    directory = tools / 'sophon'
    build = json.loads((directory / 'releases' / stamp).read_bytes())
    check('hotfix' in build and isinstance(audio['movie'], str)
          and re.fullmatch('[0-9a-f]{64}', audio['recording_sha256']))
    asset = starrail_hotfix.movie_files(directory, build).get(audio['movie'].casefold())
    check(asset is not None and (asset.digest, asset.size) == (audio['movie_md5'], audio['movie_size']))
    catalog = starrail_movie_metadata.load(directory, audio['format_revision'], audio['format_digest'])
    return recording(directory, asset, audio['locale'], catalog, audio['recording_sha256']).data
