"""Shared off-lane caption admission and authored occurrence policy."""
from dataclasses import dataclass

from .endfield_caption_context import EndfieldCaptionContext
from .steam_games import STEAM_GAMES


@dataclass(frozen=True)
class FloatingCaptionPolicy:
    film_cues: bool
    top_cues: bool
    song_cues: bool
    voice_enabled: bool
    silent_enabled: bool
    missing_enabled: bool

    @property
    def enabled(self):
        return self.voice_enabled or self.silent_enabled or self.missing_enabled

    def menu_blocks_frame(self, dialogue_menu):
        return self.song_cues and dialogue_menu


def floating_caption_policy(game, index, *, capture_unvoiced, capture_missing_audio):
    metadata = getattr(index, 'snapshot_metadata', {})
    film = game == 'endfield' and bool(metadata.get('publisher_film_cues', 0))
    top = game == 'endfield' and bool(metadata.get('publisher_top_dialogue_cues', 0))
    songs = game == 'wuwa' and bool(metadata.get('publisher_song_cues', 0))
    song_voices = game == 'wuwa' and bool(metadata.get('publisher_song_voices', songs))
    spec = STEAM_GAMES.get(game)
    voice = bool((film or top or song_voices or (spec and spec.floating_dialogue))
        and getattr(index, 'match_full_frame_voice_lines', None) and index.ready and index.audio_count)
    silent = bool(capture_unvoiced and getattr(index, 'match_unvoiced_lines', None) and index.ready
        and index.status().get('unvoiced_count', 0))
    missing = bool(capture_missing_audio and getattr(index, 'match_missing_audio_lines', None) and index.ready
        and index.status().get('missing_audio_count', 0))
    return FloatingCaptionPolicy(film, top, songs, voice, silent, missing)


def merge_authored_occurrence(index, matches, hit):
    """A display model cannot authorize replacing another source occurrence."""
    return {identity: old for identity, old in matches.items()
        if identity == hit.text_id or old.source_ocr != hit.source_ocr
        or not index.equivalent_caption_occurrence(old, hit)} | {hit.text_id: hit}


def observe_floating_contexts(index, groups, matches, contexts, policy, *, game,
        scope, now, stable_frames, capturable, dialogue_menu=False, excluded=False):
    modes = []
    if game == 'endfield' and policy.voice_enabled:
        modes.append(('film', 'cinematic', 'cinematic', False))
    if policy.song_cues and (policy.voice_enabled or policy.missing_enabled):
        modes.append(('music', 'music_subtitle', 'cinematic', True))
    if game == 'endfield' and policy.top_cues and policy.voice_enabled:
        modes.append(('top', 'conversation', 'cinematic', True))
    if game == 'endfield' and policy.silent_enabled:
        modes.append(('tutorial', 'tutorial_step', 'tip', True))
    for key, kind, channel, prefer in modes:
        context = contexts.setdefault(key, EndfieldCaptionContext())
        if dialogue_menu or excluded:
            context.reset()
            continue
        hit = context.observe(index, groups, matches.values(), channel=channel, kind=kind,
            scope=scope, now=now, stable_frames=stable_frames, prefer_authored_occurrence=prefer)
        if hit and capturable(hit):
            matches = merge_authored_occurrence(index, matches, hit) if prefer else {**matches, hit.text_id: hit}
    return matches
