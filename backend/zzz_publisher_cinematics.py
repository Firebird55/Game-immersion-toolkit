"""Original design registry -> selected publisher banks -> immutable Wwise media."""
from collections import defaultdict
from functools import lru_cache
import re
import struct

from flatbuffers import flexbuffers

from .wwise_tables import (
    PackageEntry, bank_metadata_from_reader, bank_sources_from_reader, package_tables_from_reader,
    wwise_short_id as wwise_hash,
)
from .zzz_dialogue_records import VOICE_FOLDERS, voice_namespace
from .zzz_cinematics import event_bank_links
from .zzz_voice_layers import unconditional_voice_layers
from .zzz_bus_routing import INITIAL_BANK_FILENAME, bus_parents_from_reader


def audio_registry(data):
    """A plain-named design TextAsset uses the already locked FlexBuffers reader."""
    if not 3 <= len(data) <= 32 * 1024**2:
        raise ValueError('Unsupported original ZZZ audio registry size.')
    try:
        root = flexbuffers.GetRoot(data)
        if not root.IsMap or not 1 <= len(root.AsMap) <= 128:
            raise ValueError('Unsupported original ZZZ audio registry root.')
        keys = [key.AsKey for key in root.AsMap.Keys]
        if len(keys) != len(set(keys)) or any(len(key) > 128 for key in keys):
            raise ValueError('Ambiguous original ZZZ audio registry fields.')
        entry = root.AsMap['eventReferenceBanks']
        if not entry.IsVector or not 1 <= len(entry.AsVector) <= 2_000_000:
            raise ValueError('Unsupported original ZZZ event/bank vector.')
        values = []
        for ref in entry.AsVector:
            if not ref.IsInt or ref.IsBool:
                raise ValueError('Noninteger original ZZZ event/bank identity.')
            value = ref.AsInt
            if not 0 <= value <= 0xffffffff:
                raise ValueError('Original ZZZ event/bank identity exceeds Wwise bounds.')
            values.append(value)
        return event_bank_links({'eventReferenceBanks': values})
    except (KeyError, IndexError, TypeError, OverflowError, struct.error) as exc:
        raise ValueError('Unsupported original ZZZ audio registry format.') from exc


@lru_cache(maxsize=256)
def _tables(directory, stamp, locale, name):
    from . import hoyo_publisher_voice as voice
    source = voice._archive(directory, stamp, locale, name, 'zzz')
    return package_tables_from_reader(source.size, lambda start, size: source.read(directory, start, size))


@lru_cache(maxsize=512)
def _bank(directory, stamp, locale, name, bank_id, mode='direct'):
    namespace = voice_namespace(locale).lower()
    languages, banks, _ = _tables(directory, stamp, locale, name)
    matches = [entry for (identifier, language), entry in banks.items()
               if identifier == bank_id and languages[language] == namespace]
    if len(matches) != 1 or not 0 < matches[0].size <= 64 * 1024**2:
        raise ValueError('Original ZZZ cinematic bank is missing or ambiguous.')
    entry, = matches
    from . import hoyo_publisher_voice as voice
    source = voice._archive(directory, stamp, locale, name, 'zzz')
    return _read_bank(entry, lambda start, size: source.read(directory, start, size),
                      bank_id, namespace, mode, lambda: _initial_buses(directory, stamp, locale))


def _read_bank(entry, source_read, bank_id, namespace, mode, initial_buses):
    """The same owned bank parser over a caller-bound, authenticated reader."""
    read = lambda start, size: source_read(entry.offset + start, size)
    if mode == 'unconditional_voice_layer':
        objects, embedded = bank_metadata_from_reader(entry.size, read, bank_id, language=namespace)
        buses = None
        if any(kind == 3 and len(raw) >= 6 and struct.unpack_from('<H', raw, 4)[0] == 0x0102
               for kind, raw in objects.values()):
            try:
                buses = initial_buses()
            except (ValueError, struct.error):
                pass  # Other all-Play events in this bank remain independently resolvable.
        bindings = unconditional_voice_layers(objects, buses)
    elif mode == 'direct':
        bindings, embedded = bank_sources_from_reader(entry.size, read, bank_id, language=namespace, detailed=True)
    else:
        raise ValueError('Unsupported original ZZZ cinematic source mode.')
    return bindings, {identifier: PackageEntry(entry.offset + media.offset, media.size)
                      for identifier, media in embedded.items()}


