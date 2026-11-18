"""Inert original ChannelConfig preparation; never an active game descriptor.

All codec candidates come from the authenticated original native input. Only a
unique complete profile-container/object/JSON result receives a private receipt.
Final Source activation still requires its complete catalog and selected shards.
"""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile
from urllib.parse import urlsplit

from .genshin_blb_body import unpack
from .genshin_original_containers import DataObjects


SCHEMA = 'genshin-original-channel-profile-v1'
MAX_PACKAGE = 16 * 1024**2
MAX_BODY = 4 * 1024**2
MAX_TEXT = 1024**2
MAX_RECEIPT = 4 * MAX_TEXT


def check(condition):
    if not condition:
        raise ValueError('The original Genshin channel profile is incomplete or ambiguous.')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _unique(pairs):
    result = {}
    for name, value in pairs:
        check(name not in result)
        result[name] = value
    return result


def parse_profile(payload, contract):
    """Bounded strict UTF-8/JSON, preserving unknown original fields privately."""
    check(isinstance(payload, bytes) and 0 < len(payload) <= MAX_TEXT and isinstance(contract, dict)
          and contract.get('schema') == 'genshin-original-channel-loader-v1'
          and contract.get('profile_only') is True and contract.get('complete_dispatch_bootstrap') is False
          and contract.get('later_override_excluded') is False
          and {'ChannelName', 'DispatchConfigs'} <= set(contract.get('config_fields', ()))
          and {'DispatchName', 'DispatchUrls'} <= set(contract.get('dispatch_fields', ())))
    def invalid_constant(_value):
        check(False)
    value = json.loads(payload.decode('utf-8', errors='strict'), object_pairs_hook=_unique, parse_constant=invalid_constant)
    check(isinstance(value, dict) and isinstance(value.get('ChannelName'), str) and 0 < len(value['ChannelName']) <= 128)
    profiles = value.get('DispatchConfigs')
    check(isinstance(profiles, list) and 0 < len(profiles) <= 128)
    names = set()
    for profile in profiles:
        check(isinstance(profile, dict) and isinstance(profile.get('DispatchName'), str)
              and 0 < len(profile['DispatchName']) <= 128 and profile['DispatchName'] not in names)
        names.add(profile['DispatchName'])
        urls = profile.get('DispatchUrls')
        check(isinstance(urls, list) and 0 < len(urls) <= 128
              and all(isinstance(address, str) for address in urls) and len(set(urls)) == len(urls))
        for address in urls:
            check(isinstance(address, str) and 0 < len(address) <= 2048)
            parsed = urlsplit(address)
            check(parsed.scheme == 'https' and parsed.hostname and parsed.netloc == parsed.hostname
                  and parsed.hostname.endswith('.yuanshen.com') and parsed.path == '/query_region_list'
                  and not parsed.query and not parsed.fragment)
    if 'RSAParam' in value:
        rsa = value['RSAParam']
        check(isinstance(rsa, dict) and type(rsa.get('keyId')) is int and 0 <= rsa['keyId'] < 1 << 32)
    return value


def profile_body(data, contract):
    """Validate every original map entry before resolving native-owned IDs."""
    check(isinstance(data, bytes) and 0 < len(data) <= MAX_BODY)
    objects = DataObjects(len(data), lambda offset, size: data[offset:offset + size])
    check(0 < len(objects.names) <= 4096)
    all_payloads = {name: objects.named(name) for name in objects.names}
    candidates = contract.get('object_candidates')
    check(isinstance(candidates, list) and 0 < len(candidates) <= 16)
    ids = set()
    for row in candidates:
        check(isinstance(row, dict) and type(row.get('id')) is int and 0 <= row['id'] < 1 << 32)
        ids.add(row['id'])
    accepted = []
    for identity in sorted(ids):
        name = f'{identity:08x}'
        if name not in all_payloads:
            continue
        payload = all_payloads[name]
        try:
            parsed = parse_profile(payload, contract)
        except (ValueError, TypeError, RecursionError):
            continue
        accepted.append((identity, payload, parsed))
    check(len(accepted) == 1)
    identity, payload, parsed = accepted[0]
    return parsed, payload, {'object_id': identity, 'objects': len(objects.objects), 'named_objects': len(all_payloads),
                             'complete_named_object_map': True, 'strict_payload_eof': True,
                             'body_sha256': hashlib.sha256(data).hexdigest(), 'body_bytes': len(data),
                             'payload_sha256': hashlib.sha256(payload).hexdigest(), 'payload_bytes': len(payload)}


@dataclass(frozen=True)
class PreparedProfile:
    payload: bytes = field(repr=False)
    parameters: bytes = field(repr=False)
    proof: dict


def prepare_profile(executable, source, source_receipt, contract, helper, *, directory, check_cancel=lambda: None):
    """Profile-only acceptance from all current original-derived full contracts."""
    from .genshin_blb_native import discover_candidates
    from .genshin_native_x64 import Image
    check(isinstance(executable, bytes) and isinstance(contract, dict)
          and hashlib.sha256(executable).hexdigest() == contract['source_field']['executable_sha256'])
    source = Path(source)
    check(0 < source.stat().st_size <= MAX_PACKAGE and source.stat().st_size == source_receipt['bytes']
          and source_receipt['name'].rsplit('/', 1)[-1] == contract['source_basename'])
    with source.open('rb') as stream:
        check(hashlib.file_digest(stream, 'md5').hexdigest() == source_receipt['md5'])
    with source.open('rb') as stream:
        check(hashlib.file_digest(stream, 'sha256').hexdigest() == source_receipt['sha256'])
    check_cancel()
    candidates = discover_candidates(Image(executable))
    check(0 < len(candidates) <= 128 and len({row.sha256 for row in candidates}) == len(candidates))
    accepted = []
    for candidate in candidates:
        check(isinstance(candidate.parameters, bytes) and 0 < len(candidate.parameters) <= 32 * 1024
              and candidate.sha256 == hashlib.sha256(candidate.parameters).hexdigest()
              and 0 < len(candidate.method_sha256s) <= 128
              and list(candidate.method_sha256s) == sorted(set(candidate.method_sha256s))
              and all(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) for value in candidate.method_sha256s))
        check_cancel()
        with tempfile.TemporaryDirectory(prefix='channel-codec-', dir=directory) as home:
            work = Path(home)
            parameters, decoded, body = work / 'parameters.private', work / 'decoded', work / 'body'
            parameters.write_bytes(candidate.parameters)
            try:
                helper.decode(source, parameters, decoded, work=work)
                unpack(decoded, body, max_package=MAX_PACKAGE, max_body=MAX_BODY)
                parsed, payload, details = profile_body(body.read_bytes(), contract)
            except (ValueError, TypeError, struct.error, RecursionError):
                continue
            check_cancel()
            accepted.append(PreparedProfile(payload, candidate.parameters, {
                'schema': SCHEMA, **details, 'source': source_receipt,
                'native_executable_sha256': hashlib.sha256(executable).hexdigest(),
                'loader_contract_sha256': hashlib.sha256(canonical(contract)).hexdigest(),
                'codec_parameters_sha256': candidate.sha256, 'codec_method_sha256s': list(candidate.method_sha256s),
                'helper_identity': helper.identity, 'profile_count': len(parsed['DispatchConfigs']),
                'profile_only': True, 'complete_dispatch_bootstrap': False, 'full_catalog_validated': False,
                'selected_shards_validated': False, 'later_override_excluded': False,
                'response_signature_verified': False, 'community_numeric_data_used': False,
                'original_codec_candidates_tested': len(candidates)}))
    check(len(accepted) == 1)
    return accepted[0]
