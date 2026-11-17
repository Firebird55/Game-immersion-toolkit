"""Renew ZZZ request identity from authenticated official launcher TextAssets."""
import base64
import hashlib
import re
from urllib.parse import urlsplit

from . import hoyo_dispatch_metadata as bootstrap
from .hoyo_bootstrap_assets import text_assets
from . import sophon_assets as sophon
from . import zzz_native_key_data as native_keys


RESOURCE = 'ZenlessZoneZero_Data/resources.assets'
DOCUMENTS = frozenset({'app_version', 'login_setting'})
NATIVE_RESOURCE = 'GameAssembly.dll'


def native_source_plan(build, directory, *, fetch=None):
    """Plan official key-data transport from manifest/PE metadata only.

    The section payload belongs to the authorized download stage. In particular
    it must not be hidden inside an Android metadata-only preflight budget.
    Returned byte totals are complete-container upper bounds before verified
    cache subtraction, not sums of logical key/initializer bytes.
    """
    bootstrap.check(isinstance(build, dict) and build.get('channel') in ('zzz-global', 'zzz-cn'))
    spec = tuple(build['manifests']['game'])
    options = {} if fetch is None else {'fetch': fetch}
    files = sophon.manifest(directory, build['channel'], spec, (NATIVE_RESOURCE,), **options)
    bootstrap.check(NATIVE_RESOURCE in files)
    asset = files[NATIVE_RESOURCE]
    plan = native_keys.source_plan(asset.size, lambda start, length: asset.read(directory, start, length, **options))
    start, end = plan['offset'], plan['offset'] + plan['bytes']
    chunks = {}
    for chunk in asset.chunks:
        if chunk[0] >= end or chunk[0] + chunk[1] <= start:
            continue
        previous = chunks.get(chunk[4])
        bootstrap.check(previous is None or previous[1] == chunk[1])
        if previous is None or chunk[2] > previous[2]:
            chunks[chunk[4]] = chunk
    proof = {'channel': build['channel'], 'version': build['version'], 'build': build['build'],
             'manifest_md5': spec[4], 'file': NATIVE_RESOURCE, 'file_md5': asset.digest,
             'file_bytes': asset.size, 'section': plan,
             'download_bytes_upper_bound': sum(chunk[2] for chunk in chunks.values()),
             'cache_bytes_upper_bound': sum(chunk[1] for chunk in chunks.values()),
             'chunks': [{'id': chunk[3], 'md5': chunk[4], 'expanded_bytes': chunk[1],
                         'compressed_bytes': chunk[2]} for chunk in chunks.values()]}
    return asset, plan, proof


def gateway_keys(build, directory, *, fetch=None):
    """Authorized download-stage operation; source bytes are data, never code."""
    options = {} if fetch is None else {'fetch': fetch}
    asset, plan, source = native_source_plan(build, directory, **options)
    return tuple(native_keys.KeyCandidate(item.key, {'source': source, 'initializer': item.proof})
                 for item in native_keys.read_candidates(plan, lambda start, length: asset.read(directory, start, length, **options)))


def official(build, region, directory, *, fetch=None):
    """Current official inputs only; no initial/community key cache is needed.

    This includes native data acquisition and belongs to an authorized source
    download/preparation stage. Use native_source_plan for metadata-only plans.
    """
    options = {} if fetch is None else {'fetch': fetch}
    config = renew({bootstrap._PROVENANCE: {'game': 'zzz', 'region': region}}, build, region, directory, **options)
    keys = gateway_keys(build, directory, **options)
    proof = bootstrap.provenance(config)
    proof['policy'] = 'official-current-client-data'
    proof['frozen_parameters'] = []
    proof['gateway_key_sources'] = [item.proof for item in keys]
    proof['query_parameter_policy'] = 'official-server-negotiation'
    config[bootstrap._PROVENANCE] = proof
    # Ephemeral key objects never enter a source descriptor, prepared table or
    # protected-store dependency. Only hashes/ranges above may be persisted.
    config['_official_gateway_keys'] = keys
    return config