@lru_cache(maxsize=128)
def _dependency(directory, stamp, locale, name, bank_id):
    """An original common SFX bank may be required alongside the selected dub.

    Validate its identity and structure, but never return its events or media as
    voice candidates. The actual performance must resolve in the selected dub.
    """
    if not name.rpartition('/')[0].endswith('/Audio/Windows/Full'):
        raise ValueError('Original ZZZ common bank is outside the shared package directory.')
    languages, banks, _ = _tables(directory, stamp, locale, name)
    entry, = [entry for (identifier, language), entry in banks.items()
              if identifier == bank_id and languages[language] == 'sfx']
    if not 0 < entry.size <= 64 * 1024**2:
        raise ValueError('Unsupported original ZZZ common bank size.')
    from . import hoyo_publisher_voice as voice
    source = voice._archive(directory, stamp, locale, name, 'zzz')
    bank_sources_from_reader(entry.size, lambda start, size: source.read(directory, entry.offset + start, size),
                             bank_id, language='sfx')


def _inventory(directory, stamp, locale, wanted_banks):
    from . import hoyo_publisher_voice as voice
    files = voice._files(directory, stamp, locale, 'zzz')
    return _inventory_from_files(files, locale, wanted_banks,
        lambda name: _tables(directory, stamp, locale, name))


def _inventory_from_files(files, locale, wanted_banks, tables):
    namespace = voice_namespace(locale).lower()
    folder = '/Audio/Windows/Full/' + VOICE_FOLDERS[locale] + '/'
    result = [{}, {}, {}]
    for layer in ('StreamingAssets', 'Persistent'):
        current, ambiguous = [{}, {}, {}], [set(), set(), set()]
        for name in sorted(name for name in files if name.split('/')[1] == layer and
                           (folder in name or name.rpartition('/')[0].endswith('/Audio/Windows/Full'))):
            common = folder not in name
            languages, banks, sounds = tables(name)
            for index, table in enumerate((banks, sounds)):
                for (identifier, language), entry in table.items():
                    if common:
                        if index or languages[language] != 'sfx' or identifier not in wanted_banks:
                            continue
                        target = 2
                    else:
                        if languages[language] != namespace or index == 0 and identifier not in wanted_banks:
                            continue
                        target = index
                    if identifier in current[target]:
                        ambiguous[target].add(identifier)
                    current[target][identifier] = (name, entry)
        for index in range(3):
            result[index].update(current[index])
            for identifier in ambiguous[index]:
                result[index].pop(identifier, None)
    return result


@lru_cache(maxsize=128)
def _initial_buses(directory, stamp, locale):
    identity = wwise_hash(INITIAL_BANK_FILENAME.rsplit('.', 1)[0])
    banks, _, common = _inventory(directory, stamp, locale, {identity})
    if banks or set(common) != {identity}:
        raise ValueError('Original ZZZ initialization bank is missing or ambiguous.')
    name, entry = common[identity]
    from . import hoyo_publisher_voice as voice
    source = voice._archive(directory, stamp, locale, name, 'zzz')
    return bus_parents_from_reader(entry.size,
        lambda start, size: source.read(directory, entry.offset + start, size), identity)


