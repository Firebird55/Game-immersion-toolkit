"""Host registry entry for the proven Reverse: 1999 discovery stage."""
from __future__ import annotations

import json
from urllib.error import URLError
from urllib.parse import urlsplit

from .game_data_protocol import GameDataError
from .publisher_transport import PublisherTransport
from .reverse1999_provider import Reverse1999Provider
from . import reverse1999_release as publisher

PLATFORMS = frozenset(('android', 'windows', 'linux', 'macos'))
METADATA_HOSTS = frozenset((urlsplit(publisher.GLOBAL_SITE).hostname, *publisher.GLOBAL_UPDATE_HOSTS))


class Reverse1999GameDataProvider(Reverse1999Provider):
    def __init__(self, *, platform, native=None, transport_factory=PublisherTransport):
        if not isinstance(platform, str) or platform not in PLATFORMS:
            raise GameDataError('unsupported_game_data_platform', 'This game data platform is unsupported.')
        self.platform = platform
        # Native/audio services are intentionally unused by a metadata-only stage.
        # Future materialization must remain inside the selected approved plan.
        self.transport_factory = transport_factory
        super().__init__(metadata_fetch=self._fetch_metadata)

    def _fetch_metadata(self, ctx, url, *, body, limit):
        payload = None if body is None else json.dumps(body, separators=(',', ':')).encode('utf-8')
        transport = self.transport_factory(ctx, hosts=METADATA_HOSTS)
        try:
            raw, _receipt = transport.fetch_bytes(url, limit=limit, kind='metadata',
                method='GET' if payload is None else 'POST', body=payload,
                headers={'Content-Type': 'application/json', 'lang': 'en'})
        except GameDataError as error:
            # The source discovery has its own explicit publisher backup list.
            # Semantic/consent/checksum failures must not silently switch hosts.
            if error.code == 'metadata_download_interrupted':
                raise URLError('Original publisher metadata was unavailable.') from error
            raise
        return raw


def create_provider(*, platform, native=None):
    return Reverse1999GameDataProvider(platform=platform, native=native)
