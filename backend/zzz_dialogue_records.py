"""Shared ZZZ subtitle joins and original voice evidence."""
from collections import defaultdict

from .languages import audio_locale
from .models import is_comic_text_id
from .textmaps import display_text, gender_variants

LANGUAGE_INDEX_VERSION = 24
TEXT_LOCALES = {'en': 'EN', 'zh-Hans': '', 'zh-Hant': 'CHT', 'ja': 'JA', 'ko': 'KO',
    'fr': 'FR', 'de': 'DE', 'es-ES': 'ES', 'pt-BR': 'PT', 'ru': 'RU', 'th': 'TH', 'vi': 'VI', 'id': 'ID'}
SCOPE = ('Publisher preparation covers catalogue-matched dialogue scenes, motion comics, phone messages, replies, gameplay tips, ongoing dialogue and timed clue recordings. '
         'Selected original updater inventories include in-version text, scene and voice changes. Other presentations remain partially covered.')

def voice_namespace(locale):
    return {'en': 'English(EN)', 'ja': 'Japanese(JP)', 'ko': 'Korean(KR)',
            'zh-Hans': 'Chinese(PRC)', 'zh-Hant': 'Chinese(PRC)'}[locale]


def _text(text, gender):
    variants = gender_variants(text)
    return variants.get(gender, '') if variants else display_text(text)


def _group_links(links):
    expanded, channels, evidence, kinds = [], {}, {}, {}
    for link in links:
        identity = link['text_id']
        channels.setdefault(identity, set()).update(link.get('channels', ['dialogue', 'cinematic']))
        kinds.setdefault(identity, set()).add(link.get('dialogue_kind') or
            ('comic' if is_comic_text_id(identity) else 'cutscene' if identity.startswith('CS_') else 'conversation'))
        status = link.get('voice_status') or ('unavailable' if link.get('source') else 'unknown')
        sources = gender_variants(link['source'])
        if sources:
            expanded.extend({'text_id': identity + ':' + gender, 'source': source} for gender, source in sources.items() if source)
            for gender, source in sources.items():
                evidence.setdefault(identity + ':' + gender, set()).add(status if source else 'unknown')
        elif link.get('gender'):
            expanded.append({'text_id': identity + ':' + link['gender'], 'source': link['source']})
            evidence.setdefault(identity + ':' + link['gender'], set()).add(status)
        else:
            if link['source']:
                expanded.append({'text_id': identity, 'source': link['source']})
            evidence.setdefault(identity, set()).add(status)
    return expanded, channels, evidence, kinds


def _dialogue_records(tables, source_locale, selected, channels, evidence, kinds, bindings, extra_ids=()):
    identities = set(channels).union(extra_ids, (key for key in tables[source_locale] if is_comic_text_id(key)))
    rows = []
    for identity in sorted(identities):
        values = {locale: table.get(identity, '') for locale, table in tables.items()}
        gendered = any(gender_variants(values.get(locale, '')) for locale in selected) or any(
            identity + ':' + gender in evidence or identity + ':' + gender in bindings for gender in ('M', 'F'))
        for gender in ('M', 'F') if gendered else (None,):
            text = _text(values.get(source_locale, ''), gender)
            if not text:
                continue
            texts = {locale: value for locale in selected if (value := _text(values.get(locale, ''), gender))}
            row_id = identity + ':' + gender if gender else identity
            binding = bindings.get(row_id)
            if gender and row_id not in evidence and not binding:
                binding = bindings.get(identity)
            audio = binding
            states = evidence.get(row_id, evidence.get(identity, {'unknown'}))
            voice_status = 'voiced' if audio else 'unavailable' if 'unavailable' in states else 'unvoiced' if states == {'unvoiced'} else 'unknown'
            kind = next((kind for kind in ('comic', 'cutscene', 'conversation', 'message', 'choice', 'narration', 'ambient', 'gameplay_tip') if kind in kinds.get(identity, set())),
                'comic' if is_comic_text_id(identity) else 'cutscene' if identity.startswith('CS_') else 'conversation')
            rows.append({'text_id': row_id, 'source_locale': source_locale, 'source_text': text,
                'texts': texts, 'english': _text(values.get('en', ''), gender), 'chinese': texts.get('zh-Hans', ''),
                'audio_locale': audio_locale(source_locale), 'audio': audio,
                **({'audio_scope': 'context'} if audio and audio.get('audio_scope') == 'context' else {}),
                'player_voice': {'M': 'male', 'F': 'female'}.get(gender),
                'member_text_ids': [identity] if gender else None,
                'voice_status': voice_status, 'dialogue_kind': kind,
                'channels': sorted(channels.get(identity, {'cinematic'}))})
    return rows


def _omit_requested_audio(rows, links, expanded, stamp, dub):
    """Keep original authored evidence without making it a playable binding.

    A source/event reference alone does not establish that its selected-dub
    recording exists. In particular it must not promote unavailable to voiced.
    The ordinary caption matcher still applies duplicate/player/context guards.
    """
    sources, events = defaultdict(set), defaultdict(set)
    for link in expanded:
        sources[link['text_id']].add(link['source'])
    for link in links:
        if link.get('cinematic_event'):
            events[link['text_id']].add(link['cinematic_event'])
    for row in rows:
        identity = row['text_id']
        original = (row.get('member_text_ids') or [identity])[0]
        binding = {'publisher': stamp, 'locale': dub,
                   'sources': sorted(sources.get(identity, sources.get(original, ()))),
                   'cinematic_events': sorted(events.get(original, ())),
                   'voice_status': row['voice_status']}
        row.update(audio=None, source_voice_binding=binding if binding['sources'] or binding['cinematic_events'] else None,
                   audio_omitted_by_request=row['voice_status'] != 'unvoiced',
                   text_capture_verified=True)
        if binding['cinematic_events']:
            row['audio_scope'] = 'context'
    return rows
