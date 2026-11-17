"""Context-local event/player/sequence inventory, without implicit dub policy."""
from dataclasses import dataclass

from . import starrail_events as events
from . import starrail_game_audio as audio
from .hoyo_dialogue import voice_namespace


@dataclass(frozen=True)
class EventInventory:
    quote: audio.Quote
    bindings: dict
    unresolved: dict
    choices: dict


def event_inventory(inventory, raw, names, store, locale):
    """Read exact Play/state joins, retaining unsupported switch choices."""
    lookup, state_refs, _ = events.bank_lookup(raw, with_states=True)
    quote, targets = audio.localized_bank_quote(inventory, lookup, names, store, locale)
    if quote.spans:
        audio._fail('The required original localized event banks are incomplete.')
    language = voice_namespace('starrail', locale)
    localized, streams = {}, {}
    for directory in inventory:
        if directory.owner.name.startswith(language + '/'):
            events._unique(localized, directory.banks)
            events._unique(streams, directory.sounds)
    loaded = {bid: events._bank(store.read(span), bid, language) for bid, _, span in set(targets.values())}
    hashes = {}
    for name in names:
        hashes.setdefault(events.wwise_hash(name), set()).add(name.lower())
    unique = {key for key, values in hashes.items() if len(values) == 1}
    stream_entries = {key: events.Entry(span.owner, span.start, span.length)
                      for key, span in streams.items() if span is not None}
    result, unresolved, switches, dependencies, choices = {}, {}, [], set(), {}
    male, female = (events.wwise_hash('state_' + gender) for gender in ('male', 'female'))
    player = {male: 'male', female: 'female'}
    for key in hashes:
        if key not in unique or key not in targets:
            unresolved[key] = 'event-owner-unresolved'
            continue
        bid, target, span = targets[key]
        objects, embedded = loaded[bid]
        obj = objects.get(target)
        if obj and obj[0] == 6:
            switch = events._switch(obj[1])
            state = events._state_banks(raw, state_refs[key]) if key in state_refs else None
            if (not switch or not state or switch[0] != state[0]
                    or {value for value, nodes in switch[2].items() if nodes}
                    != {value for value, banks in state[1].items() if banks}):
                unresolved[key] = 'state-owner-unresolved'
                continue
            # Player state semantics are evidenced by the actual named state
            # hashes. Other switches, including copyright-language switches,
            # require an explicit authored policy/choice. The event's name or
            # selected study language cannot supply that missing choice.
            if not player.keys() <= switch[2].keys() <= player.keys() | {events.wwise_hash('none')}:
                unresolved[key] = 'state-choice-required'
                choices[key] = {'group': switch[0], 'default': switch[1],
                    'states': [{'id': value, 'children': list(nodes), 'banks': list(state[1].get(value, ()))}
                               for value, nodes in sorted(switch[2].items())]}
                continue
            for value, variant in player.items():
                nodes, banks = switch[2][value], state[1].get(value, ())
                if len(nodes) == len(banks) == 1 and localized.get(banks[0]) is not None:
                    switches.append((key, variant, bid, target, nodes[0], banks[0]))
                    dependencies.add(banks[0])
                else:
                    unresolved[key] = 'player-state-unresolved'
            continue
        entry = events.Entry(span.owner, span.start, span.length)
        if recordings := events._recordings(objects, embedded, entry, target, stream_entries):
            result[key] = recordings
        else:
            unresolved[key] = 'event-media-unresolved'
    state_spans = store.missing(localized[bid] for bid in dependencies)
    quote = audio.Quote('audio-state-banks', audio.coalesce(state_spans))
    if not quote.spans:
        extra = {bid: events._bank(store.read(localized[bid]), bid, language) for bid in dependencies}
        for key, variant, bid, parent, child, dependency in switches:
            span = localized[dependency]
            found = events._recordings(loaded[bid][0], extra[dependency][1],
                events.Entry(span.owner, span.start, span.length), child, stream_entries, variant, parent)
            if found:
                result.setdefault(key, {}).update(found)
            else:
                unresolved[key] = 'player-media-unresolved'
    return EventInventory(quote,
        {name: {variant: (mid, audio.Span(entry.asset, entry.offset, entry.size))
                for variant, (mid, entry) in result.get(events.wwise_hash(name), {}).items()}
         for name in names if events.wwise_hash(name) in result},
        {name: unresolved[events.wwise_hash(name)] for name in names if events.wwise_hash(name) in unresolved},
        {name: choices[events.wwise_hash(name)] for name in names if events.wwise_hash(name) in choices})


def recording_quote(bindings, store):
    spans = {span for options in bindings.values() for _, span in options.values()}
    return audio.Quote('audio-streamed-members', audio.coalesce(store.missing(spans), gap=0))


def external_quote(inventory, sources, store, locale):
    """Quote all supported authored paths; missing hashes stay explicit."""
    sources = set(sources)
    bindings = audio.external_members(inventory, sources, locale)
    quote = audio.Quote('audio-external-members', audio.coalesce(store.missing(bindings.values()), gap=0))
    return quote, bindings, tuple(sorted(sources-bindings.keys()))
