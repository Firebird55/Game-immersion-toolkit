"""Resolve original ZZZ sentence names to their exact selected-dub entries."""
from collections import defaultdict
import re

from .wwise_tables import voice_hash, wwise_short_id as _short_id
from .zzz_dialogue_records import voice_namespace


# A source name and its Wwise directory do not always use the same family.
# Only an exact file ID in the selected publisher pack establishes a binding.
VOICE_DIRECTORIES = {
    'galgame': ('VO_GalGame',), 'ongoing': ('VO_Ongoing',), 'ongoinglevel': ('VO_Ongoing',),
    'ongoingmaincity': ('VO_Ongoing',), 'ongoingmaincitypartner': ('VO_Ongoing',), 'ongoingantique': ('VO_Ongoing',),
    'level': ('VO_Level', 'VO_Accompany'), 'accompany': ('VO_Accompany',),
    'chessboard': ('VO_Chessboard',), 'tips': ('VO_Tips',), 'maincity': ('VO_MainCity', 'VO_Chat'),
    'chat': ('VO_Chat',), 'chatplus': ('VO_ChatPlus',), 'chatplustimeline': ('VO_Timeline', 'VO_ChatPlus'),
    'timeline': ('VO_Timeline', 'VO_TL'), 'cinema': ('VO_Cinema',), 'ongoingcinema': ('VO_Cinema',),
}


def source_paths(source, version):
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', source) or '..' in source:
        return set()
    if '/' in source:
        return {source}
    name = source.lower()
    directories = VOICE_DIRECTORIES.get(name.split('_', 1)[0], ())
    if name.startswith('vo_csr_timeline_'):
        directories = ('VO_TL',)
    elif name.startswith('activity_maincity_fishing_'):
        directories = ('VO_Maincity_NPC',)
    if not directories:
        return set()
    # Index membership decides among candidates, including unversioned launch files.
    major, minor, _ = map(int, version.split('.'))
    versions = [f'Ver{i}_{j}/' for i in range(1, major + 1)
                for j in range(1 + minor if i == major else 10)]
    speakers = {}
    for token in source.split('_')[1:]:
        if re.fullmatch(r'[A-Za-z0-9]+', token) and re.search('[A-Za-z]', token):
            speakers.setdefault(token.lower(), token)
    return {f'{family}/{v}VO_{s}/{source}' for family in directories for v in ['', *versions] for s in speakers.values()}


def voice_directory(directory):
    if not directory:
        return {}
    # Each block starts with the 32-bit hash of a directory, followed by
    # source-name hashes, and ends with zero. A directory can designate either
    # an actor's exact folder or a parent containing multiple actors.
    descendants = defaultdict(set)
    for prefix in directory['prefixes']:
        if (not isinstance(prefix, str) or len(prefix) > 240 or not prefix.endswith('/') or
                any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. '-]*", part) or '..' in part
                    for part in prefix[:-1].split('/'))):
            raise ValueError('Invalid released ZZZ voice directory path.')
        for match in re.finditer('/', prefix):
            parent = prefix[:match.end()]
            descendants[_short_id(parent)].add(prefix)
    groups = {key: tuple(sorted(paths)) for key, paths in descendants.items()}
    sources = defaultdict(set)
    group = None
    for value in directory['blocks']:
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('Invalid released ZZZ voice directory ID.')
        if group is None:
            if value not in groups:
                raise ValueError('Unknown group in the released ZZZ voice directory.')
            group = value
        elif value == 0:
            group = None
        else:
            sources[value].add(group)
    if group is not None:
        raise ValueError('Truncated released ZZZ voice directory.')
    return {key: tuple(groups[group] for group in ids) for key, ids in sources.items()}


def _directory_paths(source, directory):
    # Film soundtracks, effects and reaction pools cannot establish a separate
    # sentence take, even when the audio file itself exists.
    if (not re.fullmatch(r'[A-Za-z0-9_-]+', source) or
            re.search(r'(?:^|_)(?:(?:cinema)?breath\d*|sfx)(?:_|$)', source, re.I)):
        return set()
    return {prefix + source for folders in directory for prefix in folders
            if not re.search(r'(?:^|/)(?:VO_Breath|VO_Bubble|VO_Effect|Film|SFX_[^/]+|VO_Clue)/', prefix, re.I)}


def original_bindings(links, entries, dub, version, directory=None):
    namespace = voice_namespace(dub)
    candidates = defaultdict(set)
    for link in links:
        candidates[link['text_id']].add(link['source'])
    result = {}
    by_source = {}
    for identity, sources in candidates.items():
        # The prologue references the same take both as a bare name and as an
        # explicit directory/name. Every spelling must independently resolve to
        # one and the same file in this dub; a missing take is not an alias.
        if len({source.rsplit('/', 1)[-1].lower() for source in sources}) != 1:
            continue
        resolved = []
        for source in sorted(sources):
            if source not in by_source:
                groups = directory.get(_short_id(source)) if directory and '/' not in source else None
                paths = _directory_paths(source, groups) if groups is not None else source_paths(source, version)
                matches = []
                for path in paths:
                    full = f'{namespace}/ex/{path}.wem'
                    file_id = voice_hash(full)
                    if file_id in entries:
                        matches.append({**entries[file_id], 'source': full, 'file_id': f'{file_id:016x}', 'locale': dub})
                by_source[source] = matches[0] if len(matches) == 1 else None
            if by_source[source]:
                resolved.append(by_source[source])
        if len(resolved) == len(sources) and len({item['file_id'] for item in resolved}) == 1:
            result[identity] = resolved[0]
    return result
