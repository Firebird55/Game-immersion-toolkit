"""Renew ZZZ request identity from authenticated official launcher TextAssets."""
import base64
import hashlib
import re
from urllib.parse import urlsplit

from . import hoyo_dispatch_metadata as bootstrap
from .hoyo_bootstrap_assets import text_assets
from . import sophon_assets as sophon


RESOURCE = 'ZenlessZoneZero_Data/resources.assets'
DOCUMENTS = frozenset({'app_version', 'login_setting'})


def renew(config, build, region, directory):
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
    files = sophon.manifest(directory, build['channel'], spec, ('resources.assets',))
    bootstrap.check(RESOURCE in files)
    asset = files[RESOURCE]
    documents = text_assets(asset.size, lambda start, length: asset.read(directory, start, length), DOCUMENTS)
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
                        and re.fullmatch(rf'globaldp-prod-{dispatch}0[1-9]\.{re.escape(domain)}', parsed.netloc)
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
