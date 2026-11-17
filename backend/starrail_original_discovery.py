"""Original-source discovery used by ordinary publisher preparation.

The caller supplies descriptions derived from the matching original native
client. starrail_native_preparation joins authenticated metadata acquisition,
managed decoding and complete required description generation.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from . import sophon_assets as sophon, starrail_hotfix as hotfix
from .game_tools import _atomic_file
from .starrail_design import _uint


class SourceUnavailable(ValueError):
    """A missing/retired source or description must retain prior preparation."""


def _check(value):
    if not value:
        raise ValueError('Invalid original Star Rail discovery input.')


def _schema(value, required):
    _check(isinstance(value, list) and 0 < len(value) <= 256)
    named = []
    for field in value:
        _check(isinstance(field, dict) and isinstance(field.get('kind'), str)
               and field['kind'] in {'string', 'string_array', 'u32', 'bool'})
        name = field.get('semantic')
        _check(name is None or isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name))
        if name is not None:
            named.append(name)
    _check(len(set(named)) == len(named) and required <= set(named))
    return value


def _description(value):
    _check(isinstance(value, dict) and isinstance(value.get('native_file_md5'), str)
           and re.fullmatch('[0-9a-f]{32}', value['native_file_md5']))
    files = value.get('bootstrap_files')
    _check(isinstance(files, dict) and set(files) == {'config', 'version', 'native'})
    _check(all(isinstance(name, str) and re.fullmatch(r'(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+', name)
               and not {'.', '..'} & set(name.split('/')) for name in files.values())
           and len(set(files.values())) == len(files))
    _schema(value.get('client_schema'), {'GlobalDispatchUrlList', 'DefaultServerIndex'})
    _schema(value.get('version_schema'), {
        'Branch', 'MajorVersion', 'MinorVersion', 'PatchVersion', 'PakType', 'DispatchSeed'})
    global_data = value.get('global_dispatch')
    _check(isinstance(global_data, dict) and isinstance(global_data.get('region_fields'), dict)
           and set(global_data['region_fields']) == {'name', 'primary_gateway', 'alternate_gateway'})
    routes = value.get('routes')
    _check(isinstance(routes, list) and len(routes) == len(hotfix.ROUTES)
           and all(isinstance(row, dict) and type(row.get('wire_type')) is int and row['wire_type'] == 2
                   and isinstance(row.get('route'), str) for row in routes)
           and {row.get('route') for row in routes} == set(hotfix.ROUTES))
    for numbers in ([global_data.get('region_list_field')], list(global_data['region_fields'].values()),
                    [row.get('field') for row in routes]):
        _check(all(type(n) is int and 0 < n < 1 << 29 for n in numbers) and len(set(numbers)) == len(numbers))
    return value


def decode_bootstrap(data, schema):
    """Decode the supplied native description, including every discarded field."""
    _check(isinstance(data, bytes) and 0 < len(data) <= 1024**2)
    _schema(schema, set())
    at = 0
    def take(size):
        nonlocal at
        _check(0 <= size <= len(data) - at)
        result = data[at:at + size]
        at += size
        return result
    def string():
        length, = struct.unpack('>h', take(2))
        return take(length).decode('utf-8')
    def read(kind):
        if kind == 'string':
            return string()
        if kind == 'u32':
            return struct.unpack('>I', take(4))[0]
        if kind == 'bool':
            value = take(1)[0]
            _check(value in (0, 1))
            return bool(value)
        count, = struct.unpack('>I', take(4))
        _check(count <= (len(data) - at) // 2)
        return [string() for _ in range(count)]
    values = {}
    for field in schema:
        value = read(field['kind'])
        if field.get('semantic') is not None:
            values[field['semantic']] = value
    _check(at == len(data))
    return values


def protobuf_fields(data):
    at, rows = 0, []
    while at < len(data):
        tag, at = _uint(data, at, 32)
        number, wire = tag >> 3, tag & 7
        _check(0 < number < 1 << 29 and wire in (0, 1, 2, 5))
        if wire == 0:
            value, at = _uint(data, at, 64)
        else:
            if wire == 2:
                length, at = _uint(data, at, 32)
            else:
                length = 8 if wire == 1 else 4
            _check(length <= len(data) - at)
            value, at = data[at:at + length], at + length
        rows.append((number, wire, value))
    return rows


def _string(rows, number):
    found = [(wire, value) for field, wire, value in rows if field == number]
    _check(len(found) == 1 and found[0][0] == 2)
    return found[0][1].decode('utf-8')


def _endpoint(value, kind, channel):
    _check(isinstance(value, str))
    parsed = urlsplit(value)
    domain = 'starrails.com' if channel == 'starrail-global' else 'bhsr.com'
    _check(parsed.scheme == 'https' and parsed.hostname is not None
           and parsed.hostname.endswith('.' + domain) and not parsed.username and not parsed.password
           and parsed.port is None and parsed.path == '/query_' + kind and not parsed.query and not parsed.fragment)
    return value


def _protobuf_get(url, *, fetch=None):
    if fetch is None:
        with urlopen(Request(url, headers={'Accept-Encoding': 'identity'}), timeout=30) as response:
            _check(response.status == 200 and response.geturl() == url)
            raw = response.read(2 * 1024**2 + 1)
    else:
        raw = fetch(url, limit=2 * 1024**2)
    _check(isinstance(raw, bytes) and len(raw) <= 2 * 1024**2)
    return protobuf_fields(base64.b64decode(b''.join(raw.split()), validate=True))


def discover(directory, build, description, *, fetch=None):
    """Resolve current routes from official bootstrap and public dispatch GETs.

    No native file is executed, no third-party route feed is queried, and no
    account identifiers or credentials are sent. A matching native description
    is required; an older cache cannot silently supply another build's tags.
    """
    description = _description(description)
    _check(build.get('channel') in {'starrail-global', 'starrail-cn'})
    directory = Path(directory)
    suffixes = tuple(description['bootstrap_files'][key] for key in ('config', 'version', 'native'))
    options = {'fetch': fetch} if fetch is not None else {}
    files = sophon.manifest(directory, build['channel'], tuple(build['manifests']['game']), suffixes, **options)
    _check(set(files) == set(suffixes))
    if files[suffixes[2]].digest != description['native_file_md5']:
        raise SourceUnavailable('Derive a description from this original Star Rail client; the previous data is retained.')
    blobs = []
    for name in suffixes[:2]:
        asset = files[name]
        _check(0 < asset.size <= 1024**2)
        raw = asset.read(directory, 0, asset.size, **options)
        _check(len(raw) == asset.size and hashlib.md5(raw).hexdigest() == asset.digest)
        blobs.append(raw)
    config = decode_bootstrap(blobs[0], description['client_schema'])
    version = decode_bootstrap(blobs[1], description['version_schema'])
    numbers = [version[key] for key in ('MajorVersion', 'MinorVersion', 'PatchVersion')]
    _check(all(type(n) is int and 0 <= n < 1 << 32 for n in numbers))
    actual = '.'.join(map(str, numbers))
    _check(actual == build['version'] and version['Branch'] == f'V{numbers[0]}.{numbers[1]}Live'
           and isinstance(version['PakType'], str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,31}', version['PakType'])
           and isinstance(version['DispatchSeed'], str) and 0 < len(version['DispatchSeed']) <= 256)
    endpoints = config['GlobalDispatchUrlList']
    _check(isinstance(endpoints, list) and 0 < len(endpoints) <= 64)
    for endpoint in endpoints:
        _endpoint(endpoint, 'dispatch', build['channel'])
    prefix = 'OS' if build['channel'] == 'starrail-global' else 'CN'
    params = {'version': prefix + version['PakType'] + 'Win' + actual, 't': int(time.time()),
              'language_type': 1, 'platform_type': 3, 'channel_id': 1, 'sub_channel_id': 1, 'is_new_format': 1}
    # These request constants describe the native Windows public bootstrap.
    # ClientConfig layout and all protobuf field numbers are supplied inputs.
    rows = _protobuf_get(endpoints[0] + '?' + urlencode(params), **options)
    global_data = description['global_dispatch']
    encoded_regions = [(wire, value) for field, wire, value in rows if field == global_data['region_list_field']]
    _check(all(wire == 2 for wire, _ in encoded_regions))
    if not encoded_regions:
        raise SourceUnavailable('The publisher supplies no regions for this Star Rail client; the previous data is retained.')
    _check(len(encoded_regions) <= 64 and type(config['DefaultServerIndex']) is int
           and 0 <= config['DefaultServerIndex'] < len(encoded_regions))
    region = protobuf_fields(encoded_regions[config['DefaultServerIndex']][1])
    _check(_string(region, global_data['region_fields']['name']))
    gateway = _endpoint(_string(region, global_data['region_fields']['primary_gateway']), 'gateway', build['channel'])
    _endpoint(_string(region, global_data['region_fields']['alternate_gateway']), 'gateway', build['channel'])
    params.pop('is_new_format')
    params['dispatch_seed'] = version['DispatchSeed']
    rows = _protobuf_get(gateway + '?' + urlencode(params), **options)
    routes = {}
    for field in description['routes']:
        parsed = urlsplit(_string(rows, field['field']))
        _check(parsed.scheme == 'https' and parsed.hostname == sophon.CHANNELS[build['channel']][3]
               and not parsed.username and not parsed.password and parsed.port is None
               and not parsed.query and not parsed.fragment)
        routes[field['route']] = parsed.path.removeprefix('/')
    # Reuse native SRMI marker validation, including route/revision agreement.
    # _discover receives the actual response, never a third-party listing.
    listing = {prefix + actual: {hotfix.ROUTES[key][0]: value for key, value in routes.items()}}
    return build | {'hotfix': hotfix._discover(build, listing, **options)}


def prepare(directory, build, description, *, fetch=None):
    """Atomically retain a complete discovery, without storing its request seed."""
    result = discover(directory, build, description, **({'fetch': fetch} if fetch is not None else {}))
    receipt = {key: result[key] for key in ('channel', 'version', 'hotfix')}
    receipt['native_file_md5'] = description['native_file_md5']
    _atomic_file(Path(directory) / 'starrail-original-discovery' / 'current.json',
                 json.dumps(receipt, sort_keys=True).encode('utf-8'))
    return result
