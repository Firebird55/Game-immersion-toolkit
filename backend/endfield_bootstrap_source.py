"""Reopen only an explicitly bound original client-bootstrap continuation.

Large table bytes must already have been approved and downloaded. Subsequent
owner recognizers may request small metadata/code ranges through the explicit
context transport, never desktop urllib or a global transport replacement.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .endfield_client_source import MAX_CLIENT, MAX_METADATA, identity_stamp

METADATA = 'Endfield_Data/il2cpp_data/Metadata/global-metadata.dat'
ARTIFACTS = {METADATA: MAX_METADATA, 'GameAssembly.dll': MAX_CLIENT}
SMALL_RANGE = 65536
SMALL_TOTAL = 1024**2


def _helpers():
    from .game_data import _read, _write, _write_bytes
    from .game_data_protocol import GameDataError
    from .private_data_paths import _no_links
    return _read, _write, _write_bytes, GameDataError, _no_links


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class Bootstrap:
    def __init__(self, ctx, identity, transport, stage):
        read, _, _, Error, no_links = _helpers()
        self.ctx, self.identity, self.transport = ctx, identity, transport
        if (not isinstance(stage, dict) or type(stage.get('schema')) is not int or stage['schema'] != 1 or
                stage.get('stage') != 'client-bootstrap-downloaded' or stage.get('client') != identity or
                stage.get('request') != ctx.request.json() or ctx.game != 'endfield' or
                ctx.request.region != identity.get('region') or
                not isinstance(stage.get('receipt_sha256'), str) or
                not re.fullmatch('[0-9a-f]{64}', stage['receipt_sha256'])):
            raise Error('invalid_local_state', 'Endfield original client continuation is not bound to this request.')
        selection = hashlib.sha256(_json({'client': identity, 'request': ctx.request.json()})).hexdigest()
        self.root = Path(ctx.cache_directory) / 'endfield-client-bootstrap' / selection
        ctx.check()
        path = self.root / 'receipt.json'
        no_links(path)
        result = read(path)
        if (not isinstance(result, dict) or hashlib.sha256(_json(result)).hexdigest() != stage['receipt_sha256'] or
                type(result.get('schema')) is not int or result['schema'] != 1 or result.get('stage') != stage['stage'] or
                result.get('client') != identity or result.get('request') != ctx.request.json() or
                not isinstance(result.get('ranges'), list) or not 1 <= len(result['ranges']) <= 32):
            raise Error('invalid_local_state', 'Endfield original client bootstrap receipt needs repair.')
        self.rows, self.owners = {name: [] for name in ARTIFACTS}, {}
        self.readers = {}
        for n, item in enumerate(result['ranges']):
            if not isinstance(item, dict) or set(item) != {'range', 'receipt', 'file'} or item['file'] != f'{n}.bin':
                raise Error('invalid_local_state', 'Endfield original client table ownership is invalid.')
            row, receipt = item['range'], item['receipt']
            if (not isinstance(row, dict) or set(row) != {'artifact', 'offset', 'bytes'} or
                    row['artifact'] not in ARTIFACTS or type(row['offset']) is not int or type(row['bytes']) is not int or
                    row['offset'] < 0 or row['bytes'] <= 0 or not isinstance(receipt, dict)):
                raise Error('invalid_local_state', 'Endfield original client table range is invalid.')
            owner = receipt.get('original_range')
            artifact = row['artifact']
            if (not isinstance(owner, list) or len(owner) != 3 or not all(type(value) is int for value in owner) or
                    owner[:2] != [row['offset'], row['bytes']] or not row['offset'] + row['bytes'] <= owner[2] <= ARTIFACTS[artifact] or
                    type(receipt.get('bytes')) is not int or receipt['bytes'] != row['bytes'] or
                    receipt.get('source_url_sha256') != hashlib.sha256((identity['url'] + '/' + artifact).encode()).hexdigest() or
                    not isinstance(receipt.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', receipt['sha256']) or
                    self.owners.get(artifact, owner[2]) != owner[2]):
                raise Error('invalid_local_state', 'Endfield original client range receipt differs from its artifact.')
            self.owners[artifact] = owner[2]
            self.rows[artifact].append({**row, 'path': self.root / item['file'], 'sha256': receipt['sha256']})
        if set(self.owners) != set(ARTIFACTS):
            raise Error('invalid_local_state', 'Endfield original client bootstrap is incomplete.')
        for rows in self.rows.values():
            ordered = sorted(rows, key=lambda row: row['offset'])
            if any(left['offset'] + left['bytes'] > right['offset'] for left, right in zip(ordered, ordered[1:])):
                raise Error('invalid_local_state', 'Endfield original client table ranges overlap.')
        self.stage = stage

    def artifact(self, relative):
        if relative not in ARTIFACTS:
            raise ValueError('Only the two original client metadata artifacts are supported.')
        if relative not in self.readers:
            self.readers[relative] = Artifact(self, relative)
        return self.readers[relative]


class Artifact:
    def __init__(self, bootstrap, relative):
        self.bootstrap, self.relative = bootstrap, relative
        self.total = bootstrap.owners[relative]
        self.cached, self.acquired = {}, 0

    def read(self, offset, size):
        read, write, write_bytes, Error, no_links = _helpers()
        source, ctx = self.bootstrap, self.bootstrap.ctx
        ctx.check()
        if type(offset) is not int or type(size) is not int or not 0 <= offset < self.total or not 0 < size <= self.total - offset:
            raise Error('publisher_range_changed', 'Endfield original metadata read leaves its declared artifact.')
        covered = [row for row in source.rows[self.relative] if row['offset'] <= offset and
                   offset + size <= row['offset'] + row['bytes']]
        if covered:
            if len(covered) != 1:
                raise Error('invalid_local_state', 'Endfield original table byte ownership is ambiguous.')
            row = covered[0]
            no_links(row['path'])
            if row['path'] not in self.cached:
                try:
                    raw = row['path'].read_bytes()
                except OSError as error:
                    raise Error('invalid_local_state', 'Endfield original client table is unavailable; prepare its source again.') from error
                if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                    raise Error('invalid_local_state', 'Endfield original client table checksum differs.')
                self.cached[row['path']] = raw
            at = offset - row['offset']
            raw = self.cached[row['path']][at:at + size]
            ctx.check()
            return raw
        # Never hide a new large client-table transfer in the small-range path.
        if size > SMALL_RANGE:
            raise Error('source_not_prepared', 'Endfield needs another original client table preparation before this read.')
        root = source.root / 'owned-ranges' / Path(self.relative).name
        path = root / f'{offset}-{size}.bin'
        expected = {'client': identity_stamp(source.identity), 'artifact': self.relative,
                    'range': [offset, size, self.total]}
        no_links(path)
        receipt = read(path.with_suffix('.json'))
        if isinstance(receipt, dict) and all(receipt.get(k) == v for k, v in expected.items()):
            try:
                if path.stat().st_size == size:
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() == receipt.get('sha256'):
                        ctx.check()
                        return raw
            except FileNotFoundError:
                pass
        if self.acquired + size > SMALL_TOTAL:
            raise Error('source_not_prepared', 'Endfield original owner metadata exceeds this bounded preparation step.')
        raw, transfer = source.transport.fetch_bytes(source.identity['url'] + '/' + self.relative,
            limit=size, expected_size=size, kind='metadata', original_range=(offset, size, self.total))
        self.acquired += len(raw)
        if (transfer.original_range != (offset, size, self.total) or transfer.bytes != size or
                len(raw) != size or hashlib.sha256(raw).hexdigest() != transfer.sha256):
            raise Error('publisher_range_changed', 'Endfield original owner range receipt is inconsistent.')
        ctx.check()
        write_bytes(path, raw)
        write(path.with_suffix('.json'), {**expected, 'sha256': transfer.sha256,
            'transfer': transfer.json(), 'whole_artifact_hash_verified': False})
        ctx.check()
        return raw