def requested_events(links, registry):
    """Select only unanimous authored contexts, before any bank/source access."""
    uses = defaultdict(list)
    for link in links:
        uses[link['text_id']].append(link)
    events_by_text, modes_by_text = {}, {}
    for identity, rows in uses.items():
        events = {row.get('cinematic_event') for row in rows}
        if (len(events) != 1 or None in events or any(row.get('source') or row.get('audio_scope') != 'context' for row in rows)):
            continue
        event, = events
        if not re.fullmatch(r'Play_vo_[A-Za-z0-9_]+', event, re.I):
            continue
        mode = 'direct'
        if not registry.get(wwise_hash(event)):
            alternates = [row.get('cinematic_alternates') for row in rows]
            if (any(not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str)
                    or not re.fullmatch(r'Play_[A-Za-z0-9_]+', values[0], re.I)
                    or re.match(r'Play_vo_', values[0], re.I) for values in alternates)
                    or len({values[0] for values in alternates}) != 1):
                continue
            event, mode = alternates[0][0], 'unconditional_voice_layer'
        events_by_text[identity], modes_by_text[identity] = event, mode
    if not events_by_text:
        return {}, {}, {}
    names = defaultdict(set)
    for identity, event in events_by_text.items():
        names[wwise_hash(event)].add((event, modes_by_text[identity]))
    events = {identity: next(iter(values)) for identity, values in names.items() if len(values) == 1}
    return events_by_text, modes_by_text, events


def bindings(data_dir, stamp, locale, links, registry, *, catalogue=None):
    """Only unanimous authored cinema uses can acquire a whole-film context."""
    events_by_text, modes_by_text, events = requested_events(links, registry)
    wanted = set().union(*(registry.get(event, set()) for event in events))
    if not wanted:
        return {}
    directory = data_dir / 'tools/sophon'
    inventory = ((lambda wanted: _inventory(directory, stamp, locale, wanted)) if catalogue is None else catalogue.inventory)
    dependency = ((lambda name, identifier: _dependency(directory, stamp, locale, name, identifier))
                  if catalogue is None else catalogue.dependency)
    bank = ((lambda name, identifier, mode: _bank(directory, stamp, locale, name, identifier, mode))
            if catalogue is None else catalogue.bank)
    banks, sounds, dependencies = inventory(wanted)
    complete = {event for event in events if registry.get(event) and registry[event] <= banks.keys() | dependencies.keys()}
    wanted = set().union(*(registry[event] for event in complete))
    verified_dependencies = set()
    for identifier, (name, _) in dependencies.items():
        if identifier not in wanted or identifier in banks:
            continue
        try:
            dependency(name, identifier)
            verified_dependencies.add(identifier)
        except (ValueError, struct.error):
            continue
    parsed_modes = {}
    for mode in {value[1] for value in events.values()}:
        wanted_mode = set().union(*(registry[event] for event in complete if events[event][1] == mode))
        parsed = parsed_modes[mode] = {}
        for identifier, (name, _) in banks.items():
            if identifier not in wanted_mode:
                continue
            try:
                parsed[identifier] = (name, *bank(name, identifier, mode))
            except (ValueError, struct.error):
                # A changed or unsupported hierarchy is unresolved, never silent.
                continue
    candidates = defaultdict(dict)
    for event_id, (event, mode) in events.items():
        parsed = parsed_modes[mode]
        required = registry.get(event_id, set())
        if not required or not required <= parsed.keys() | verified_dependencies:
            continue
        for event_bank in sorted(required & parsed.keys()):
            event_name, event_sources, _ = parsed[event_bank]
            source = event_sources.get(event_id)
            if source is None or not 0 < source.media_id <= 0xffffffff:
                continue
            media_id = source.media_id
            # Wwise 135 source kinds are Data, PrefetchStreaming and Streaming.
            # A bank's prefetch prefix is not the complete streamed recording.
            sources = [(parsed[bank][0], parsed[bank][2][media_id], bank)
                       for bank in sorted(required & parsed.keys()) if source.stream_type == 0 and media_id in parsed[bank][2]
                       and parsed[bank][2][media_id].size == source.memory_size]
            if source.stream_type in (1, 2) and media_id in sounds:
                name, entry = sounds[media_id]
                if (source.stream_type == 1 and 0 < source.memory_size < entry.size
                        or source.stream_type == 2 and source.memory_size == 0):
                    sources.append((name, entry, None))
            for name, entry, media_bank in sources:
                identity = (name, entry.offset, entry.size, media_id)
                candidates[event_id].setdefault(identity, {
                    'publisher': stamp, 'locale': locale, 'source': '', 'file_id': f'{media_id:016x}',
                    'package': name, 'event_package': event_name, 'event_bank': event_bank,
                    'media_bank': media_bank, 'event': event, 'audio_scope': 'context',
                    **({'event_mode': mode} if mode != 'direct' else {}),
                    'matched_by': 'publisher_cinematic_event'})
    return {identity: next(iter(candidates[wwise_hash(event)].values()))
            for identity, event in events_by_text.items() if len(candidates[wwise_hash(event)]) == 1}


