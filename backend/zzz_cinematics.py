"""Resolve authored Mandarin cinematic events to installed Wwise 135 media."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import struct

from .honkai_assets import PackageEntry, bank_sources, package_tables, read_entry
from .nte_assets import wwise_hash

MANDARIN = 'chinese(prc)'


def event_bank_links(resource: dict) -> dict[int, set[int]]:
    values = resource.get('eventReferenceBanks', [])
    result, position = {}, 0
    while position < len(values):
        event = values[position]; position += 1
        banks = set()
        while position < len(values) and values[position] != 0:
            banks.add(values[position]); position += 1
        if position >= len(values) or not banks:
            raise ValueError('Incomplete cinematic event bank references')
        result[event] = banks
        position += 1
    return result


def resolve_cinematic_links(links: list[dict], game_data: Path, resource: dict) -> dict[str, dict]:
    events_by_text = defaultdict(set)
    names = {}
    for link in links:
        text_id, event = link.get('text_id', ''), link.get('event', '')
        if not re.fullmatch(r'CS_[A-Za-z0-9_]+', text_id) or not re.fullmatch(r'Play_vo_[A-Za-z0-9_]+', event, re.I):
            continue
        event_id = wwise_hash(event)
        events_by_text[text_id].add(event_id)
        names[event_id] = event
    wanted = {next(iter(values)) for values in events_by_text.values() if len(values) == 1}
    event_banks = event_bank_links(resource)
    wanted_banks = set().union(*(event_banks.get(event, set()) for event in wanted))
    banks, sounds = {}, {}
    for layer in ('StreamingAssets', 'Persistent'):
        for package in sorted((game_data / layer / 'Audio/Windows/Full/Cn').glob('*.pck')):
            languages, package_banks, package_sounds = package_tables(package)
            for (identifier, language), entry in package_banks.items():
                if languages[language] == MANDARIN:
                    banks[identifier] = (package, entry)
            for (identifier, language), entry in package_sounds.items():
                if languages[language] == MANDARIN:
                    sounds[identifier] = (package, entry)
    candidates, bindings_by_bank, embedded_by_bank = defaultdict(dict), {}, {}
    for bank_id, (package, bank) in banks.items():
        if bank_id not in wanted_banks:
            continue
        try:
            bindings, embedded = bank_sources(read_entry(package, bank), bank_id, language=MANDARIN)
        except (ValueError, struct.error):
            continue
        bindings_by_bank[bank_id] = bindings
        embedded_by_bank[bank_id] = {media: (package, PackageEntry(bank.offset + entry.offset, entry.size))
                                      for media, entry in embedded.items()}
    for bank_id, bindings in bindings_by_bank.items():
        for event in wanted & bindings.keys():
            if bank_id not in event_banks.get(event, set()):
                continue
            media = bindings[event]
            sources = [entries[media] for linked_bank, entries in embedded_by_bank.items()
                       if linked_bank in event_banks[event] and media in entries]
            if media in sounds:
                sources.append(sounds[media])
            for path, entry in sources:
                with path.open('rb') as stream:
                    stream.seek(entry.offset)
                    if stream.read(4) != b'RIFF':
                        continue
                identity = (str(path), entry.offset, entry.size)
                candidates[event][identity] = {
                    'source': '', 'file_id': f'{media:016x}', 'package': str(path),
                    'offset': entry.offset, 'size': entry.size,
                    'event': names[event], 'matched_by': 'authored_cinematic_event',
                }
    result = {}
    for text_id, events in events_by_text.items():
        if len(events) != 1:
            continue
        matches = candidates[next(iter(events))]
        if len(matches) == 1:
            result[text_id] = next(iter(matches.values()))
    return result
