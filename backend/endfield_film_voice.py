"""Resolve an authored film voice event to a single recording in the released dub."""
import re
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

from . import endfield_metadata, endfield_release as release, endfield_vfs as vfs
from .nte_assets import wwise_hash
from .pragmata_audio import read_bank_play_layers


def event_count(bank, identity):
    """An unsupported definition must also count when testing uniqueness."""
    count = pos = 0
    while pos < len(bank):
        if len(bank) - pos < 8:
            raise ValueError('Incomplete Wwise bank section.')
        tag, size = struct.unpack_from('<4sI', bank, pos)
        pos += 8
        end = pos + size
        if end > len(bank):
            raise ValueError('Truncated Wwise bank section.')
        if tag == b'HIRC':
            if size < 4:
                raise ValueError('Truncated Wwise object count.')
            objects, = struct.unpack_from('<I', bank, pos)
            pos += 4
            for _ in range(objects):
                if pos + 9 > end:
                    raise ValueError('Truncated Wwise object.')
                kind, length, key = struct.unpack_from('<BII', bank, pos)
                if length < 4 or pos + 5 + length > end:
                    raise ValueError('Invalid Wwise object size.')
                count += kind == 4 and key == identity
                pos += 5 + length
            if pos != end:
                raise ValueError('Unexpected Wwise object data.')
        pos = end
    return count


def recording(tools, stamp, dub, event):
    if dub not in vfs.LOCALE_BLOCKS or not re.fullmatch('au_vo_[A-Za-z0-9_]{1,160}', event):
        raise ValueError('Expected a localized Endfield voice event.')
    key = wwise_hash(event)
    params = endfield_metadata.parameters(tools)
    hits = []
    with TemporaryDirectory() as temporary:
        class Banks(vfs.Package):
            def _bank(self, identity, offset, size):
                if not 8 <= size <= vfs.MAX_VOICE:
                    raise ValueError('Unsupported Endfield soundbank size.')
                data = self.source.read(offset, size)
                if data[:4] != b'BKHD':
                    data = vfs.xor_data(data, identity, params)
                if data[:4] != b'BKHD':
                    raise ValueError('Invalid Endfield soundbank.')
                if key.to_bytes(4, 'little') in data and (count := event_count(data, key)):
                    path = Path(temporary) / 'event.bnk'
                    path.write_bytes(data)
                    layers = read_bank_play_layers(path).get(key, [])
                    if count != 1 or len(layers) != 1 or layers[0]['delay_seconds'] != 0:
                        raise ValueError('Film event has an ambiguous or unsupported performance.')
                    hits.append((localized, layers[0]['media_id']))
                return ()

        for block in (1, vfs.LOCALE_BLOCKS[dub], 21):
            base, files = release.group(tools, stamp, block)
            for file in files:
                owner = release.hotfix_dub(file.name) if block == 21 else None
                if owner and owner not in (dub, 'main'):
                    continue
                localized = block == vfs.LOCALE_BLOCKS[dub] or owner == dub
                source = release._source(tools, base, file)
                if file.size <= 16 * 1024**2 and ('bank' in file.name or block == 21):
                    raw = release._whole(tools, base, file)
                    source = _Buffer(raw)
                Banks(source, params)
    if len(hits) != 1 or not hits[0][0]:
        raise ValueError('No unique localized film voice event in the released packages.')
    identity = hits[0][1]
    return identity, release.media(tools, stamp, dub, identity)


class _Buffer:
    def __init__(self, data):
        self.data, self.size = data, len(data)

    def read(self, offset, length):
        return self.data[offset:offset + length]
