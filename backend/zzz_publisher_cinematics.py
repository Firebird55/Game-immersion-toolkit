"""Original design registry -> selected publisher banks -> immutable Wwise media."""
from collections import defaultdict
from functools import lru_cache
import re
import struct

from flatbuffers import flexbuffers

from . import hoyo_publisher_voice as voice
from .honkai_assets import PackageEntry, bank_sources_from_reader, package_tables_from_reader
from .hoyo_dialogue import voice_namespace
from .nte_assets import wwise_hash
from .zzz_assets import VOICE_FOLDERS
from .zzz_cinematics import event_bank_links


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
    source = voice._archive(directory, stamp, locale, name, 'zzz')
    return package_tables_from_reader(source.size, lambda start, size: source.read(directory, start, size))


@lru_cache(maxsize=512)
def _bank(directory, stamp, locale, name, bank_id):
    namespace = voice_namespace('zzz', locale).lower()
    languages, banks, _ = _tables(directory, stamp, locale, name)
    matches = [entry for (identifier, language), entry in banks.items()
               if identifier == bank_id and languages[language] == namespace]
    if len(matches) != 1 or not 0 < matches[0].size <= 64 * 1024**2:
        raise ValueError('Original ZZZ cinematic bank is missing or ambiguous.')
    entry, = matches
    source = voice._archive(directory, stamp, locale, name, 'zzz')
    bindings, embedded = bank_sources_from_reader(entry.size,
        lambda start, size: source.read(directory, entry.offset + start, size), bank_id, language=namespace, detailed=True)
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
    source = voice._archive(directory, stamp, locale, name, 'zzz')
    bank_sources_from_reader(entry.size, lambda start, size: source.read(directory, entry.offset + start, size),
                             bank_id, language='sfx')


def _inventory(directory, stamp, locale, wanted_banks):
    namespace = voice_namespace('zzz', locale).lower()
    folder = '/Audio/Windows/Full/' + VOICE_FOLDERS[locale] + '/'
    files = voice._files(directory, stamp, locale, 'zzz')
    result = [{}, {}, {}]
    for layer in ('StreamingAssets', 'Persistent'):
        current, ambiguous = [{}, {}, {}], [set(), set(), set()]
        for name in sorted(name for name in files if name.split('/')[1] == layer and
                           (folder in name or name.rpartition('/')[0].endswith('/Audio/Windows/Full'))):
            common = folder not in name
            languages, banks, sounds = _tables(directory, stamp, locale, name)
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


def bindings(data_dir, stamp, locale, links, registry):
    """Only unanimous authored cinema uses can acquire a whole-film context."""
    uses = defaultdict(list)
    for link in links:
        uses[link['text_id']].append(link)
    events_by_text = {}
    for identity, rows in uses.items():
        events = {row.get('cinematic_event') for row in rows}
        if (len(events) != 1 or None in events or any(row.get('source') or row.get('audio_scope') != 'context' for row in rows)):
            continue
        event, = events
        if re.fullmatch(r'Play_vo_[A-Za-z0-9_]+', event, re.I):
            events_by_text[identity] = event
    if not events_by_text:
        return {}
    names = defaultdict(set)
    for event in events_by_text.values():
        names[wwise_hash(event)].add(event)
    events = {identity: next(iter(values)) for identity, values in names.items() if len(values) == 1}
    wanted = set().union(*(registry.get(event, set()) for event in events))
    if not wanted:
        return {}
    directory = data_dir / 'tools/sophon'
    banks, sounds, dependencies = _inventory(directory, stamp, locale, wanted)
    complete = {event for event in events if registry.get(event) and registry[event] <= banks.keys() | dependencies.keys()}
    wanted = set().union(*(registry[event] for event in complete))
    verified_dependencies = set()
    for identifier, (name, _) in dependencies.items():
        if identifier not in wanted or identifier in banks:
            continue
        try:
            _dependency(directory, stamp, locale, name, identifier)
            verified_dependencies.add(identifier)
        except (ValueError, struct.error):
            continue
    parsed = {}
    for identifier, (name, _) in banks.items():
        if identifier not in wanted:
            continue
        try:
            parsed[identifier] = (name, *_bank(directory, stamp, locale, name, identifier))
        except (ValueError, struct.error):
            # A changed or unsupported hierarchy is unresolved, never silent.
            continue
    candidates = defaultdict(dict)
    for event_id, event in events.items():
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
                    'matched_by': 'publisher_cinematic_event'})
    return {identity: next(iter(candidates[wwise_hash(event)].values()))
            for identity, event in events_by_text.items() if len(candidates[wwise_hash(event)]) == 1}


def extract(audio, tools):
    locale, stamp = audio['locale'], audio['publisher']
    event, media_id = audio.get('event', ''), int(audio['file_id'], 16)
    if (locale not in VOICE_FOLDERS or audio.get('source') or audio.get('audio_scope') != 'context'
            or not re.fullmatch(r'Play_vo_[A-Za-z0-9_]+', event, re.I) or not 0 < media_id <= 0xffffffff):
        raise ValueError('Invalid original ZZZ cinematic context identity.')
    if (type(audio.get('event_bank')) is not int or not 0 < audio['event_bank'] <= 0xffffffff
            or audio.get('media_bank') is not None and
            (type(audio['media_bank']) is not int or not 0 < audio['media_bank'] <= 0xffffffff)):
        raise ValueError('Invalid original ZZZ cinematic bank identity.')
    directory = tools / 'sophon'
    folder = '/Audio/Windows/Full/' + VOICE_FOLDERS[locale] + '/'
    if any(folder not in audio[key] for key in ('package', 'event_package')):
        raise ValueError('ZZZ cinematic context crosses original voice locales.')
    event_sources, _ = _bank(directory, stamp, locale, audio['event_package'], audio['event_bank'])
    source = event_sources.get(wwise_hash(event))
    if source is None or source.media_id != media_id:
        raise ValueError('Original ZZZ cinematic event no longer identifies this recording.')
    if audio.get('media_bank') is not None:
        if source.stream_type != 0:
            raise ValueError('Original ZZZ streamed source cannot use a bank prefix.')
        _, embedded = _bank(directory, stamp, locale, audio['package'], audio['media_bank'])
        entry = embedded[media_id]
        if entry.size != source.memory_size:
            raise ValueError('Original ZZZ bank recording size has changed.')
    else:
        languages, _, sounds = _tables(directory, stamp, locale, audio['package'])
        namespace = voice_namespace('zzz', locale).lower()
        entry, = [value for (identifier, language), value in sounds.items()
                  if identifier == media_id and languages[language] == namespace]
        if not (source.stream_type == 1 and 0 < source.memory_size < entry.size
                or source.stream_type == 2 and source.memory_size == 0):
            raise ValueError('Original ZZZ source does not identify a complete streamed recording.')
    data = voice._archive(directory, stamp, locale, audio['package'], 'zzz').read(directory, entry.offset, entry.size)
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE' or len(data) != struct.unpack_from('<I', data, 4)[0] + 8:
        raise ValueError('Original ZZZ cinematic context is incomplete.')
    return data
