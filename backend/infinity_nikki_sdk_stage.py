"""Ordinary quoted Global launcher source; original client code is never run.

This continuation verifies the complete selected PE before any original SDK
configuration is accepted. It is a preparation stage, never dialogue readiness.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile

from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .publisher_transport import STRONG_ETAG
from . import infinity_nikki_bootstrap as bootstrap
from . import infinity_nikki_release as release

POLICY = 'infinitynikki-global-launcher-source/1'
STAGES = {'global-launcher-bootstrap', 'global-sdk-source'}
MAX_ARTIFACT = 16 * 1024**2
MAX_METADATA = 8 * 1024**2
PUBLISHERS = frozenset({'Suzhou Nikki Co.,Ltd.'})
GATE = ('The official Global launcher source is verified. Current SDK/build manifests, '
        'configuration packages and the response/keychain reader still need preparation. '
        'No language library has been activated.')
SIGNATURE_GATE = ('The Global metadata source needs reviewed PE publisher-signature verification. '
                  'This host currently lacks that capability. Existing game data is retained.')
QUOTE = ('Download the official Global metadata source and verify its publisher signature. '
         'The temporary decode size is an upper bound. Current game text, voice and settings '
         'require further preparation; no optional voice pack is selected by this step.')


def _check(value):
    if not value:
        raise GameDataError('publisher_source_unverified', 'Could not verify the current official Global metadata source.')


def _foundation():
    from . import infinitynikki_game_data
    return infinitynikki_game_data


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _path(ctx, digest, suffix='json'):
    _check(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest) and suffix in {'json', 'pe'})
    path = Path(ctx.cache_directory).absolute() / 'infinitynikki-global-sdk' / (digest + '.' + suffix)
    _no_links(path)
    return path


def _read(ctx, digest):
    path = _path(ctx, digest)
    _check(path.is_file() and 0 < path.stat().st_size <= MAX_ARTIFACT)
    raw = path.read_bytes()
    _check(_sha(raw) == digest)
    return json.loads(raw, object_pairs_hook=release._unique_object)


def _store(ctx, value):
    raw = _json(value)
    _check(len(raw) <= MAX_ARTIFACT)
    digest = _sha(raw)
    ctx.check()
    _foundation()._save(_path(ctx, digest), raw)
    return digest


def _runtime(platform):
    if platform not in {'windows', 'desktop'}:
        return False
    from .publisher_pe_signature import source_runtime, SignatureCapabilityUnavailable
    try:
        source_runtime()
        return True
    except SignatureCapabilityUnavailable:
        return False


def _verify(path):
    from .publisher_pe_signature import verify
    return verify(path, publishers=PUBLISHERS, maximum_bytes=bootstrap.MAX_MEMBER)


def _parent(artifact, ctx):
    _check(ctx.request.region == 'global' and artifact.get('policy') == POLICY and
           artifact.get('request') == ctx.request.json())
    native = artifact.get('native_handle')
    _foundation()._handle(native, ctx.request)
    _check(native['stage'] == 'content-reader')
    return _foundation()._retained(native, ctx)


def _selection(artifact, ctx):
    _parent(artifact, ctx)
    _check(set(artifact) == {'policy', 'request', 'native_handle', 'url', 'total', 'etag',
                            'website_sha256', 'ranges'})
    release._launcher_url(artifact['url'], 'global')
    total, etag = artifact['total'], artifact['etag']
    _check(type(total) is int and 64*1024 <= total <= 1024**3 and isinstance(etag, str) and
           STRONG_ETAG.fullmatch(etag) and isinstance(artifact['website_sha256'], str) and
           re.fullmatch('[0-9a-f]{64}', artifact['website_sha256']) and isinstance(artifact['ranges'], list) and
           len(artifact['ranges']) == 4)
    values, count = {}, 0
    for item in artifact['ranges']:
        _check(isinstance(item, list) and len(item) == 2 and type(item[0]) is int and isinstance(item[1], str))
        raw = base64.b64decode(item[1], validate=True)
        count += len(raw)
        _check(0 < len(raw) and count <= MAX_METADATA and 0 <= item[0] <= total-len(raw) and
               (item[0], len(raw)) not in values)
        values[item[0], len(raw)] = raw
    def read(start, size):
        _check((start, size) in values)
        return values[start, size]
    overlay = bootstrap.nsis_overlay_offset(read(0, 64*1024), total)
    frame = read(overlay, 32)
    header_plan = bootstrap.nsis_header_plan(frame)
    header = bootstrap.decode_nsis_header(frame, read(overlay+32, header_plan.packed_bytes))
    offset = overlay + header_plan.data_offset + bootstrap.nsis_member_offsets(header)['xstarter.exe']
    following = struct.unpack_from('<I', frame, 24)[0]
    _check(overlay+following <= total and offset <= overlay+following-4)
    prefix = read(offset, 4)
    packed = (struct.unpack('<I', prefix)[0] & 0x7fffffff)+4
    _check(4 < packed <= bootstrap.MAX_PACKED+4 and offset+packed <= overlay+following)
    return offset, packed, prefix, _sha(header)


def _quote(artifact, handle, ctx, platform):
    _, packed, _, header_sha = _selection(artifact, ctx)
    available = _runtime(platform)
    return GameDataPlan('global-launcher-'+header_sha[:24]+'-'+_sha(artifact['etag'].encode())[:12], packed+4,
        packed+bootstrap.MAX_MEMBER+len(_json(artifact))+128*1024, handle,
        download_is_upper_bound=True, runtime_available=available,
        stage='global-launcher-bootstrap', message=QUOTE if available else SIGNATURE_GATE)


def _retained(handle, ctx):
    receipt = _read(ctx, handle['receipt_sha256'])
    _parent(receipt, ctx)
    _check(set(receipt) == {'policy', 'request', 'native_handle', 'artifact_sha256', 'module_sha256',
                            'module_bytes', 'signature', 'transfer', 'whole_installer_verified'})
    artifact = _read(ctx, receipt['artifact_sha256'])
    offset, size, _, _ = _selection(artifact, ctx)
    _check(artifact['native_handle'] == receipt['native_handle'] and
           type(receipt['module_bytes']) is int and 512 <= receipt['module_bytes'] <= bootstrap.MAX_MEMBER and
           receipt['whole_installer_verified'] is False)
    transfer = receipt['transfer']
    _check(isinstance(transfer, dict) and transfer.get('source_url_sha256') == _sha(artifact['url'].encode()) and
           transfer.get('bytes') == size and transfer.get('original_range') == [offset, size, artifact['total']] and
           transfer.get('response_etag') == artifact['etag'])
    path = _path(ctx, receipt['module_sha256'], 'pe')
    _check(path.is_file() and path.stat().st_size == receipt['module_bytes'])
    with path.open('rb') as stream:
        _check(hashlib.file_digest(stream, 'sha256').hexdigest() == receipt['module_sha256'])
    _check(receipt['signature'].get('sha256') == receipt['module_sha256'] and
           receipt['signature'].get('bytes') == receipt['module_bytes'] and
           receipt['signature'].get('publisher') in PUBLISHERS and
           receipt['signature'].get('verification') == 'Windows offline Authenticode' and
           receipt['signature'].get('online_revocation_freshness') is False)
    return receipt, artifact, path


def plan(provider, previous, ctx):
    ctx.check()
    if previous['stage'] == 'global-sdk-source':
        from . import infinity_nikki_build_stage
        return infinity_nikki_build_stage.plan(provider, previous, ctx)
    if previous['stage'] == 'global-launcher-bootstrap':
        prior = _read(ctx, previous['receipt_sha256'])
        _selection(prior, ctx)
        previous = prior['native_handle']
    _check(previous['stage'] == 'content-reader')
    _foundation()._retained(previous, ctx)
    if ctx.request.region != 'global':
        return GameDataPlan('mainland-sdk-reader', 0, 0, previous, stage='content-reader',
            message='Independent current mainland metadata selection still requires verification. Existing data is retained.')
    transport = provider.transport_factory(ctx, hosts={'infinitynikki.infoldgames.com', release.REGIONS['global'][1]})
    raw, _ = transport.fetch_bytes(release.REGIONS['global'][0], limit=release.MAX_PAGE, kind='metadata')
    url = release.parse_launcher_link(raw, 'global')
    prefix, identity = transport.fetch_bytes(url, limit=64*1024, expected_size=64*1024, kind='metadata',
                                            original_range=(0, 64*1024, None))
    _check(identity.original_range is not None and identity.response_etag is not None)
    total, etag = identity.original_range[2], identity.response_etag
    _check(type(total) is int and STRONG_ETAG.fullmatch(etag))
    ranges = [[0, base64.b64encode(prefix).decode('ascii')]]
    def read(start, size):
        value, _ = transport.fetch_bytes(url, limit=size, expected_size=size, kind='metadata',
            original_range=(start, size, total), headers={'If-Match': etag})
        ranges.append([start, base64.b64encode(value).decode('ascii')])
        return value
    overlay = bootstrap.nsis_overlay_offset(prefix, total)
    frame = read(overlay, 32)
    header_plan = bootstrap.nsis_header_plan(frame)
    header = bootstrap.decode_nsis_header(frame, read(overlay+32, header_plan.packed_bytes))
    offset = overlay + header_plan.data_offset + bootstrap.nsis_member_offsets(header)['xstarter.exe']
    read(offset, 4)
    artifact = {'policy': POLICY, 'request': ctx.request.json(), 'native_handle': previous,
                'url': url, 'total': total, 'etag': etag, 'website_sha256': _sha(raw), 'ranges': ranges}
    _selection(artifact, ctx)
    digest = _store(ctx, artifact)
    handle = {'policy': _foundation().POLICY, 'request': ctx.request.json(),
              'stage': 'global-launcher-bootstrap', 'receipt_sha256': digest}
    return _quote(artifact, handle, ctx, provider.platform)


def download(provider, consent, ctx):
    if consent.handle['stage'] == 'global-sdk-source':
        _retained(consent.handle, ctx)
        raise GameDataError('publisher_sdk_reader_unresolved', GATE, 409)
    _check(consent.stage == consent.handle['stage'] == 'global-launcher-bootstrap')
    artifact = _read(ctx, consent.handle['receipt_sha256'])
    _check(consent == _quote(artifact, consent.handle, ctx, provider.platform))
    if not _runtime(provider.platform):
        raise GameDataError('game_runtime_unavailable', SIGNATURE_GATE, 409)
    offset, size, prefix, _ = _selection(artifact, ctx)
    transport = provider.transport_factory(ctx, hosts={release.REGIONS['global'][1]})
    block, transfer = transport.fetch_bytes(artifact['url'], limit=size, expected_size=size, kind='asset',
        original_range=(offset, size, artifact['total']), headers={'If-Match': artifact['etag']})
    _check(block[:4] == prefix)
    member = bootstrap.decode_nsis_member(block)
    digest = _sha(member)
    root = _path(ctx, digest, 'pe').parent
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='pending-') as pending:
        path = Path(pending)/'publisher.pe'
        path.write_bytes(member)
        signature = _verify(path)
        _check(signature.get('sha256') == digest and signature.get('bytes') == len(member) and
               signature.get('publisher') in PUBLISHERS and
               signature.get('verification') == 'Windows offline Authenticode' and
               signature.get('online_revocation_freshness') is False)
        after, _ = transport.fetch_bytes(artifact['url'], limit=4, expected_size=4, kind='metadata',
            original_range=(offset, 4, artifact['total']), headers={'If-Match': artifact['etag']})
        _check(after == prefix)
        ctx.check()
        target = _path(ctx, digest, 'pe')
        if target.exists():
            with target.open('rb') as existing:
                _check(hashlib.file_digest(existing, 'sha256').hexdigest() == digest)
        else:
            _foundation().atomic_replace(path, target)
    receipt = {'policy': POLICY, 'request': ctx.request.json(), 'native_handle': artifact['native_handle'],
        'artifact_sha256': consent.handle['receipt_sha256'], 'module_sha256': digest, 'module_bytes': len(member),
        'signature': signature, 'transfer': transfer.json(), 'whole_installer_verified': False}
    digest = _store(ctx, receipt)
    ctx.check()
    return PreparationStage({'policy': _foundation().POLICY, 'request': ctx.request.json(),
                             'stage': 'global-sdk-source', 'receipt_sha256': digest}, GATE)


def restore(handle, ctx):
    if handle['stage'] == 'global-sdk-source':
        _retained(handle, ctx)
    else:
        _selection(_read(ctx, handle['receipt_sha256']), ctx)
    raise GameDataError('publisher_sdk_reader_unresolved', GATE, 409)
