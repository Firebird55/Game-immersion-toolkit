"""Context-owned original native-member stage, never a ready game library.

The managed source owner supplies the import; original launcher declarations
supply split artifacts. Planning reads only the small ZIP directory/envelope.
The separately approved payload must pass complete CRC and publisher signature.
The returned stage is not an active AKPK master or publisher dialogue proof.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import zlib

from .endfield_client_archive import Archive, MAX_MEMBER
from .endfield_client_source import identity_stamp
from .endfield_native_import import Import
from . import endfield_publisher_signature as signature

RECHECK_METADATA_UPPER = 2 * 1024**2
RECEIPT_DISK_UPPER = 2 * 1024**2


def _helpers():
    # Shared pure core: no game_tools/runtime/prepared-library/ZIP dependency.
    from .game_data import _read, _write, _write_bytes
    from .game_data_protocol import GameDataError
    from .private_data_paths import _no_links
    return _read, _write, _write_bytes, GameDataError, _no_links


def _strong(value):
    return (isinstance(value, str) and 2 <= len(value) <= 1024 and
            re.fullmatch(r'"[\x21\x23-\x7e]*"', value) is not None)


class OriginalNativeSource:
    """Use only the provider's explicit transport and same-request context."""

    def __init__(self, ctx, identity, transport):
        self.ctx, self.identity, self.transport = ctx, identity, transport
        self.client = identity_stamp(identity)
        self.root = Path(ctx.cache_directory) / 'endfield-original-native' / self.client
        self.kind = 'metadata'
        self.receipts = {}
        self.archive = Archive(identity['artifacts'], self._read_part)

    def _admit(self):
        _, _, _, Error, _ = _helpers()
        self.ctx.check()
        if self.ctx.game != 'endfield' or self.ctx.request.content_mode != 'text-audio':
            raise Error('audio_not_requested', 'Endfield original audio parameters are only prepared when audio is requested.')
        if self.identity.get('region') != self.ctx.request.region:
            raise Error('invalid_game_languages', 'Endfield original native source belongs to another selected region.')
        from .preparation_errors import PreparationFailure
        try:
            signature.source_runtime()
        except PreparationFailure as error:
            raise Error(error.code, str(error)) from error

    def _read_part(self, number, offset, size):
        read, write, write_bytes, Error, no_links = _helpers()
        self.ctx.check()
        item = self.identity['artifacts'][number]
        if not 0 < size <= MAX_MEMBER or not 0 <= offset <= item['bytes'] - size:
            raise Error('publisher_range_changed', 'Endfield original archive range leaves its declared artifact.')
        parent = self.root / ('part-' + str(number))
        owner_path = parent / 'owner.json'
        no_links(owner_path)
        owner = read(owner_path)
        if owner is not None and (not isinstance(owner, dict) or owner.get('client') != self.client or
                owner.get('artifact') != item or not _strong(owner.get('etag'))):
            raise Error('invalid_local_state', 'Endfield original archive ownership needs repair.')
        expected = {'client': self.client, 'artifact': item,
                    'range': [offset, size, item['bytes']]}
        path = parent / f'{offset}-{size}.bin'
        receipt_path = path.with_suffix('.json')
        no_links(path)
        receipt = read(receipt_path)
        if isinstance(receipt, dict) and owner is not None and all(receipt.get(k) == v for k, v in expected.items()) and receipt.get('etag') == owner['etag']:
            try:
                if path.stat().st_size == size:
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() == receipt.get('sha256'):
                        self.receipts[(number, offset, size)] = receipt
                        return raw
            except FileNotFoundError:
                pass
        headers = {'If-Match': owner['etag']} if owner else None
        arguments = dict(limit=size, expected_size=size, kind=self.kind,
                         original_range=(offset, size, item['bytes']), headers=headers)
        if self.kind == 'asset':
            transfer = self.transport.download_to(item['url'], path, **arguments)
            no_links(path)
            if path.stat().st_size != size:
                raise Error('publisher_size_changed', 'Endfield original archive range size differs.')
            raw = path.read_bytes()
        else:
            raw, transfer = self.transport.fetch_bytes(item['url'], **arguments)
        tag = getattr(transfer, 'response_etag', None)
        if not _strong(tag) or owner and tag != owner['etag']:
            raise Error('publisher_object_changed', 'Endfield original archive object changed. Check its size again.', 409)
        if (transfer.original_range != (offset, size, item['bytes']) or transfer.bytes != size or
                len(raw) != size or hashlib.sha256(raw).hexdigest() != transfer.sha256):
            raise Error('publisher_range_changed', 'Endfield original archive receipt differs from its declared range.')
        self.ctx.check()
        if self.kind == 'metadata':
            write_bytes(path, raw)
        receipt = {**expected, 'etag': tag, 'sha256': transfer.sha256,
                   'transfer': transfer.json(), 'whole_part_md5_verified': False}
        write(receipt_path, receipt)
        if owner is None:
            write(owner_path, {'client': self.client, 'artifact': item, 'etag': tag})
        self.ctx.check()
        self.receipts[(number, offset, size)] = receipt
        return raw

    def plan(self, original_import):
        self._admit()
        _, _, _, Error, _ = _helpers()
        if not isinstance(original_import, Import):
            raise Error('unverified_original_import', 'Endfield original audio import ownership has not been established.')
        self.kind = 'metadata'
        try:
            member = self.archive.native_member(original_import.module)
            envelope = self.archive.member_plan(member)
        except (ValueError, KeyError, UnicodeError) as error:
            raise Error('unsupported_game_format', 'Endfield original native archive structure is unsupported. Existing data is retained.') from error
        # The large compressed member is not a planning-metadata read. Both its
        # download size and complete decoded staging allowance are explicit.
        return {'schema': 1, 'stage': 'original-audio-native-member', 'client': self.client,
                'import': asdict(original_import), 'member': asdict(member), 'payload': envelope,
                'download_bytes': envelope['download_bytes'] + RECHECK_METADATA_UPPER,
                'download_is_upper_bound': True, 'verification_metadata_upper_bound': RECHECK_METADATA_UPPER,
                'required_disk_bytes': envelope['required_disk_bytes'] + RECEIPT_DISK_UPPER,
                'authentication': 'original split-artifact ranges and ZIP controls; complete publisher signature still required'}

    def acquire(self, plan, original_import, *, recheck):
        self._admit()
        read, write, write_bytes, Error, no_links = _helpers()
        if plan != self.plan(original_import):
            raise Error('publisher_size_changed', 'Endfield original native source or download size changed. Check its size again.')
        if self.ctx.phase != 'download':
            raise Error('unapproved_asset_transfer', 'Check the Endfield native source download size before continuing.')
        member = self.archive.native_member(original_import.module)
        previous = read(self.root / 'module.json')
        target = None
        if (isinstance(previous, dict) and previous.get('plan') == plan and
                previous.get('stage') == 'original-audio-native-member-verified' and
                type(previous.get('range_receipt_count')) is int and 0 < previous['range_receipt_count'] <= 2048 and
                isinstance(previous.get('range_receipts_sha256'), str) and
                re.fullmatch('[0-9a-f]{64}', previous['range_receipts_sha256'])):
            sha = previous.get('sha256')
            if isinstance(sha, str) and re.fullmatch('[0-9a-f]{64}', sha):
                path = self.root / ('module-' + sha + '.bin')
                no_links(path)
                try:
                    if path.stat().st_size == member.size:
                        raw = path.read_bytes()
                        if hashlib.sha256(raw).hexdigest() == sha and zlib.crc32(raw) == member.crc32:
                            target = path
                except FileNotFoundError:
                    pass
        reused = target is not None
        if not reused:
            self.kind = 'asset'
            try:
                raw = self.archive.extract(member)
            finally:
                self.kind = 'metadata'
            self.ctx.check()
            digest = hashlib.sha256(raw).hexdigest()
            target = self.root / ('module-' + digest + '.bin')
            write_bytes(target, raw)
        try:
            proof = signature.verify(target)
        except (ValueError, OSError) as error:
            raise Error('unverified_original_source',
                'Endfield original native data failed its publisher-signature check. Existing data is retained.') from error
        if (proof.get('sha256') != hashlib.sha256(raw).hexdigest() or proof.get('bytes') != member.size):
            raise Error('unverified_original_source', 'Endfield publisher-signature proof differs from its original native member.')
        self.ctx.check()
        if recheck() != self.identity:
            raise Error('publisher_object_changed', 'Endfield changed before native source publication. Existing data is retained.', 409)
        # This pointer is source-stage state only. Do not activate a master,
        # snapshot, dialogue library or a voice source from its presence.
        stage = {'schema': 1, 'stage': 'original-audio-native-member-verified', 'plan': plan,
                 'sha256': proof['sha256'], 'signature': proof,
                 'whole_part_md5_verified': False, 'gamefiles_member_md5_verified': False,
                 'range_receipt_count': len(self.receipts),
                 'range_receipts_sha256': hashlib.sha256(json.dumps(
                     [value for _, value in sorted(self.receipts.items())], sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()}
        if reused:
            # Offline revalidation must retain the earlier complete payload
            # acquisition proof, not replace it with metadata-only reads.
            stage['range_receipt_count'] = previous['range_receipt_count']
            stage['range_receipts_sha256'] = previous['range_receipts_sha256']
        self.ctx.check()
        write(self.root / 'module.json', stage)
        self.ctx.check()
        return target, stage
