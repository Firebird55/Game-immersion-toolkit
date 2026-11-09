"""Resolve an authored film voice event to a single recording in the released dub."""
from collections import Counter
import re
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

from . import endfield_metadata, endfield_release as release, endfield_vfs as vfs
from .nte_assets import wwise_hash
from .pragmata_audio import read_bank_play_layers


def event_counts(bank, identities):
    """Count every requested event definition, including unsupported definitions."""
    counts = Counter()
    pos = 0
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
                if kind == 4 and key in identities:
                    counts[key] += 1
                pos += 5 + length
            if pos != end:
                raise ValueError('Unexpected Wwise object data.')
        pos = end
    return counts


def recording_ids(tools, stamp, dub, events):
    """Resolve multiple film events in one pass through this release's soundbanks."""
    events = set(events)
    if dub not in vfs.LOCALE_BLOCKS or not all(re.fullmatch('au_vo_[A-Za-z0-9_]{1,160}', name) for name in events):
        raise ValueError('Expected a localized Endfield voice event.')
    keys = {wwise_hash(name): name for name in events}
    if len(keys) != len(events):
        raise ValueError('Ambiguous film voice event hash.')
    params = endfield_metadata.parameters(tools)
    definitions = Counter()
    localized_media = {}
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
                counts = event_counts(data, keys)
                definitions.update(counts)
                if localized and counts:
                    path = Path(temporary) / 'event.bnk'
                    path.write_bytes(data)
                    layers = read_bank_play_layers(path)
                    for key in counts:
                        play = layers.get(key, [])
                        if len(play) == 1 and play[0]['delay_seconds'] == 0:
                            localized_media[key] = play[0]['media_id']
                return ()

        for block in (1, 12, vfs.LOCALE_BLOCKS[dub], 21):
            base, files = release.group(tools, stamp, block)
            for file in files:
                owner = release.hotfix_dub(file.name) if block == 21 else None
                if owner and owner not in (dub, 'main'):
                    continue
                localized = block == vfs.LOCALE_BLOCKS[dub] or owner == dub
                source = release._source(tools, base, file)
                if ('bank' in file.name and file.size <= vfs.MAX_VOICE) or (block == 21 and file.size <= 16 * 1024**2):
                    raw = release._whole(tools, base, file)
                    source = _Buffer(raw)
                Banks(source, params)
    return {keys[key]: media for key, media in localized_media.items() if definitions[key] == 1}


def recording(tools, stamp, dub, event):
    media = recording_ids(tools, stamp, dub, (event,))
    if event not in media:
        raise ValueError('No unique localized film voice event in the released packages.')
    identity = media[event]
    return identity, release.media(tools, stamp, dub, identity)


class _Buffer:
    def __init__(self, data):
        self.data, self.size = data, len(data)

    def read(self, offset, length):
        return self.data[offset:offset + length]
