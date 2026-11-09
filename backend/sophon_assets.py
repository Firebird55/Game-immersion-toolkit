"""Read checksummed files from released Windows HoYoPlay manifests."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from http.client import IncompleteRead
import json
from pathlib import Path
import re
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit

import zstandard

from .game_tools import _atomic_file, download

GLOBAL = ('sg-hyp-api.hoyoverse.com', 'VYTpXlbWo8', 'sg-public-api.hoyoverse.com')
CHINA = ('hyp-api.mihoyo.com', 'jGHBHlcOq1', 'api-takumi.mihoyo.com')
CHANNELS = {
    'genshin-cn': (CHINA, '1Z8W5NHUQb', '1Zg4loy9r2BG', 'autopatchcn.yuanshen.com'),
    'genshin-global': (GLOBAL, 'gopR6Cufr3', 'cxhpq4g4rgg0', 'autopatchhk.yuanshen.com'),
    'starrail-global': (GLOBAL, '4ziysqXOQ8', 'cxi9x2wxybk0', 'autopatchos.starrails.com'),
    'zzz-global': (GLOBAL, 'U5hbdsT9W7', 'ddxf6vlr1reo', 'autopatchos.zenlesszonezero.com'),
}
VOICE_FIELDS = {'en': 'en-us', 'zh-Hans': 'zh-cn', 'zh-Hant': 'zh-cn', 'ja': 'ja-jp', 'ko': 'ko-kr'}
MAX_MANIFEST = 128 * 1024**2
MAX_CHUNK = 16 * 1024**2


def _check(condition):
    if not condition:
        raise ValueError('Invalid or unsupported HoYoPlay publisher package.')


def _prefix(url, channel):
    parsed = urlsplit(url)
    _check(parsed.scheme == 'https' and parsed.netloc == CHANNELS[channel][3]
           and re.fullmatch(r'/[a-zA-Z0-9_./-]+', parsed.path) and '..' not in parsed.path
           and not parsed.query and not parsed.fragment)
    return url.rstrip('/')


def release(channel):
    (launcher, launcher_id, downloader), game_id, platform, _ = CHANNELS[channel]
    url = f'https://{launcher}/hyp/hyp-connect/api/getGameBranches?launcher_id={launcher_id}'
    listing = json.loads(download(url, limit=2 * 1024**2))
    _check(listing['retcode'] == 0)
    main, = [item['main'] for item in listing['data']['game_branches'] if item['game']['id'] == game_id]
    _check(main['branch'] == 'main' and re.fullmatch(r'\d+\.\d+\.\d+', main['tag']))
    query = urlencode({key: main[key] for key in ('tag', 'branch', 'password', 'package_id')} | {'plat_app': platform})
    # The temporary branch parameter is used only in this request.
    reply = json.loads(download(f'https://{downloader}/downloader/sophon_chunk/api/getBuild?{query}', limit=4 * 1024**2))
    build = reply['data']
    _check(reply['retcode'] == 0 and build['tag'] == main['tag'] and re.fullmatch('[a-zA-Z0-9]+', build['build_id']))
    manifests = {}
    for row in build['manifests']:
        field = row['matching_field']
        if field not in {'game', *VOICE_FIELDS.values()}:
            continue
        info = row['manifest']
        for method in ('manifest_download', 'chunk_download'):
            delivery = row[method]
            _check(delivery['encryption'] == 0 and delivery['compression'] == 1 and not delivery['url_suffix'])
        _check(field not in manifests and re.fullmatch('manifest_[0-9a-f]{16}_[0-9a-f]{32}', info['id'])
               and info['id'].endswith('_' + info['checksum']))
        manifests[field] = (_prefix(row['manifest_download']['url_prefix'], channel), info['id'],
                            int(info['compressed_size']), int(info['uncompressed_size']), info['checksum'],
                            _prefix(row['chunk_download']['url_prefix'], channel))
    _check(set(manifests) == {'game', *VOICE_FIELDS.values()})
    return {'channel': channel, 'version': build['tag'], 'build': build['build_id'], 'manifests': manifests}


def _verified(directory, url, compressed, length, digest, maximum):
    _check(0 < compressed <= maximum and 0 < length <= maximum and re.fullmatch('[0-9a-f]{32}', digest))
    path = directory / digest
    if path.is_file() and path.stat().st_size == length:
        data = path.read_bytes()
        if hashlib.md5(data).hexdigest() == digest:
            return data
    # Reuse all verified chunks; retry only this immutable object after an
    # interrupted transfer. A full-length checksum failure is a different error.
    try:
        encoded = download(url, limit=compressed)
    except (IncompleteRead, ConnectionError, TimeoutError):
        encoded = b''
    except URLError as error:
        if not isinstance(error.reason, (ConnectionError, TimeoutError)):
            raise
        encoded = b''
    if len(encoded) < compressed:
        encoded = download(url, limit=compressed)
    _check(len(encoded) == compressed)
    declared = zstandard.frame_content_size(encoded)
    _check(declared in (-1, length))
    data = zstandard.ZstdDecompressor(max_window_size=maximum // 1024).decompress(
        encoded, max_output_size=length, allow_extra_data=False)
    _check(len(data) == length and hashlib.md5(data).hexdigest() == digest)
    _atomic_file(path, data)
    return data


def _varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        _check(pos < len(data))
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError('Invalid Sophon manifest integer.')


def _fields(data):
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        value, pos = _varint(data, pos)
        _check(tag >> 3 and tag & 7 in (0, 2))
        if tag & 7 == 2:
            end = pos + value
            _check(end <= len(data))
            value, pos = data[pos:end], end
        yield tag >> 3, value


@dataclass(frozen=True)
class File:
    name: str
    size: int
    digest: str
    chunks: tuple
    prefix: str

    def read(self, directory, start, length):
        _check(0 <= start <= self.size - length and 0 < length <= 64 * 1024**2)
        end = start + length
        output = bytearray()
        for base, size, compressed, object_name, digest in self.chunks:
            if base >= end:
                break
            if base + size <= start:
                continue
            data = _verified(directory / 'chunks', self.prefix + '/' + object_name,
                             compressed, size, digest, MAX_CHUNK)
            output.extend(data[max(0, start - base):end - base])
        _check(len(output) == length)
        if start == 0 and length == self.size:
            _check(hashlib.md5(output).hexdigest() == self.digest)
        return bytes(output)


@lru_cache(maxsize=12)
def manifest(directory: Path, channel, spec, suffixes):
    base, name, compressed, length, digest, prefix = spec
    _check(re.fullmatch('manifest_[0-9a-f]{16}_' + re.escape(digest), name))
    data = _verified(directory / 'manifests', _prefix(base, channel) + '/' + name,
                     compressed, length, digest, MAX_MANIFEST)
    prefix = _prefix(prefix, channel)
    result = {}
    for number, body in _fields(memoryview(data)):
        if number != 1:
            continue
        fields = list(_fields(body))
        row = dict(fields)
        path = bytes(row[1]).decode()
        if not path.endswith(suffixes):
            continue
        _check(path not in result and not path.startswith('/') and '..' not in path.split('/')
               and '\\' not in path and ':' not in path)
        size = row[4]
        file_digest = bytes(row[5]).decode('ascii')
        _check(re.fullmatch('[0-9a-f]{32}', file_digest))
        chunks = []
        for key, value in fields:
            if key == 2:
                item = dict(_fields(value))
                name, md5 = bytes(item[1]).decode('ascii'), bytes(item[2]).decode('ascii')
                _check(re.fullmatch('[0-9a-f]{16}_[0-9a-f]{32}', name) and name.endswith('_' + md5)
                       and 0 < item[4] <= MAX_CHUNK and 0 < item[5] <= MAX_CHUNK and len(md5) == 32)
                chunks.append((item.get(3, 0), item[5], item[4], name, md5))
        offset = 0
        for position, count, *_ in sorted(chunks):
            _check(position == offset)
            offset += count
        _check(offset == size)
        result[path] = File(path, size, file_digest, tuple(sorted(chunks)), prefix)
    return result
