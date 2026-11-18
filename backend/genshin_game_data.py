"""Accounted original Genshin native-input stage, never a partial dialogue index.

The launcher manifest and complete selected source files come from the publisher.
Original dispatch, remaining bindings and Subtitle acquisition still gate the
next content stage. Missing host readers cannot trigger large source transfers.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import marshal
from pathlib import Path
import re

from . import sophon_assets as sophon
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .publisher_transport import PublisherTransport

SCHEMA = 'genshin-original-native-input-stage-v1'
PLATFORMS = {'android', 'windows', 'linux', 'macos'}
TEXT_LOCALES = {'en', 'zh-Hans', 'zh-Hant', 'ja', 'ko', 'de', 'fr', 'es-ES',
                'pt-BR', 'th', 'ru', 'vi', 'id', 'it', 'tr'}
VOICE_LOCALES = {'en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'}


class GenshinRuntime:
    """Installed Windows native analysis plus the owned portable BLB software."""
    def __init__(self, layout):
        self.layout = layout
        self.helper = self.validate()

    def validate(self):
        # Keep the existing native/host gate before any publisher payload quote.
        # BLB itself no longer resolves or executes a managed apphost/SDK.
        from .genshin_blb_portable import PortableHelper
        from .genshin_native_x64 import decoder
        if getattr(self.layout, 'mode', None) != 'bundle':
            raise ValueError('The installed Genshin native reader is unavailable.')
        decoder()
        return PortableHelper()

    def initial_seed(self, executable, metadata, *, expected_owner):
        from .genshin_native_channel import read_bootstrap_inputs
        return read_bootstrap_inputs(executable, metadata, expected_owner=expected_owner)

    def channel_profile(self, executable, source, source_receipt, contract, *, directory, check_cancel):
        from .genshin_original_bootstrap import prepare_profile
        return prepare_profile(executable, source, source_receipt, contract, self.validate(),
                               directory=directory, check_cancel=check_cancel)


class _UnplannedTransfer(Exception):
    pass


def _offline(*args, **kwargs):
    raise _UnplannedTransfer()


def _safe(path):
    path = Path(path).absolute()
    _no_links(path)
    return path


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _revision(build):
    return 'genshin-native-' + hashlib.sha256(_canonical(build)).hexdigest()


def _selection(request):
    if (request.source_locale not in TEXT_LOCALES or set(request.target_locales) - TEXT_LOCALES
            or request.content_mode == 'text-audio' and request.source_locale not in VOICE_LOCALES):
        raise GameDataError('genshin_languages', 'Choose official Genshin text languages and, when requested, an official dub.')
    return request.json()


def _names(region):
    stem = 'GenshinImpact' if region == 'global' else 'YuanShen'
    return (stem + '.exe', stem + '_Data/Native/Data/Metadata/global-metadata.dat')


def _valid(path, digest, size):
    path = _safe(path)
    try:
        if not path.is_file() or path.stat().st_size != size:
            return False
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'md5').hexdigest() == digest
    except OSError:
        return False


def _source(cache, asset):
    return _safe(cache / 'sources' / asset.digest)


def _files(cache, build, region, fetch):
    spec = tuple(build['manifests']['game'])
    _safe(cache / 'manifests' / spec[4])
    wanted = _names(region)
    files = sophon.manifest(cache, build['channel'], spec, wanted, fetch=fetch)
    if set(files) != set(wanted):
        raise GameDataError('genshin_original_source_missing', 'The complete original Genshin native inputs are unavailable.')
    for asset in files.values():
        maximum = 768 * 1024**2 if asset.name.endswith('.exe') else 256 * 1024**2
        if not 512 <= asset.size <= maximum:
            raise GameDataError('genshin_original_source_bounds', 'The original Genshin native inputs exceed their supported bounds.')
        for _, _, _, _, digest in asset.chunks:
            _safe(cache / 'chunks' / digest)
    return files


def _quote(cache, files):
    chunks, originals, pending = {}, [], 0
    for name, asset in sorted(files.items()):
        cached = _valid(_source(cache, asset), asset.digest, asset.size)
        originals.append({'name': name, 'md5': asset.digest, 'bytes': asset.size, 'cached': cached})
        if cached:
            continue
        pending += asset.size
        for _, size, compressed, identity, digest in asset.chunks:
            row = {'md5': digest, 'bytes': size, 'compressed_bytes': compressed,
                   'urls': [asset.prefix + '/' + identity],
                   'cached': _valid(cache / 'chunks' / digest, digest, size)}
            previous = chunks.get(digest)
            if previous:
                if (previous['bytes'], previous['compressed_bytes']) != (size, compressed):
                    raise GameDataError('genshin_source_identity_changed', 'The original Genshin source sizes disagree.')
                row['urls'] = sorted(set(previous['urls'] + row['urls']))
            chunks[digest] = row
    rows = [row for _, row in sorted(chunks.items())]
    missing = [row for row in rows if not row['cached']]
    transfer = sum(row['compressed_bytes'] for row in missing)
    # Includes complete materialized files, verified expanded cache, one chunk's
    # atomic staging, and a bounded receipt; it is not a complete game quote.
    disk = pending + sum(row['bytes'] for row in missing) + max((row['bytes'] for row in missing), default=0) + 1024**2
    return {'files': originals, 'chunks': rows}, transfer, disk


def _record(ctx, handle):
    target = _safe(ctx.directory / 'original-native-inputs.json')
    pending = _safe(ctx.directory / 'original-native-inputs.pending')
    ctx.check()
    pending.write_bytes(_canonical(handle))
    ctx.check()
    pending.replace(target)
    message = ('Official Genshin manifest verified. Check the native source download size next.'
        if handle['phase'] == 'official-manifest' else
        'Original Genshin connection profile verified. Complete preparation still needs supported connection, dialogue and audio stages.'
        if handle['phase'] == 'original-channel-profile' else
        'Original initial dispatch value verified. RSA, request template, signature ownership and later overrides remain unresolved.'
        if handle['phase'] == 'original-bootstrap-seed' else
        'Original Genshin native inputs verified. Dialogue and audio still need the next supported source stage.')
    return PreparationStage(handle, message)


def _implementation(names):
    implementation = hashlib.sha256()
    for name in names:
        spec = importlib.util.find_spec('backend.' + name)
        code = spec.loader.get_code(spec.name) if spec is not None and hasattr(spec.loader, 'get_code') else None
        if code is None:
            raise GameDataError('genshin_bootstrap_reader_unavailable', 'Repair the original Genshin bootstrap reader.')
        implementation.update(name.encode())
        implementation.update(marshal.dumps(code))
    return implementation.hexdigest()


def _seed_owner(cache, files, runtime_identity):
    sources = []
    for name, asset in sorted(files.items()):
        path = _source(cache, asset)
        if not _valid(path, asset.digest, asset.size):
            raise GameDataError('game_data_plan_changed', 'The original Genshin input changed. Check its source size again.', 409)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        sources.append({'name': name, 'md5': asset.digest, 'bytes': asset.size, 'sha256': digest})
    # Reader implementation changes require extraction again from original bytes.
    # Frozen Python loaders expose code objects; an installed app need not ship
    # editable .py files. Include the complete maintained parser closure.
    implementation = _implementation(('genshin_native_dispatch', 'genshin_native_channel', 'genshin_original_excel', 'genshin_native_x64',
                 'genshin_native_metadata', 'genshin_native_expression', 'genshin_native_registration',
                 'genshin_native_view', 'genshin_native_usage', 'genshin_native_literals'))
    return {'sources': sources, 'runtime_identity': runtime_identity, 'implementation_sha256': implementation}


def _seed_path(cache, owner):
    return _safe(cache / 'bootstrap-seeds' / (hashlib.sha256(_canonical(owner)).hexdigest() + '.json'))


def _seed_receipt(path, owner):
    try:
        if not path.is_file() or path.stat().st_size > 1024**2:
            return None
        receipt = json.loads(path.read_bytes())
        value, proof = receipt['value'], receipt['proof']
        contract = proof['channel_loader']
        contract_methods = contract['methods']
        expected = {'metadata_sha256' if row['name'].endswith('.dat') else 'executable_sha256': row['sha256']
                    for row in owner['sources']}
        if (receipt['owner'] != owner or proof['schema'] != 'genshin-original-initial-dispatch-seed-v1'
                or not isinstance(value, str) or not 16 <= len(value) <= 128
                or any(character not in '0123456789abcdef' for character in value)
                or proof['value_sha256'] != hashlib.sha256(value.encode()).hexdigest()
                or proof['later_override_excluded'] is not False or proof['complete_dispatch_bootstrap'] is not False
                or contract['schema'] != 'genshin-original-channel-loader-v1' or contract['profile_only'] is not True
                or contract['complete_dispatch_bootstrap'] is not False or contract['later_override_excluded'] is not False
                or not isinstance(contract_methods, list) or len(contract_methods) != 2
                or {row['name'] for row in contract_methods} != {'GetConfigChannel', 'LoadChannelConfigBlk'}
                or not all(isinstance(row['sha256'], str) and re.fullmatch('[a-f0-9]{64}', row['sha256'])
                           and type(row['rva']) is int and row['rva'] > 0 for row in contract_methods)
                or contract['source_field']['field']['name'] != 'channelConfigBlkName'
                or any(contract['source_field'][key] != digest for key, digest in expected.items())
                or any(proof[key] != digest for key, digest in expected.items())):
            return None
        return receipt
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _accepted_seed(previous, handle, owner, receipt):
    if not isinstance(previous, dict) or receipt is None:
        return False
    if any(previous.get(key) != handle[key] for key in ('schema', 'game', 'request', 'revision', 'runtime_identity')):
        return False
    phase = previous.get('phase')
    if phase not in {'original-bootstrap-seed', 'original-channel-profile'} or previous.get('seed_owner') != owner:
        return False
    expected = previous.get('receipt_sha256' if phase == 'original-bootstrap-seed' else 'seed_receipt_sha256')
    return expected == hashlib.sha256(_canonical(receipt)).hexdigest()


def _profile_files(cache, build, basename, fetch):
    from .genshin_original_bootstrap import MAX_PACKAGE
    if not isinstance(basename, str) or not re.fullmatch('[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}', basename):
        raise GameDataError('genshin_profile_source_unavailable', 'The original connection profile source is unavailable.')
    files = sophon.manifest(cache, build['channel'], tuple(build['manifests']['game']), (basename,), fetch=fetch)
    if len(files) != 1 or any(asset.name.rsplit('/', 1)[-1] != basename or not 0 < asset.size <= MAX_PACKAGE for asset in files.values()):
        raise GameDataError('genshin_profile_source_unavailable', 'The complete original connection profile is unavailable or ambiguous.')
    for asset in files.values():
        for _, _, _, _, digest in asset.chunks:
            _safe(cache / 'chunks' / digest)
    return files


def _profile_owner(handle, seed_owner, seed_receipt, files):
    from .genshin_original_bootstrap import MAX_BODY, MAX_PACKAGE, MAX_RECEIPT, MAX_TEXT
    asset, = files.values()
    contract = seed_receipt['proof']['channel_loader']
    return {'game': 'genshin', 'request': handle['request'], 'revision': handle['revision'],
            'seed_owner': seed_owner, 'seed_receipt_sha256': hashlib.sha256(_canonical(seed_receipt)).hexdigest(),
            'loader_contract_sha256': hashlib.sha256(_canonical(contract)).hexdigest(),
            'source': {'name': asset.name, 'md5': asset.digest, 'bytes': asset.size},
            'runtime_identity': handle['runtime_identity'],
            'implementation_sha256': _implementation(('genshin_original_bootstrap', 'genshin_original_containers',
                'genshin_blb_native', 'genshin_blb', 'genshin_blb_portable', 'genshin_native_x64', 'hoyo_bootstrap_assets')),
            'bounds': {'package': MAX_PACKAGE, 'body': MAX_BODY, 'text': MAX_TEXT, 'receipt': MAX_RECEIPT}}


def _profile_path(cache, owner):
    return _safe(cache / 'channel-profiles' / (hashlib.sha256(_canonical(owner)).hexdigest() + '.json'))


def _profile_quote(cache, files):
    from .genshin_original_bootstrap import MAX_BODY, MAX_RECEIPT
    ledger, transfer, disk = _quote(cache, files)
    asset, = files.values()
    # One sequential candidate's decoded file/body, all bounded parameter data,
    # and an atomic private receipt; this is expressly a profile-only quote.
    return ledger, transfer, disk + asset.size + MAX_BODY + 128 * 32 * 1024 + MAX_RECEIPT


def _profile_receipt(path, owner, contract, source):
    from .genshin_original_bootstrap import MAX_BODY, MAX_RECEIPT, SCHEMA as PROFILE_SCHEMA, parse_profile
    try:
        if not path.is_file() or path.stat().st_size > MAX_RECEIPT:
            return None
        receipt = json.loads(path.read_bytes())
        proof = receipt['proof']
        payload = receipt['payload'].encode('utf-8')
        parameters = receipt['parameters'].encode('ascii')
        methods = proof['codec_method_sha256s']
        if (receipt['owner'] != owner or proof['schema'] != PROFILE_SCHEMA or proof['profile_only'] is not True
                or proof['complete_dispatch_bootstrap'] is not False or proof['full_catalog_validated'] is not False
                or proof['selected_shards_validated'] is not False or proof['later_override_excluded'] is not False
                or proof['response_signature_verified'] is not False or proof['community_numeric_data_used'] is not False
                or proof['source'] != source or proof['helper_identity'] != owner['runtime_identity']
                or proof['native_executable_sha256'] != contract['source_field']['executable_sha256']
                or proof['loader_contract_sha256'] != owner['loader_contract_sha256']
                or proof['codec_parameters_sha256'] != hashlib.sha256(parameters).hexdigest()
                or not isinstance(methods, list) or not 1 <= len(methods) <= 128 or methods != sorted(set(methods))
                or not all(isinstance(item, str) and re.fullmatch('[a-f0-9]{64}', item) for item in methods)
                or type(proof['original_codec_candidates_tested']) is not int or not 1 <= proof['original_codec_candidates_tested'] <= 128
                or type(proof['body_bytes']) is not int or not 0 < proof['body_bytes'] <= MAX_BODY
                or not isinstance(proof['body_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', proof['body_sha256'])
                or proof['complete_named_object_map'] is not True
                or proof['strict_payload_eof'] is not True or proof['payload_bytes'] != len(payload)
                or proof['payload_sha256'] != hashlib.sha256(payload).hexdigest()
                or proof['object_id'] not in {row['id'] for row in contract['object_candidates']}):
            return None
        parse_profile(payload, contract)
        return receipt
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return None


def _source_rows(cache, files):
    result = []
    for asset in files.values():
        path = _source(cache, asset)
        if not _valid(path, asset.digest, asset.size):
            raise GameDataError('game_data_plan_changed', 'The original Genshin source changed. Check its size again.', 409)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        result.append({'name': asset.name, 'md5': asset.digest, 'bytes': asset.size, 'sha256': digest})
    return result


def _materialize_files(ctx, cache, files, fetch):
    for asset in files.values():
        ctx.check()
        destination = _source(cache, asset)
        if _valid(destination, asset.digest, asset.size):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        pending = _safe(destination.with_suffix('.pending'))
        try:
            with pending.open('wb') as stream:
                for offset in range(0, asset.size, 8 * 1024**2):
                    ctx.check()
                    stream.write(asset.read(cache, offset, min(8 * 1024**2, asset.size - offset), fetch=fetch))
            if not _valid(pending, asset.digest, asset.size):
                raise GameDataError('genshin_original_source_invalid', 'An original Genshin input failed its whole-file checksum.')
            ctx.check()
            pending.replace(destination)
        except ValueError as error:
            raise GameDataError('genshin_original_source_invalid', 'An original Genshin input failed its whole-file checksum.') from error
        finally:
            pending.unlink(missing_ok=True)
    return _source_rows(cache, files)


class GenshinGameDataProvider:
    title = 'Genshin Impact'

    def __init__(self, *, platform, native=None, transport_factory=PublisherTransport):
        if platform not in PLATFORMS:
            raise GameDataError('unsupported_game_data_platform', 'This game data platform is unsupported.')
        self.platform, self.runtime, self.transport_factory = platform, native, transport_factory

    def _reader(self):
        if self.platform != 'windows':
            return None
        try:
            if self.runtime is None:
                from .runtime_bundle import discover_layout
                layout = discover_layout()
                # A source checkout has no accepted installed closure. Do not
                # call the development helper builder or look for a PATH SDK.
                if getattr(layout, 'mode', None) != 'bundle':
                    return None
                self.runtime = GenshinRuntime(layout)
                return self.runtime.helper
            if not isinstance(self.runtime, GenshinRuntime):
                return None
            return self.runtime.validate()
        except (ImportError, OSError, ValueError, RuntimeError):
            return None

    def _fetch(self, ctx, *, kind, allowed=None):
        (launcher, _, downloader), _, _, publisher = sophon.CHANNELS['genshin-' + ctx.request.region]
        transport = self.transport_factory(ctx, hosts={launcher, downloader, publisher})
        def fetch(url, *, limit):
            ctx.check()
            if allowed is not None and url not in allowed:
                raise GameDataError('game_data_plan_changed', 'Check the Genshin source download size again.', 409)
            raw, _ = transport.fetch_bytes(url, limit=limit, kind=kind)
            return raw
        return fetch

    def _download_profile(self, plan, ctx, cache, native_files, reader):
        handle, build = plan.handle, plan.handle['build']
        seed_owner = _seed_owner(cache, native_files, reader.identity)
        seed = _seed_receipt(_seed_path(cache, seed_owner), seed_owner)
        if (seed is None or handle.get('seed_owner') != seed_owner
                or handle.get('seed_receipt_sha256') != hashlib.sha256(_canonical(seed)).hexdigest()):
            raise GameDataError('game_data_plan_changed', 'The original connection inputs changed. Check their size again.', 409)
        contract = seed['proof']['channel_loader']
        try:
            files = _profile_files(cache, build, contract['source_basename'], _offline)
        except _UnplannedTransfer as error:
            raise GameDataError('game_data_plan_changed', 'The original profile manifest changed. Check its size again.', 409) from error
        ledger, transfer, disk = _profile_quote(cache, files)
        owner = _profile_owner(handle, seed_owner, seed, files)
        if handle.get('profile_ledger') != ledger or handle.get('profile_owner') != owner or (plan.download_bytes, plan.required_disk_bytes) != (transfer, disk):
            raise GameDataError('game_data_plan_changed', 'The original profile source changed. Check its size again.', 409)
        fetch = self._fetch(ctx, kind='asset', allowed={url for row in ledger['chunks'] if not row['cached'] for url in row['urls']})
        source, = _materialize_files(ctx, cache, files, fetch)
        executable = next(asset for asset in native_files.values() if asset.name.endswith('.exe'))
        raw = _source(cache, executable).read_bytes()
        if hashlib.sha256(raw).hexdigest() != contract['source_field']['executable_sha256']:
            raise GameDataError('game_data_plan_changed', 'The original Genshin native input changed.', 409)
        ctx.check()
        try:
            result = self.runtime.channel_profile(raw, _source(cache, next(iter(files.values()))), source, contract,
                directory=ctx.directory, check_cancel=ctx.check)
        except (ValueError, RuntimeError) as error:
            raise GameDataError('genshin_profile_reader_unavailable', 'The original connection profile cannot be verified for this build.') from error
        receipt = {'owner': owner, 'payload': result.payload.decode('utf-8'),
                   'parameters': result.parameters.decode('ascii'), 'proof': result.proof}
        destination = _profile_path(cache, owner)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pending = _safe(destination.with_suffix('.pending'))
        try:
            ctx.check()
            pending.write_bytes(_canonical(receipt))
            if _profile_receipt(pending, owner, contract, source) is None:
                raise GameDataError('genshin_profile_reader_unavailable', 'The original connection profile receipt failed verification.')
            ctx.check()
            pending.replace(destination)
            result_handle = {key: value for key, value in handle.items() if key not in {'profile_ledger', 'ledger'}}
            return _record(ctx, {**result_handle, 'phase': 'original-channel-profile',
                'profile_receipt_sha256': hashlib.sha256(_canonical(receipt)).hexdigest()})
        finally:
            pending.unlink(missing_ok=True)

    def plan(self, request, ctx):
        selection = _selection(request)
        if ctx.game != 'genshin' or ctx.request != request:
            raise GameDataError('game_data_plan_changed', 'Check the selected Genshin languages again.', 409)
        ctx.check()
        reader = self._reader()
        if reader is None:
            return GameDataPlan('genshin-reader-unavailable', None, None, stage='original-runtime',
                message=("Install or repair the toolkit's verified Genshin reader before downloading game data."
                    if self.platform == 'windows' else
                    'Original Genshin preparation is not available on this device yet.'))
        with ctx.transfer_lock:
            cache = _safe(ctx.cache_directory / 'genshin-original' / request.region)
            build = sophon.release('genshin-' + request.region, fetch=self._fetch(ctx, kind='metadata'))
            revision = _revision(build)
            handle = {'schema': SCHEMA, 'game': 'genshin', 'request': selection, 'build': build,
                      'revision': revision, 'runtime_identity': reader.identity}
            spec = tuple(build['manifests']['game'])
            if not (0 < spec[2] <= sophon.MAX_MANIFEST and 0 < spec[3] <= sophon.MAX_MANIFEST):
                raise GameDataError('genshin_manifest_bounds', 'The official Genshin manifest exceeds its supported bounds.')
            if not _valid(cache / 'manifests' / spec[4], spec[4], spec[3]) and spec[2] > ctx.remaining_bytes(kind='metadata'):
                return GameDataPlan(revision, spec[2], spec[3] * 2 + 1024**2, handle=handle,
                    runtime_available=True, download_is_upper_bound=True, stage='official-manifest',
                    message='Download the official Genshin manifest first, then check the native source size.')
            files = _files(cache, build, request.region, self._fetch(ctx, kind='metadata'))
            ledger, transfer, disk = _quote(cache, files)
            if all(row['cached'] for row in ledger['files']):
                owner = _seed_owner(cache, files, reader.identity)
                receipt = _seed_receipt(_seed_path(cache, owner), owner)
                if not _accepted_seed(ctx.stage_handle, handle, owner, receipt):
                    handle.update(ledger=ledger, seed_owner=owner)
                    return GameDataPlan(revision, 0, 1024**2, handle=handle, runtime_available=True,
                        stage='original-bootstrap-seed',
                        message='Read the original initial dispatch value from verified publisher files. This local stage does not prepare dialogue or audio.')
                contract = receipt['proof']['channel_loader']
                profile_files = _profile_files(cache, build, contract['source_basename'], self._fetch(ctx, kind='metadata'))
                profile_ledger, profile_transfer, profile_disk = _profile_quote(cache, profile_files)
                profile_owner = _profile_owner(handle, owner, receipt, profile_files)
                if all(row['cached'] for row in profile_ledger['files']):
                    source_row, = _source_rows(cache, profile_files)
                    profile_receipt = _profile_receipt(_profile_path(cache, profile_owner), profile_owner, contract, source_row)
                    if (profile_receipt is not None and ctx.stage_handle.get('phase') == 'original-channel-profile'
                            and ctx.stage_handle.get('profile_owner') == profile_owner
                            and ctx.stage_handle.get('profile_receipt_sha256') == hashlib.sha256(_canonical(profile_receipt)).hexdigest()):
                        return GameDataPlan(revision, None, None, handle=handle, stage='original-content-reader',
                            message='The original connection profile is verified. RSA, signature ownership, overrides, remaining dialogue bindings and film subtitles still need supported source stages.')
                handle.update(seed_owner=owner, seed_receipt_sha256=hashlib.sha256(_canonical(receipt)).hexdigest(),
                              profile_owner=profile_owner, profile_ledger=profile_ledger)
                return GameDataPlan(revision, profile_transfer, profile_disk, handle=handle, runtime_available=True,
                    download_is_upper_bound=True, stage='original-channel-profile',
                    message='Prepare the complete original Genshin connection profile. This stage does not prepare dialogue or audio.')
            handle['ledger'] = ledger
            return GameDataPlan(revision, transfer, disk, handle=handle, download_is_upper_bound=True,
                runtime_available=True, stage='official-native-inputs',
                message='Download the complete official Genshin native reader inputs. This stage does not prepare dialogue or audio.')

    def download(self, plan, ctx):
        selection = _selection(ctx.request)
        handle, build = plan.handle, plan.handle.get('build', {})
        reader = self._reader()
        if (ctx.game != 'genshin' or handle.get('schema') != SCHEMA or handle.get('game') != 'genshin'
                or handle.get('request') != selection or build.get('channel') != 'genshin-' + ctx.request.region
                or plan.revision != handle.get('revision') or plan.revision != _revision(build)
                or plan.stage not in {'official-manifest', 'official-native-inputs', 'original-bootstrap-seed', 'original-channel-profile'} or not plan.runtime_available
                or reader is None or handle.get('runtime_identity') != reader.identity):
            raise GameDataError('game_data_plan_changed', 'Check the Genshin source download again.', 409)
        with ctx.transfer_lock:
            cache = _safe(ctx.cache_directory / 'genshin-original' / ctx.request.region)
            ctx.check()
            if plan.stage == 'official-manifest':
                spec = tuple(build['manifests']['game'])
                if (plan.download_bytes, plan.required_disk_bytes) != (spec[2], spec[3] * 2 + 1024**2):
                    raise GameDataError('game_data_plan_changed', 'Check the Genshin manifest size again.', 409)
                _files(cache, build, ctx.request.region,
                       self._fetch(ctx, kind='asset', allowed={spec[0] + '/' + spec[1]}))
                return _record(ctx, {**handle, 'phase': 'official-manifest'})
            try:
                files = _files(cache, build, ctx.request.region, _offline)
            except _UnplannedTransfer as error:
                raise GameDataError('game_data_plan_changed', 'The cached Genshin manifest changed. Check its size again.', 409) from error
            ledger, transfer, disk = _quote(cache, files)
            if plan.stage == 'original-channel-profile':
                return self._download_profile(plan, ctx, cache, files, reader)
            if plan.stage == 'original-bootstrap-seed':
                owner = _seed_owner(cache, files, reader.identity)
                if (not all(row['cached'] for row in ledger['files']) or handle.get('ledger') != ledger
                        or handle.get('seed_owner') != owner or (plan.download_bytes, plan.required_disk_bytes) != (0, 1024**2)):
                    raise GameDataError('game_data_plan_changed', 'Check the original Genshin bootstrap inputs again.', 409)
                values = {}
                for name, asset in files.items():
                    ctx.check()
                    raw = _source(cache, asset).read_bytes()
                    row = next(row for row in owner['sources'] if row['name'] == name)
                    if len(raw) != row['bytes'] or hashlib.md5(raw).hexdigest() != row['md5'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                        raise GameDataError('game_data_plan_changed', 'An original Genshin bootstrap input changed.', 409)
                    values['metadata' if name.endswith('.dat') else 'executable'] = raw
                expected = {key + '_sha256': hashlib.sha256(value).hexdigest() for key, value in values.items()}
                try:
                    result = self.runtime.initial_seed(**values, expected_owner=expected)
                except (ValueError, RuntimeError) as error:
                    raise GameDataError('genshin_bootstrap_owner_unavailable',
                        'The original initial dispatch value cannot be verified for this build.') from error
                receipt = {'owner': owner, 'value': result.value, 'proof': result.proof}
                destination = _seed_path(cache, owner)
                destination.parent.mkdir(parents=True, exist_ok=True)
                pending = _safe(destination.with_suffix('.pending'))
                try:
                    ctx.check()
                    pending.write_bytes(_canonical(receipt))
                    if _seed_receipt(pending, owner) is None:
                        raise GameDataError('genshin_bootstrap_owner_unavailable', 'The original dispatch receipt failed verification.')
                    ctx.check()
                    pending.replace(destination)
                    return _record(ctx, {**{k: v for k, v in handle.items() if k not in {'ledger', 'seed_owner'}},
                        'phase': 'original-bootstrap-seed', 'seed_owner': owner,
                        'receipt_sha256': hashlib.sha256(_canonical(receipt)).hexdigest()})
                finally:
                    pending.unlink(missing_ok=True)
            if handle.get('ledger') != ledger or (plan.download_bytes, plan.required_disk_bytes) != (transfer, disk):
                raise GameDataError('game_data_plan_changed', 'The cached Genshin sources changed. Check their size again.', 409)
            fetch = self._fetch(ctx, kind='asset', allowed={url for row in ledger['chunks'] if not row['cached'] for url in row['urls']})
            receipts = [{'name': row['name'], 'publisher_md5': row['md5'], 'bytes': row['bytes'], 'sha256': row['sha256']}
                        for row in _materialize_files(ctx, cache, files, fetch)]
            return _record(ctx, {**{k: v for k, v in handle.items() if k != 'ledger'},
                                 'phase': 'official-native-inputs', 'sources': receipts})

    def restore(self, handle, ctx):
        ctx.check()
        raise GameDataError('genshin_native_inputs_only', 'Original Genshin source files are not a prepared dialogue library.', 409)


def create_provider(*, platform, native=None):
    return GenshinGameDataProvider(platform=platform, native=native)