def renew(config, build, region, directory, *, fetch=None):
    """Keep frozen crypto separate from current official seed/endpoint inputs.

    Original Unity metadata bounds identify the named objects on every release;
    neither old object offsets nor revision-specific IDs are stored in code.
    An invalid new source never overwrites a previous immutable source object.
    """
    prefix, domain, dispatch = {'global': ('OSPRODWin', 'zenlesszonezero.com', 'os'),
                               'cn': ('CNPRODWin', 'juequling.com', 'cn')}[region]
    proof = bootstrap.provenance(config)
    bootstrap.check(proof.get('game') == 'zzz' and proof.get('region') == region)
    bootstrap.check(isinstance(build, dict) and build.get('channel') == 'zzz-' + region
                    and re.fullmatch(r'[1-9][0-9]*\.[0-9]+\.[0-9]+', str(build.get('version', ''))))
    spec = tuple(build['manifests']['game'])
    options = {} if fetch is None else {'fetch': fetch}
    files = sophon.manifest(directory, build['channel'], spec, ('resources.assets',), **options)
    bootstrap.check(RESOURCE in files)
    asset = files[RESOURCE]
    documents = text_assets(asset.size, lambda start, length: asset.read(directory, start, length, **options), DOCUMENTS)
    app, login = (bootstrap._json(documents[name]['payload']) for name in ('app_version', 'login_setting'))
    bootstrap.check(isinstance(app, dict) and isinstance(login, dict)
                    and login.get('$Type') == 'Foundation.LoginSetting'
                    and app.get('ApplicationVersion') == build['version']
                    and app.get('ChannelName') == prefix
                    and app.get('DispatchVersion') == prefix + build['version']
                    and re.fullmatch('[0-9a-fA-F]{16,128}', str(app.get('DispatchSeed', ''))))
    endpoints = login.get('dispatch_urls')
    bootstrap.check(isinstance(endpoints, list) and 0 < len(endpoints) <= 8
                    and all(isinstance(endpoint, str) for endpoint in endpoints)
                    and len(set(endpoints)) == len(endpoints))
    for endpoint in endpoints:
        bootstrap.check(isinstance(endpoint, str) and len(endpoint) <= 1024)
        parsed = urlsplit(endpoint)
        bootstrap.check(parsed.scheme == 'https'
                        and re.fullmatch(rf'globaldp-prod-{dispatch}[0-9]{{1,3}}\.{re.escape(domain)}', parsed.netloc)
                        and parsed.path == '/query_dispatch' and not parsed.query and not parsed.fragment)

    def encoded(value):
        return base64.b64encode(value.encode('utf-8')).decode('ascii')

    result = dict(config)
    result['ProtoDispatchKey'] = encoded(app['DispatchSeed'])
    result['GameDispatchChannelName'] = encoded(app['ChannelName'])
    result['GameDispatchArrayURL'] = [encoded(endpoint) for endpoint in endpoints]
    proof['policy'] = 'official-current-with-frozen-format-seed'
    proof['official'] = {'channel': build['channel'], 'version': build['version'], 'build': build['build'],
                         'manifest_md5': spec[4], 'file': RESOURCE, 'file_md5': asset.digest,
                         'file_bytes': asset.size,
                         'documents': {name: {'sha256': hashlib.sha256(row['payload']).hexdigest(),
                                              'id': row['id'], 'offset': row['offset'], 'size': row['size']}
                                       for name, row in documents.items()}}
    proof['official_parameters'] = ['ProtoDispatchKey', 'GameDispatchChannelName', 'GameDispatchArrayURL']
    proof['frozen_parameters'] = ['GameDispatchURLTemplate', 'GameGatewayURLTemplate',
                                  'GameDispatchDefaultName', 'DispatcherKey']
    result[bootstrap._PROVENANCE] = proof
    return result
