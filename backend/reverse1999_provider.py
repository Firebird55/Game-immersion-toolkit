"""Conservative publisher-discovery stage for independent Android/PC preparation.

The host injects bounded, accounted metadata transport. No game assets are
acquired here, and source discovery must never activate a dialogue snapshot.
"""
from __future__ import annotations
from urllib.error import HTTPError, URLError

from .game_data_protocol import GameDataError, GameDataPlan, GameDataRequest, PreparationContext
from . import reverse1999_release as publisher

SCHEMA = 'reverse1999-source-stage-v1'
TEXT_LOCALES = frozenset(('en', 'ja', 'ko', 'zh', 'zh-Hans', 'zh-Hant'))
CONTENT_MODES = frozenset(('text', 'text-audio'))


def _selection(request):
    mode = getattr(request, 'content_mode', None)
    if not isinstance(mode, str) or mode not in CONTENT_MODES:
        raise GameDataError('repair_needed', 'Choose text or text and audio, then check this game again.', 409)
    if (request.region not in ('global', 'cn') or request.source_locale not in TEXT_LOCALES
            or any(locale not in TEXT_LOCALES for locale in request.target_locales)
            or len(set(request.target_locales)) != len(request.target_locales)):
        raise GameDataError('reverse1999_languages', 'Choose official Reverse: 1999 text languages.')
    return {'region': request.region, 'source_locale': request.source_locale,
            'target_locales': sorted(request.target_locales), 'content_mode': mode}


class Reverse1999Provider:
    title = 'Reverse: 1999'

    def __init__(self, *, metadata_fetch=None):
        """metadata_fetch(ctx, url, *, body, limit) owns byte accounting.

        The shared host supplies allowed-host/redirect/limit enforcement and
        accounts all received bytes, including failed or malformed responses.
        This provider additionally bounds successful responses before parsing.
        """
        self.metadata_fetch = metadata_fetch

    def plan(self, request: GameDataRequest, ctx: PreparationContext) -> GameDataPlan:
        ctx.check()
        selection = _selection(request)
        handle = {'schema': SCHEMA, 'game': 'reverse1999', 'request': selection,
                  'content_mode': selection['content_mode'],
                  'selection_bytes': {'text': None, 'shared': None,
                                      'audio': 0 if selection['content_mode'] == 'text' else None},
                  'dialogue_preparation_implemented': False}
        revision = 'reverse1999/' + request.region + '/source-pending/' + selection['content_mode']
        message = 'Reverse: 1999 data preparation is not available yet.'
        if request.region == 'global' and self.metadata_fetch is not None:
            def fetch(url, *, body=None):
                ctx.check()
                if ctx.remaining_bytes(kind='metadata') < publisher.METADATA_LIMIT:
                    raise GameDataError('transfer_budget_exceeded', 'The game source exceeded its metadata budget.')
                raw = self.metadata_fetch(ctx, url, body=body, limit=publisher.METADATA_LIMIT)
                ctx.check()
                if not isinstance(raw, bytes) or not 0 < len(raw) <= publisher.METADATA_LIMIT:
                    raise GameDataError('invalid_publisher_metadata', 'The game source returned incomplete metadata.')
                return raw

            try:
                inventory = publisher.discover(fetch=fetch)
            except (ValueError, KeyError, UnicodeError, HTTPError, URLError) as error:
                raise GameDataError('reverse1999_source_unavailable',
                                    'The original game source check did not complete. Existing data is kept.', 503) from error
            handle['publisher_inventory'] = inventory
            revision = ('reverse1999/global/' + inventory['version'] + '/'
                        + inventory['resource_revision'] + '/' + selection['content_mode'])
            message = 'Original game sources found. Selected game data cannot be prepared yet.'
        ctx.check()
        # Complete client sizes in the private source handle are not the user's
        # selected text/audio estimate. Missing selected sizes stay unknown.
        return GameDataPlan(revision, None, None, handle=handle, runtime_available=False,
                            stage='publisher-discovery', message=message)

    def download(self, plan: GameDataPlan, ctx: PreparationContext):
        ctx.check()
        selection = _selection(ctx.request)
        if (plan.handle.get('schema') != SCHEMA or plan.handle.get('game') != 'reverse1999'
                or plan.handle.get('content_mode') != selection['content_mode']
                or plan.handle.get('request') != selection):
            raise GameDataError('game_data_plan_changed', 'Check this game’s selected download again.', 409)
        raise GameDataError('reverse1999_preparation_incomplete',
                            'Selected Reverse: 1999 data cannot be prepared yet. Existing data is kept.', 409)

    def restore(self, handle, ctx: PreparationContext):
        ctx.check()
        selection = _selection(ctx.request)
        if (not isinstance(handle, dict) or handle.get('schema') != SCHEMA or handle.get('game') != 'reverse1999'
                or handle.get('content_mode') != selection['content_mode']
                or handle.get('request') != selection):
            raise GameDataError('repair_needed', 'Check this game’s selected download again. Saved history stays.', 409)
        raise GameDataError('reverse1999_preparation_incomplete',
                            'Original source discovery is not a prepared game. Existing data is kept.', 409)