def recording(audio, tools, *, catalogue=None):
    """Validate the full original event-to-media join before selecting bytes."""
    locale, stamp = audio['locale'], audio['publisher']
    event, media_id = audio.get('event', ''), int(audio['file_id'], 16)
    mode = audio.get('event_mode', 'direct')
    pattern = r'Play_[A-Za-z0-9_]+' if mode == 'unconditional_voice_layer' else r'Play_vo_[A-Za-z0-9_]+'
    if (locale not in VOICE_FOLDERS or audio.get('source') or audio.get('audio_scope') != 'context'
            or mode not in ('direct', 'unconditional_voice_layer')
            or not re.fullmatch(pattern, event, re.I) or not 0 < media_id <= 0xffffffff):
        raise ValueError('Invalid original ZZZ cinematic context identity.')
    if (type(audio.get('event_bank')) is not int or not 0 < audio['event_bank'] <= 0xffffffff
            or audio.get('media_bank') is not None and
            (type(audio['media_bank']) is not int or not 0 < audio['media_bank'] <= 0xffffffff)):
        raise ValueError('Invalid original ZZZ cinematic bank identity.')
    directory = tools / 'sophon'
    folder = '/Audio/Windows/Full/' + VOICE_FOLDERS[locale] + '/'
    if any(folder not in audio[key] for key in ('package', 'event_package')):
        raise ValueError('ZZZ cinematic context crosses original voice locales.')
    bank = ((lambda name, identifier, mode='direct': _bank(directory, stamp, locale, name, identifier, mode))
            if catalogue is None else catalogue.bank)
    tables = ((lambda name: _tables(directory, stamp, locale, name)) if catalogue is None else catalogue.tables)
    event_sources, _ = bank(audio['event_package'], audio['event_bank'], mode)
    source = event_sources.get(wwise_hash(event))
    if source is None or source.media_id != media_id:
        raise ValueError('Original ZZZ cinematic event no longer identifies this recording.')
    if audio.get('media_bank') is not None:
        if source.stream_type != 0:
            raise ValueError('Original ZZZ streamed source cannot use a bank prefix.')
        _, embedded = bank(audio['package'], audio['media_bank'])
        entry = embedded[media_id]
        if entry.size != source.memory_size:
            raise ValueError('Original ZZZ bank recording size has changed.')
    else:
        languages, _, sounds = tables(audio['package'])
        namespace = voice_namespace(locale).lower()
        entry, = [value for (identifier, language), value in sounds.items()
                  if identifier == media_id and languages[language] == namespace]
        if not (source.stream_type == 1 and 0 < source.memory_size < entry.size
                or source.stream_type == 2 and source.memory_size == 0):
            raise ValueError('Original ZZZ source does not identify a complete streamed recording.')
    return audio['package'], entry


def extract(audio, tools, *, catalogue=None):
    name, entry = recording(audio, tools, catalogue=catalogue)
    from . import hoyo_publisher_voice as voice
    data = (voice._archive(tools / 'sophon', audio['publisher'], audio['locale'], name, 'zzz').read(
                tools / 'sophon', entry.offset, entry.size) if catalogue is None
            else catalogue.read(name, entry.offset, entry.size))
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE' or len(data) != struct.unpack_from('<I', data, 4)[0] + 8:
        raise ValueError('Original ZZZ cinematic context is incomplete.')
    return data
