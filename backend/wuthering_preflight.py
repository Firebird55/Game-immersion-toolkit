"""Platform-neutral original PAK plans; no network, key store or subprocess IO."""
from dataclasses import dataclass
import re


def manifest_upper_bound(snapshot, channels):
    """Coarse original-owner bound before complete member indices are available.

    This does not turn compressed package sizes into a fake installed size.
    The caller must still enforce its separate discovery/metadata reservation.
    """
    if (not isinstance(snapshot, dict) or not isinstance(snapshot.get('base'), dict)
            or not isinstance(snapshot.get('products', {}), dict)
            or not isinstance(snapshot.get('root'), str)
            or not channels or not set(channels) <= {'resource', 'en', 'ja', 'ko', 'zh'}):
        raise ValueError('A selected original manifest inventory is required.')
    owners = {}
    def add(url, size, digest):
        if (not isinstance(url, str) or not url or type(size) is not int or size <= 0
                or not isinstance(digest, str) or not re.fullmatch(r'(?:[0-9a-f]{32}|[0-9a-f]{40})', digest)):
            raise ValueError('Invalid original manifest owner.')
        if url in owners and owners[url] != (size, digest):
            raise ValueError('Conflicting original manifest owners.')
        owners[url] = size, digest
    for name, value in snapshot['base'].items():
        add(snapshot['root'] + '/' + name, *value)
    for name, value in snapshot.get('products', {}).items():
        if name.split('/', 1)[0] in channels:
            add(*value)
    sizes = [size for size, _ in owners.values()]
    return {'policy': 'original_manifest_owner_upper_bound', 'owner_count': len(owners),
            'all_selected_archive_bytes': sum(sizes),
            'index_body_max_bytes': sum(min(512, size) + 16 + 2 * min(64 * 1024**2, size) for size in sizes),
            'installed_disk_size_known': False,
            'limits': 'Selected owner ceiling, not a request to download whole archives. '
                      'Discovery responses, member metadata and derived output require separate caps. '
                      'Complete indices are needed for the selective payload/disk plan.'}


@dataclass(frozen=True)
class MemberPlan:
    owner_bytes: int
    offset: int
    header_bytes: int
    body_bytes: int
    plain_bytes: int
    compression: str
    compression_index: int
    stored_bytes: int
    blocks: int
    block_size: int
    block_lengths: tuple
    encrypted: bool
    custom: int

    def __post_init__(self):
        fields = (self.owner_bytes, self.offset, self.header_bytes, self.body_bytes,
                  self.plain_bytes, self.compression_index, self.stored_bytes,
                  self.blocks, self.block_size, self.custom)
        if (any(type(value) is not int or value < 0 for value in fields)
                or not self.header_bytes or not self.body_bytes or not self.plain_bytes
                or self.offset + self.header_bytes + self.body_bytes > self.owner_bytes
                or self.stored_bytes > self.body_bytes
                or self.compression not in ('None', 'Zlib', 'Oodle')
                or type(self.encrypted) is not bool):
            raise ValueError('Invalid original member plan.')

    @property
    def ranges(self):
        return ((self.offset, self.header_bytes),
                (self.offset + self.header_bytes, self.body_bytes))


def selection_plan(members, *, metadata_max_bytes, derived_output_max_bytes):
    """Cold-body maximum; cache reuse may reduce it, never silently increase it.

    Metadata and derived JSON/PCM/export output require explicit separate caps.
    Plans do not authenticate member bodies until ordinary extraction checks.
    """
    if any(type(value) is not int or value < 0 for value in (metadata_max_bytes, derived_output_max_bytes)):
        raise ValueError('Explicit nonnegative preflight reservations are required.')
    owners, entries = {}, {}
    for owner, plan in members:
        if not isinstance(owner, str) or not owner or not isinstance(plan, MemberPlan):
            raise ValueError('An original owner and validated member plan are required.')
        if owner in owners and owners[owner] != plan.owner_bytes:
            raise ValueError('Conflicting original package sizes.')
        owners[owner] = plan.owner_bytes
        key = owner, plan.offset
        if key in entries and entries[key] != plan:
            raise ValueError('Conflicting original member plans.')
        entries[key] = plan
    body_bytes = sum(p.header_bytes + p.body_bytes for p in entries.values())
    plain_bytes = sum(p.plain_bytes for p in entries.values())
    return {'policy': 'original_index_selection_maximum', 'member_count': len(entries),
            'owner_count': len(owners), 'metadata_max_bytes': metadata_max_bytes,
            'payload_body_max_bytes': body_bytes,
            'download_body_max_bytes': metadata_max_bytes + body_bytes,
            'original_plaintext_bytes': plain_bytes,
            'derived_output_max_bytes': derived_output_max_bytes,
            'retained_payload_and_derived_max_bytes': plain_bytes + derived_output_max_bytes,
            'largest_member_body_and_plain_bytes': max((p.header_bytes + p.body_bytes + p.plain_bytes
                                                       for p in entries.values()), default=0),
            'required_compressions': sorted({p.compression for p in entries.values()}),
            'limits': 'Body bytes exclude HTTP/TLS overhead and retries. Metadata, filesystem/cache overhead, '
                      'atomic replacement and decoded/encoded output need enforced reservations. '
                      'Member contents remain unverified until extraction.'}
