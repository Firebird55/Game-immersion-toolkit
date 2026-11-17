"""Per-original-archive key selection; community descriptions never approve keys.

Only a supported, complete publisher index checksum can admit a candidate. The
same region, manifest and signed source own every retained proof. Raw key values
are private in-memory inputs, not profile/source identifiers.
"""
from dataclasses import asdict
import hashlib
from pathlib import Path
import struct
import threading

from Crypto.Cipher import AES

from . import nte_archive_metadata as metadata, nte_community_metadata as community


class KeyRing:
    def __init__(self, primary, cache, original, *, sealed=None, allow_community_fallback=False):
        self.primary, self.cache = primary, Path(cache)
        self.original = community.original(original)
        self.region = original['region']
        self.parameters = primary.parameters if primary is not None else {}
        self._candidates = [(primary, None)] if primary is not None else []
        self.sealed = sealed
        metadata.check(type(allow_community_fallback) is bool)
        self.allow_community_fallback = allow_community_fallback
        metadata.check(primary is not None or isinstance(sealed, dict))
        self._known_loaded = self._queried = False
        self._lock = threading.RLock()
        self.bindings = {}

    def _fixed(self):
        path = self.cache.parent / f'{self.primary.revision}-{self.primary.digest}.txt'
        metadata.check(path.is_file() and 0 < path.stat().st_size <= metadata.LIMIT)
        return community.retain('archive', self.primary.revision, self.primary.digest,
                                path.read_bytes(), self.cache)

    def _add(self, candidate):
        if any(row.digest == candidate.reference['sha256'] for row, _ in self._candidates):
            return
        # Existing source parser enforces exact game/region labels, complete
        # key widths and uniqueness. This callback supplies data, never code.
        parsed = metadata.load(revision=candidate.reference['revision'], digest=candidate.reference['sha256'],
            cache=self.cache.parent, fetch=lambda _url, _limit: candidate.data)
        self._candidates.append((parsed, candidate))

    def _prove(self, catalog, candidate, read, size, source):
        key = catalog.verified_key(read, size, self.region, source=source)
        if key is None:
            return None
        metadata.check(source is not None and source.region == self.region
                       and source.branch == self.original['branch'] and source.item.size == size)
        tail_size = min(512, size)
        footer = read(size-tail_size, tail_size)
        marker = footer.rfind(metadata.MAGIC)
        metadata.check(marker >= 17)
        offset, length = struct.unpack_from('<QQ', footer, marker+8)
        encrypted = read(offset-1, (length+15)//16*16)
        plain = AES.new(bytes.fromhex(key[2:]), AES.MODE_ECB).decrypt(encrypted)[:length]
        metadata.check(hashlib.sha1(plain).digest() == footer[marker+24:marker+44])
        candidate = candidate or self._fixed()
        if self.sealed is None:
            receipt = community.remember(candidate, self.original, 'archive-index', plain, self.cache)
        else:
            expected = self.sealed[source.item.digest]
            receipt = expected['metadata']
            proof = community.check_receipt(receipt, self.original, self.cache)
            metadata.check(proof['verification'] == {'kind': 'archive-index',
                'sha256': hashlib.sha256(plain).hexdigest()} and receipt['source'] == candidate.reference)
        binding = {'archive': asdict(source.item), 'signature': asdict(source.signature),
                   'guid': footer[marker-17:marker-1].hex(),
                   'index_sha256': hashlib.sha256(plain).hexdigest(), 'metadata': receipt,
                   'key_sha256': hashlib.sha256(bytes.fromhex(key[2:])).hexdigest()}
        metadata.check(self.sealed is None or self.sealed[source.item.digest] == binding)
        with self._lock:
            previous = self.bindings.get(source.item.digest)
            metadata.check(previous is None or previous == binding)
            self.bindings[source.item.digest] = binding
        return key

    def verified_key(self, read, size, region=None, *, source=None):
        metadata.check(region == self.region)
        if self.sealed is not None:
            metadata.check(source is not None)
            # A plaintext index has no key material; verify it through the
            # normal parser without consulting any metadata or latest source.
            tail = read(max(0, size-512), min(512, size))
            marker = tail.rfind(metadata.MAGIC)
            metadata.check(marker >= 17)
            if tail[marker-1] == 0:
                return None
            binding = self.sealed.get(source.item.digest)
            metadata.check(isinstance(binding, dict) and binding['archive'] == asdict(source.item)
                           and binding['signature'] == asdict(source.signature))
            ref = binding['metadata']['source']
            candidate = community.load('archive', self.cache, retained=ref)
            catalog = metadata.load(revision=ref['revision'], digest=ref['sha256'], cache=self.cache.parent,
                                    fetch=lambda _url, _limit: candidate.data)
            return self._prove(catalog, candidate, read, size, source)
        try:
            return self._prove(self.primary, None, read, size, source)
        except metadata.ArchiveParameterMismatch:
            if not self.allow_community_fallback:
                raise
        # Serialize only the incompatible path. Concurrent archive mounts do
        # not each query latest or admit cross-generation cipher state.
        with self._lock:
            if not self._known_loaded:
                for ref in community.known('archive', self.cache, self.region):
                    self._add(community.load('archive', self.cache, retained=ref))
                self._known_loaded = True
            for candidate, proof_source in self._candidates[1:]:
                try:
                    return self._prove(candidate, proof_source, read, size, source)
                except metadata.ArchiveParameterMismatch:
                    continue
            if not self._queried:
                self._queried = True
                self._add(community.load('archive', self.cache))
                candidate, proof_source = self._candidates[-1]
                return self._prove(candidate, proof_source, read, size, source)
        raise metadata.ArchiveParameterMismatch()

    def proved_keys(self, archives):
        keys = []
        for archive in archives:
            if archive.selected_key is None:
                continue
            binding = self.bindings.get(archive.source.item.digest)
            metadata.check(binding is not None and binding['key_sha256'] ==
                           hashlib.sha256(bytes.fromhex(archive.selected_key[2:])).hexdigest())
            if archive.selected_key not in keys:
                keys.append(archive.selected_key)
        metadata.check(0 < len(keys) <= 8)
        return keys
