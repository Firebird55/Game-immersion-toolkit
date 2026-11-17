"""Conservative complete-source contexts for authored cinematic scenes.

A complete scene source preserves full utterances without claiming sentence
boundaries. Source duration alone never establishes its scene/dub/player owner.
"""
from contextlib import closing
import hashlib
import re
import sqlite3
import struct

from . import wuthering_assets as assets
from .wuthering_cinematics import MEDIA_ROOT, caption_cues


def full_scene_events(db_root):
    """Exact native VideoSound callers that play from scene zero to completion."""
    events = {}
    for scene, variant, blob in assets._rows(
            db_root / 'db_cgVedio.db', 'SELECT CgName, GirlOrBoy, BinData FROM videosound'):
        if variant != 2 or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', scene):
            continue
        path = assets._string(blob, 3)
        match = re.fullmatch(r'/Game/Aki/WwiseAudio/Events/([A-Za-z0-9_]{1,256})\.\1', path)
        if not match:
            continue
        def moment(column, default):
            at = assets._field(blob, column)
            if at is None:
                return default
            if at + 4 > len(blob):
                raise ValueError('Incomplete original cinematic source clock')
            return struct.unpack_from('<f', blob, at)[0]
        if moment(4, 0) == 0 and moment(5, -1) == -1:
            events.setdefault(scene, set()).add(match[1])
    return events


def _separate_sources(db_root, plot_audio_sha256):
    flagged = {assets._string(blob, 4) for blob, in assets._rows(
        db_root / 'db_cgVedio.db', 'SELECT BinData FROM videocaption')
        if assets._boolean(blob, 11)}
    if plot_audio_sha256 is None or not flagged:
        return flagged
    from .preparation_errors import PreparationFailure
    try:
        raw = (db_root / 'db_plot_audio.db').read_bytes()
        if (not isinstance(plot_audio_sha256, str) or not re.fullmatch('[0-9a-f]{64}', plot_audio_sha256)
                or hashlib.sha256(raw).hexdigest() != plot_audio_sha256):
            raise ValueError('Complete original PlotAudio bytes no longer match their verified input.')
        # Query the exact verified bytes. Native GetConfig binds CaptionText to
        # WHERE Id=?; SQLite collation/type semantics must not be replaced by a
        # Python set comparison. Even an existing empty/null row keeps the veto.
        with closing(sqlite3.connect(':memory:')) as database:
            database.deserialize(raw)
            with closing(database.cursor()) as statement:
                return {identity for identity in flagged if statement.execute(
                    'SELECT 1 FROM PlotAudio WHERE Id=? LIMIT 1', (identity,)).fetchone() is not None}
    except (OSError, ValueError, sqlite3.Error, AttributeError) as error:
        raise PreparationFailure('game_metadata_unavailable',
            'The complete official Wuthering dialogue audio metadata could not be verified or read. '
            'Retry preparation; the previous complete index and recordings are retained.') from error


def assign_contexts(db_root, records, locale, event_sources, source_shapes, *, plot_audio_sha256=None):
    """Add complete scene contexts after caller, bank and native source proof.

    event_sources comes from scene_sources with real selected-dub members;
    source_shapes comes from probing those exact original bytes. No per-scene
    IDs, guessed recording names, caption-derived cuts or ASR alignment is used.
    plot_audio_sha256 is supplied only after a complete publisher member read;
    without it, every separately flagged caption keeps the original veto.
    """
    events = full_scene_events(db_root)
    # build_language_records merges presentation evidence by text identity.
    # A cinematic's unresolved status must not hide an explicit silent use or
    # an unknown written presentation of the same visible words.
    unresolved_presentations = {
        identity for identity, evidence in assets._narrative_refs(db_root).items()
        if any(status == 'unvoiced' or status == 'unknown'
               and kind in {'story_card', 'readable', 'choice', 'message'} for kind, status in evidence)}
    # VideoView posts a flagged external source only when GetConfig finds its
    # exact key. A present config keeps the veto even if its pack/voice is
    # missing. Only a complete verified table can establish true absence.
    separate_sources = _separate_sources(db_root, plot_audio_sha256)
    owners = {}
    for scene, identity, _, _ in caption_cues(db_root, locale):
        owners.setdefault(identity, set()).add(scene)
    code = assets.VOICE_LOCALES[locale][0]
    additions, all_ids = [], {row['text_id'] for row in records}
    for row in records:
        if (row.get('audio') is not None or row.get('voice_status') != 'unavailable'
                or row.get('dialogue_kind') != 'cinematic'
                or not row['text_id'].startswith('wuwa:')
                or not any(character.isalnum() for character in row.get('source_text', ''))):
            additions.append(row)
            continue
        identity = re.sub(r':(?:female|male)$', '', row['text_id'][5:])
        if identity in unresolved_presentations or identity in separate_sources:
            additions.append(row)
            continue
        scenes = owners.get(identity, set())
        if len(scenes) != 1:
            additions.append(row)
            continue
        scene = next(iter(scenes))
        choices = [(event, event_sources[event]) for event in events.get(scene, ())
                   if event_sources.get(event)]
        if len(choices) != 1:
            additions.append(row)
            continue
        event, sources = choices[0]
        variants = []
        for source in sources:
            selected = row.get('player_voice')
            if selected and source.gender and selected != source.gender:
                continue
            variant = dict(row)
            if source.gender:
                variant['player_voice'] = source.gender
                if not selected:
                    variant['text_id'] += ':' + source.gender
                    if variant['text_id'] in all_ids:
                        variants = []
                        break
            shape = source_shapes.get(source.media_id)
            if (not source.authored_mute and shape and len(shape) == 2
                    and type(shape[0]) is int and shape[0] in (1, 2)
                    and type(shape[1]) is int and 0 < shape[1] <= 48000 * assets.FILM_CONTEXT_SECONDS):
                channels, frames = shape
                variant.update(audio_scope='context', voice_status='voiced', audio={
                    'depot': f'{MEDIA_ROOT}{code}/{source.media_id}.wem',
                    'locale': row['audio_locale'], 'scene_context': True, 'scene': scene,
                    'event': event, 'source_frames': frames, 'source_channels': channels})
            variants.append(variant)
        if variants and any(variant.get('audio') for variant in variants):
            additions.extend(variants)
        else:
            additions.append(row)
    records[:] = additions
