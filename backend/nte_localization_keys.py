"""Approve a data-only text key only against a complete original locres member."""
from pathlib import Path
import hashlib
import struct

from . import nte_archive_metadata as metadata, nte_community_metadata as community
from . import nte_locres as locres


class LocalizationKeys:
    def __init__(self, catalog):
        self.catalog = catalog
        self.cache = catalog.cache/'format/community'
        revision, digest = catalog.snapshot['localization']
        self.primary = metadata.load_localization(revision=revision, digest=digest, cache=self.cache.parent)
        self._candidates = [(self.primary, None)]
        self._known = self._latest = False
        self.bindings = {}

    def _add(self, candidate):
        if any(row.digest == candidate.reference['sha256'] for row, _ in self._candidates):
            return
        parsed = metadata.load_localization(revision=candidate.reference['revision'],
            digest=candidate.reference['sha256'], cache=self.cache.parent, fetch=lambda *_: candidate.data)
        self._candidates.append((parsed, candidate))

    def _prove(self, description, candidate, path, data):
        rows = locres.parse(data, description.parameter)
        encrypted = struct.unpack_from('<i', data, 21)[0] == 1
        string_count = struct.unpack_from('<i', data, struct.unpack_from('<q', data, 25)[0])[0]
        needs_key = encrypted and string_count > 0
        if needs_key and candidate is None:
            source = self.cache.parent/f'{description.revision}-{description.digest}.txt'
            candidate = community.retain('localization', description.revision, description.digest,
                                          source.read_bytes(), self.cache)
        catalog = self.catalog
        # The caller acquired data through the original overlay and complete
        # signed PAK member integrity check before any metadata attempt.
        location = catalog.location(path)
        metadata.check(location is not None and location[0] in catalog.snapshot['files'])
        proof = (community.remember(candidate, catalog.keyring.original, 'localization', data, self.cache)
                 if needs_key else None)
        self.bindings[path] = {'archive': location[0], 'member_sha256': hashlib.sha256(data).hexdigest(),
                               'metadata': proof, 'key_required': needs_key}
        return rows

    def parse(self, path, data):
        try:
            return self._prove(self.primary, None, path, data)
        except locres.LocalizationParameterMismatch:
            if not getattr(self.catalog.keyring, 'allow_community_fallback', False):
                raise
        if not self._known:
            for ref in community.known('localization', self.cache, self.catalog.region):
                self._add(community.load('localization', self.cache, retained=ref))
            self._known = True
        for description, candidate in self._candidates[1:]:
            try:
                return self._prove(description, candidate, path, data)
            except locres.LocalizationParameterMismatch:
                continue
        if not self._latest:
            self._latest = True
            self._add(community.load('localization', self.cache))
            return self._prove(*self._candidates[-1], path, data)
        raise locres.LocalizationParameterMismatch()
