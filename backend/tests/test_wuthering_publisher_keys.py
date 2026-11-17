"""Owned synthetic signed metadata; no publisher keys, packages or recordings."""
import base64
import hashlib
import json
from pathlib import Path
import struct
import uuid

import pytest
from Crypto.PublicKey import RSA

from backend import wuthering_publisher_keys as keys, wuthering_release as release
from backend import wuthering_release_pak as pak, wuthering_metadata as metadata
from backend.preparation_errors import PreparationFailure
from backend.tests.test_wuthering_metadata import encrypted_package, protected
from backend.tests.test_wuthering_retained_preparation import original


GUID = uuid.UUID('11111111-2222-3333-4444-555555555555')
OTHER = uuid.UUID('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
BASE = 'https://owned.aki-game.net/prod/client/OwnedPublisherRoot123/Windows/'
VERSION = '3.8.0'


@pytest.fixture(scope='module')
def signer():
    return RSA.generate(1024)


def signed(signer, payload, *, invalid_padding=False):
    encoded = b'\0\x01' + b'\xff' * (125 - len(payload)) + b'\0' + payload
    assert len(encoded) == 128
    if invalid_padding:
        encoded = encoded[:2] + b'\xfe' + encoded[3:]
    integer = pow(int.from_bytes(encoded, 'big'), signer.d, signer.n)
    return base64.b64encode(integer.to_bytes(128, 'big'))


def packet(signer, entries, *, payloads=None, invalid_padding=False):
    payloads = payloads if payloads is not None else [str(identity).encode() + b',' + base64.b64encode(value)
                                                   for identity, value in entries]
    raw = b''.join(signed(signer, payload, invalid_padding=invalid_padding) + b'\n' for payload in payloads)
    config = {'Hash': hashlib.sha1(raw).hexdigest(), 'Random': 'OwnedSyntheticRoute',
              'Key': base64.b64encode(signer.n.to_bytes(128, 'little')).decode(), 'UpdateTime': 1234}
    return json.dumps(config).encode(), raw


def native_package(parameter, identity=GUID):
    raw = encrypted_package(parameter)
    magic = raw.rfind(pak.MAGIC)
    raw[magic-17:magic-1] = struct.pack('<4I', *(int(identity.hex[i:i+8], 16) for i in range(0, 32, 8)))
    return raw


def fetcher(wire, body, *, base=BASE, version=VERSION, calls=None):
    calls = calls if calls is not None else []
    def fetch(url, *, limit):
        calls.append((url, limit))
        if url in (base + f'KeyList_{version}.json', base + 'KeyList.json'):
            return wire
        assert url == base + f'client_key/{version}/OwnedSyntheticRoute/PakData'
        return body
    return fetch


def test_same_reader_accepts_new_signed_parameters_and_revokes_untried_old_records(signer, tmp_path):
    old, new = bytes(range(32)), b'n' * 32
    wire_a, body_a = packet(signer, [(GUID, old)])
    pointers_a = {}
    first = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire_a, body_a), json.loads, pointers_a)
    wire_b, body_b = packet(signer, [(OTHER, new)])
    pointers_b = {}
    second = keys.current(tmp_path, BASE, VERSION, 'global', first,
                          fetcher(wire_b, body_b), json.loads, pointers_b)
    assert dict(first.native) == {GUID: old} and dict(second.native) == {OTHER: new}
    assert not tuple(second)  # A native-only candidate never becomes a default.
    assert first.sources != second.sources and pointers_a != pointers_b
    retained = keys.restore(tmp_path, list(first.sources), 'global', (), json.loads)
    assert dict(retained.native) == {GUID: old}
    assert not metadata.parameters(tmp_path)  # Wire validation alone authorizes no protected key.
    assert all(old.hex().encode() not in path.read_bytes() and base64.b64encode(old) not in path.read_bytes()
               for path in (tmp_path/'wuwa-publisher/native-key-inputs').rglob('*.json'))


def test_actual_package_reader_requires_exact_native_uuid_and_preserves_default_route(signer, tmp_path, monkeypatch, protected):
    parameter, default = bytes(range(32)), b'd' * 32
    wire, body = packet(signer, [(GUID, parameter)])
    inputs = keys.current(tmp_path, BASE, VERSION, 'global', (default, parameter), fetcher(wire, body), json.loads, {})
    assert tuple(inputs) == (default,)
    original = native_package(parameter)
    reads = []
    def block(url, total, offset, count):
        reads.append((offset, count))
        return bytes(original[offset:offset+count])
    monkeypatch.setattr(pak, 'block', block)
    selected = release._package(tmp_path, ('owned', len(original), 'first'), inputs)
    assert selected.locations(wanted={'Client/voices/a.wem'}) == {'Client/voices/a.wem': 0}
    assert metadata.parameters(tmp_path) == (parameter,)
    assert len(reads) == 4  # Complete encrypted main AND directory before persistence.
    wrong = keys.Parameters((parameter,), {OTHER: parameter}, ())
    with pytest.raises(PreparationFailure) as failure:
        release._package(tmp_path, ('wrong-guid', len(original), 'second'), wrong)
    assert failure.value.code == 'archive_parameters_missing'
    original[:] = native_package(default, uuid.UUID(int=0))
    assert release._package(tmp_path, ('default', len(original), 'third'), inputs).verified_parameter == default
    original[:] = native_package(default, OTHER)
    with pytest.raises(PreparationFailure) as error:
        release._package(tmp_path, ('unknown', len(original), 'fourth'), inputs)
    assert error.value.code == 'archive_parameters_missing'


def test_new_native_candidate_must_decrypt_complete_indices_even_when_plaintext_cache_exists(tmp_path, monkeypatch, protected):
    parameter = bytes(range(32))
    original = native_package(parameter)
    monkeypatch.setattr(pak, 'block', lambda url, total, offset, count: bytes(original[offset:offset+count]))
    warm = pak.Package('seed', len(original), 'seed', tmp_path, (parameter,))
    retained = {path.name: path.read_bytes() for path in warm.cache.iterdir()}
    # The mount-prefix sample stays intact. A plaintext cache must not mask the
    # new candidate's failure on the complete encrypted main index.
    original[128+40] ^= 1
    native = keys.Parameters((), {GUID: parameter}, ())
    with pytest.raises(ValueError):
        release._package(tmp_path, ('changed-wire', len(original), 'new'), native)
    assert not metadata.parameters(tmp_path)
    assert {path.name: path.read_bytes() for path in warm.cache.iterdir()} == retained


@pytest.mark.parametrize('prior_owner', ['default-new', 'other-native-uuid', 'legacy-value'])
def test_equal_verified_bytes_do_not_skip_a_new_owners_complete_original_checks(tmp_path, monkeypatch, protected, prior_owner):
    parameter = bytes(range(32))
    identity = uuid.UUID(int=0) if prior_owner == 'default-new' else GUID
    original = native_package(parameter, identity)
    monkeypatch.setattr(pak, 'block', lambda url, total, offset, count: bytes(original[offset:offset+count]))
    # Warm valid plaintext without recording a default or the selected native
    # UUID. Neither this cache nor a different verified owner is sufficient.
    pak.Package('warm', len(original), 'warm', tmp_path, (parameter,))
    if prior_owner == 'other-native-uuid':
        assert metadata.remember_parameter(tmp_path, parameter, native_guid=OTHER)
    elif prior_owner == 'legacy-value':
        assert metadata.remember_parameter(tmp_path, parameter)
    path = metadata._path(tmp_path, 'verified-parameters')
    before = path.read_bytes() if path.exists() else None
    original[128+40] ^= 1
    candidates = ((parameter,) if not identity.int else keys.Parameters((), {GUID: parameter}, ()))
    with pytest.raises(ValueError):
        release._package(tmp_path, ('changed-original', len(original), 'new-owner'), candidates)
    assert (path.read_bytes() if path.exists() else None) == before


def test_only_the_same_verified_native_owner_can_reuse_authenticated_plaintext_indices(tmp_path, monkeypatch, protected):
    parameter = bytes(range(32))
    original = native_package(parameter)
    calls = []
    def block(url, total, offset, count):
        calls.append((offset, count)); return bytes(original[offset:offset+count])
    monkeypatch.setattr(pak, 'block', block)
    candidates = keys.Parameters((), {GUID: parameter, OTHER: parameter}, ())
    release._package(tmp_path, ('first', len(original), 'first'), candidates)
    assert len(calls) == 4
    calls.clear()
    release._package(tmp_path, ('same-owner', len(original), 'same'), candidates)
    assert len(calls) == 2
    calls.clear(); original[:] = native_package(parameter, OTHER)
    release._package(tmp_path, ('new-owner', len(original), 'other'), candidates)
    assert len(calls) == 4
    assert set(metadata.native_parameters(tmp_path)) == {(GUID, parameter), (OTHER, parameter)}
    assert not metadata.baseline_parameters(tmp_path)


@pytest.mark.parametrize('fault', ['hash', 'modulus', 'modulus-base64', 'random-path', 'boolean-time', 'padding',
    'uuid', 'uuid-zero', 'uuid-spacing', 'separator', 'key-length', 'key-base64', 'conflicting-uuid', 'record-base64'])
def test_invalid_native_metadata_cannot_become_a_candidate(signer, fault):
    parameter = bytes(range(32))
    wire, body = packet(signer, [(GUID, parameter)])
    config = json.loads(wire)
    if fault == 'hash': config['Hash'] = '0' * 40
    elif fault == 'modulus': config['Key'] = base64.b64encode(bytes(128)).decode()
    elif fault == 'modulus-base64': config['Key'] += '\n'
    elif fault == 'random-path': config['Random'] = '../outside'
    elif fault == 'boolean-time': config['UpdateTime'] = True
    elif fault == 'record-base64': body = b'!' + body[1:]; config['Hash'] = hashlib.sha1(body).hexdigest()
    else:
        payload = str(GUID).encode() + b',' + base64.b64encode(parameter)
        if fault == 'uuid': payload = b'x' * 36 + payload[36:]
        elif fault == 'uuid-zero': payload = str(uuid.UUID(int=0)).encode() + payload[36:]
        elif fault == 'uuid-spacing': payload = b' ' + payload[1:]
        elif fault == 'separator': payload = payload[:36] + b':' + payload[37:]
        elif fault == 'key-length': payload = payload[:37] + base64.b64encode(parameter[:-1])
        elif fault == 'key-base64': payload = payload[:37] + b'!' + payload[38:]
        payloads = [payload]
        if fault == 'conflicting-uuid': payloads.append(str(GUID).encode() + b',' + base64.b64encode(b'x' * 32))
        wire, body = packet(signer, [], payloads=payloads, invalid_padding=fault == 'padding')
        config = json.loads(wire)
    with pytest.raises((ValueError, UnicodeError)):
        keys.records(config, body)


def test_identical_duplicate_and_shared_parameter_keep_every_explicit_uuid(signer):
    parameter = b'k' * 32
    wire, body = packet(signer, [(GUID, parameter), (GUID, parameter), (OTHER, parameter)])
    assert keys.records(json.loads(wire), body) == {GUID: parameter, OTHER: parameter}


def test_explicit_empty_native_list_does_not_fetch_a_guessed_body(tmp_path):
    wire = json.dumps({'Hash': '', 'Key': '', 'Random': '', 'UpdateTime': 0}).encode()
    calls = []
    inputs = keys.current(tmp_path, BASE, VERSION, 'global', (b'd' * 32,),
                          fetcher(wire, b'unused', calls=calls), json.loads, {})
    assert not inputs.native and len(calls) == 2 and tuple(inputs) == (b'd' * 32,)


@pytest.mark.parametrize('scope', ['region', 'version', 'host', 'role'])
def test_immutable_wire_cache_cannot_cross_publisher_version_host_or_role(signer, tmp_path, scope):
    wire, body = packet(signer, [(GUID, b'k' * 32)])
    inputs = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire, body), json.loads, {})
    refs = [dict(reference) for reference in inputs.sources]
    if scope == 'region': refs[0]['region'] = 'cn'
    elif scope == 'version': refs[0]['version'] = '3.9.0'
    elif scope == 'host': refs[0]['base'] = BASE.replace('owned.', 'different.')
    else: refs[0]['role'] = 'video'
    with pytest.raises(PreparationFailure) as error:
        keys.restore(tmp_path, refs, 'global', (), json.loads)
    assert error.value.code == 'publisher_key_inputs_missing'


def test_corrupt_wire_cache_repairs_only_from_exact_original_hash_and_outage_keeps_old_inputs(signer, tmp_path):
    wire, body = packet(signer, [(GUID, b'k' * 32)])
    first = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire, body), json.loads, {})
    files = list((tmp_path/'wuwa-publisher/native-key-inputs').rglob('*.json'))
    files[0].write_bytes(b'[]')
    def outage(url, *, limit):
        if url.endswith('.json'): return wire
        raise OSError('Owned publisher body outage')
    with pytest.raises(PreparationFailure) as error:
        keys.current(tmp_path, BASE, VERSION, 'global', (), outage, json.loads, {})
    assert error.value.code == 'publisher_key_metadata_failed' and files[0].read_bytes() == b'[]'
    repaired = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire, body), json.loads, {})
    assert repaired.sources == first.sources
    calls = []
    warm = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire, b'unused', calls=calls), json.loads, {})
    assert warm.sources == first.sources and len(calls) == 2


def test_interrupted_rotated_wire_publication_preserves_prior_immutable_source(signer, tmp_path, monkeypatch):
    wire_a, body_a = packet(signer, [(GUID, b'a' * 32)])
    old = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire_a, body_a), json.loads, {})
    old_bytes = {p: p.read_bytes() for p in (tmp_path/'wuwa-publisher/native-key-inputs').rglob('*.json')}
    wire_b, body_b = packet(signer, [(GUID, b'b' * 32)])
    def interrupted(*args): raise OSError('Owned atomic native-wire interruption')
    monkeypatch.setattr(keys, '_atomic_file', interrupted)
    with pytest.raises(PreparationFailure):
        keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire_b, body_b), json.loads, {})
    assert all(path.read_bytes() == raw for path, raw in old_bytes.items())
    assert keys.restore(tmp_path, list(old.sources), 'global', (), json.loads).native == old.native


def test_normal_snapshot_and_later_voice_reader_restore_the_same_native_uuid_inputs(signer, tmp_path, monkeypatch):
    wire, body = packet(signer, [(GUID, b'k' * 32)])
    inputs = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire, body), json.loads, {})
    monkeypatch.setattr(release, 'launcher', lambda region: ('3.8.0', 'owned-launcher', {}))
    monkeypatch.setattr(release, 'discover', lambda *a, **k: ({'resource': '3.8.11'}, {}, {}, inputs, {'pointer': b'owned'}))
    monkeypatch.setattr(release, '_archive_parameters', lambda *_: ())
    stamp, descriptor, params, pointers = release._current(tmp_path, 101)
    assert descriptor['native_key_sources'] == list(inputs.sources)
    assert params.native == inputs.native and pointers == {'pointer': b'owned'}
    assert release._voice_parameters(stamp, tmp_path).native == inputs.native
    # Retained replay reconstructs from that exact descriptor; no live source.
    assert release._parameters_for_snapshot(tmp_path, descriptor).native == inputs.native


@pytest.fixture
def native_voice(signer, tmp_path, monkeypatch, protected):
    """Exercise the real voice entry point without a feed or protected key."""
    parameter = bytes(range(32))
    wire, body = packet(signer, [(GUID, parameter)])
    inputs = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire, body), json.loads, {})
    snapshot = {'schema': 1, 'region': 'global', 'native_key_sources': list(inputs.sources)}
    data, calls = native_package(parameter), []
    def unavailable(url, *, limit):
        assert url == release.PUBLIC_METADATA_URL
        calls.append('legacy-unavailable')
        raise OSError('Owned legacy metadata outage')
    def block(url, size, offset, count):
        assert url == 'owned-native-voice'
        calls.append((offset, count))
        return bytes(data[offset:offset+count])
    monkeypatch.setattr(release, 'download', unavailable)
    monkeypatch.setattr(pak, 'block', block)
    def prepare():
        raw = json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()
        stamp = 'wuwa-' + hashlib.sha256(raw).hexdigest()
        path = release._descriptor_path(tmp_path, stamp)
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        return release._voice_package(tmp_path, stamp, ('owned-native-voice', len(data), stamp))
    return parameter, data, calls, snapshot, prepare


@pytest.mark.parametrize('baseline', ['absent', 'protected-empty'])
def test_real_voice_package_works_with_only_owned_native_inputs(native_voice, tmp_path, baseline):
    parameter, _, calls, _, prepare = native_voice
    if baseline == 'protected-empty':
        assert metadata._write(metadata._path(tmp_path, 'verified-parameters'),
                               b'{"schema":1,"parameters":[]}')
    assert not metadata.parameters(tmp_path)
    result = prepare()
    assert result.locations(wanted={'Client/voices/a.wem'}) == {'Client/voices/a.wem': 0}
    assert result.verified_parameter == parameter and metadata.parameters(tmp_path) == (parameter,)
    assert calls[0] == 'legacy-unavailable' and len(calls) == 5


@pytest.mark.parametrize('identity', [uuid.UUID(int=0), OTHER])
def test_native_only_voice_package_never_uses_unrelated_key_as_default(native_voice, tmp_path, identity):
    parameter, data, _, _, prepare = native_voice
    data[:] = native_package(parameter, identity)
    with pytest.raises(PreparationFailure) as error:
        prepare()
    assert error.value.code == 'archive_parameters_missing'
    assert not metadata.parameters(tmp_path)


@pytest.mark.parametrize('fault', ['envelope', 'json', 'schema', 'boolean-schema', 'missing-list', 'null-list',
                                  'invalid-key', 'directory'])
def test_present_invalid_legacy_cache_cannot_authorize_native_only_fallback(native_voice, tmp_path, fault):
    _, _, calls, _, prepare = native_voice
    path = metadata._path(tmp_path, 'verified-parameters')
    if fault == 'directory':
        path.mkdir(parents=True)
    elif fault == 'envelope':
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'not-a-protected-envelope')
    else:
        raw = {'json': b'{', 'schema': b'{"schema":2,"parameters":[]}',
            'boolean-schema': b'{"schema":true,"parameters":[]}', 'missing-list': b'{"schema":1}',
            'null-list': b'{"schema":1,"parameters":null}',
            'invalid-key': b'{"schema":1,"parameters":["bad"]}'}[fault]
        assert metadata._write(path, raw)
    with pytest.raises(PreparationFailure) as error:
        prepare()
    assert error.value.code == 'game_metadata_unavailable'
    assert calls == []  # Reject present corruption before consulting a feed.


@pytest.mark.parametrize('fault', ['region', 'host', 'hash', 'wire', 'historical'])
def test_native_only_voice_package_keeps_immutable_authority_guards(native_voice, tmp_path, fault):
    _, _, calls, snapshot, prepare = native_voice
    if fault == 'region': snapshot['region'] = 'cn'
    elif fault == 'host': snapshot['native_key_sources'][0]['base'] = BASE.replace('owned.', 'different.')
    elif fault == 'hash': snapshot['native_key_sources'][0]['sha256'] = '0' * 64
    elif fault == 'wire':
        next((tmp_path/'wuwa-publisher/native-key-inputs').rglob('*.json')).write_bytes(b'corrupt')
    else: del snapshot['native_key_sources']
    with pytest.raises(PreparationFailure) as error:
        prepare()
    assert error.value.code == ('game_metadata_unavailable' if fault == 'historical' else 'publisher_key_inputs_missing')
    assert calls == ['legacy-unavailable'] and not metadata.parameters(tmp_path)


def test_native_only_fallback_cannot_swallow_other_preparation_failures(native_voice, monkeypatch):
    _, _, calls, _, prepare = native_voice
    def rejected(*args):
        raise PreparationFailure('owned_integrity_failure', 'Owned integrity control')
    monkeypatch.setattr(release, '_archive_parameters', rejected)
    with pytest.raises(PreparationFailure) as error:
        prepare()
    assert error.value.code == 'owned_integrity_failure' and calls == []


@pytest.mark.parametrize('independent_default', [False, True])
def test_verified_native_a_removed_b_cannot_become_default_but_retained_a_still_works(
        native_voice, tmp_path, monkeypatch, independent_default):
    parameter, data, _, snapshot, prepare = native_voice
    if independent_default:
        data[:] = native_package(parameter, uuid.UUID(int=0))
        # Separate complete package proof owns this default; equal bytes alone
        # in a mutable feed must never establish that independent provenance.
        release._package(tmp_path, ('owned-native-voice', len(data), 'independent-default'), (parameter,))
        data[:] = native_package(parameter)
    first = prepare()
    assert first.verified_native_guid == GUID
    assert metadata.native_parameters(tmp_path) == ((GUID, parameter),)
    assert metadata.baseline_parameters(tmp_path) == ((parameter,) if independent_default else ())
    assert metadata.default_parameters(tmp_path) == ((parameter,) if independent_default else ())
    retained_a = json.loads(json.dumps(snapshot))
    disabled = json.dumps({'Hash': '', 'Key': '', 'Random': '', 'UpdateTime': 0}).encode()
    inputs_b = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(disabled, b''), json.loads, {})
    snapshot['native_key_sources'] = list(inputs_b.sources)
    # The old native value is still present in the foreign feed in generation B.
    # Its removal from B's original KeyList must not grant default eligibility.
    monkeypatch.setattr(release, 'download', lambda url, **kwargs: json.dumps({'legacy': '0x'+parameter.hex()}).encode())
    data[:] = native_package(parameter, uuid.UUID(int=0))
    if independent_default:
        assert prepare().verified_parameter == parameter
    else:
        with pytest.raises(PreparationFailure) as error:
            prepare()
        assert error.value.code == 'archive_parameters_missing'
    snapshot.clear(); snapshot.update(retained_a)
    data[:] = native_package(parameter)
    release._voice_package.cache_clear(); release._voice_parameters.cache_clear()
    assert prepare().verified_native_guid == GUID
    assert metadata.baseline_parameters(tmp_path) == ((parameter,) if independent_default else ())


def test_a_matching_legacy_value_is_not_independent_default_ownership(native_voice, tmp_path):
    parameter, _, _, _, prepare = native_voice
    assert metadata.remember_parameter(tmp_path, parameter)
    assert not metadata.default_parameters(tmp_path)
    prepare()
    assert metadata.native_parameters(tmp_path) == ((GUID, parameter),)
    assert not metadata.baseline_parameters(tmp_path) and not metadata.default_parameters(tmp_path)


def test_failed_native_ownership_publication_preserves_prior_protected_state(native_voice, tmp_path, monkeypatch):
    _, _, _, _, prepare = native_voice
    prior = b'd' * 32
    assert metadata.remember_parameter(tmp_path, prior)
    path = metadata._path(tmp_path, 'verified-parameters')
    before = path.read_bytes()
    monkeypatch.setattr(metadata, '_write', lambda *args: False)
    with pytest.raises(PreparationFailure) as error:
        prepare()
    assert error.value.code == 'publisher_key_cache_failed'
    assert path.read_bytes() == before and metadata.parameters(tmp_path) == (prior,)
    assert not metadata.native_parameters(tmp_path)


def test_native_owner_cannot_be_retagged_by_legacy_save_before_any_write(tmp_path, protected, monkeypatch):
    parameter = b'a' * 32
    assert metadata.remember_parameter(tmp_path, parameter, native_guid=GUID)
    before = metadata._path(tmp_path, 'verified-parameters').read_bytes()
    def forbidden(*args): raise AssertionError('Invalid provenance must stop before publication')
    monkeypatch.setattr(metadata, '_write', forbidden)
    assert not metadata.remember_parameter(tmp_path, parameter)
    assert metadata._path(tmp_path, 'verified-parameters').read_bytes() == before
    assert metadata.baseline_parameters(tmp_path) == ()


@pytest.mark.parametrize('identity,default', [(uuid.UUID(int=0), False), (GUID, True), (None, 1)])
def test_impossible_native_default_write_roles_are_rejected(tmp_path, protected, identity, default):
    assert not metadata.remember_parameter(tmp_path, b'a' * 32, native_guid=identity, default_verified=default)
    assert not metadata._path(tmp_path, 'verified-parameters').exists()


@pytest.mark.parametrize('fault', ['replace', 'false-success'])
def test_native_atomic_replace_and_readback_failures_keep_prior_envelope(native_voice, tmp_path, monkeypatch, fault):
    from backend import atomic_files
    _, _, _, _, prepare = native_voice
    assert metadata.remember_parameter(tmp_path, b'd' * 32)
    path = metadata._path(tmp_path, 'verified-parameters')
    before = path.read_bytes()
    if fault == 'replace':
        replace = atomic_files.replace
        def interrupted(source, target, *args, **kwargs):
            if Path(target) == path: raise OSError('Owned protected atomic-replace interruption')
            return replace(source, target, *args, **kwargs)
        monkeypatch.setattr(atomic_files, 'replace', interrupted)
    else:
        monkeypatch.setattr(metadata, '_write', lambda *args: True)
    with pytest.raises(PreparationFailure) as error:
        prepare()
    assert error.value.code == 'publisher_key_cache_failed'
    assert path.read_bytes() == before and not list(path.parent.glob('*.pending'))


def test_provenance_reclassification_at_capacity_does_not_add_a_candidate(tmp_path, protected):
    values = [number.to_bytes(32, 'big') for number in range(1024)]
    path = metadata._path(tmp_path, 'verified-parameters')
    assert metadata._write(path, json.dumps({'schema': 1, 'parameters': [value.hex() for value in values]}).encode())
    assert metadata.remember_parameter(tmp_path, values[0], native_guid=GUID)
    assert len(metadata.parameters(tmp_path)) == 1024
    assert values[0] not in metadata.baseline_parameters(tmp_path)
    before = path.read_bytes()
    assert not metadata.remember_parameter(tmp_path, b'x' * 32, native_guid=OTHER)
    assert path.read_bytes() == before


def test_archive_candidates_use_one_consistent_protected_envelope(tmp_path, protected, monkeypatch):
    native, default = b'n' * 32, b'd' * 32
    assert metadata.remember_parameter(tmp_path, native, native_guid=GUID)
    assert metadata.remember_parameter(tmp_path, default, default_verified=True)
    monkeypatch.setattr(release, 'download', lambda *args, **kwargs: json.dumps(
        {'metadata': ['0x'+native.hex(), '0x'+default.hex()]}).encode())
    original_read, reads = metadata._parameter_record, []
    def read(tools):
        reads.append(tools)
        return original_read(tools)
    monkeypatch.setattr(metadata, '_parameter_record', read)
    assert release._archive_parameters(tmp_path) == (default,)
    assert reads == [tmp_path]


@pytest.mark.parametrize('fault', ['zero-native', 'unproven-overlap', 'foreign-default'])
def test_protected_reader_rejects_impossible_owner_combinations(tmp_path, protected, fault):
    parameter = b'a' * 32
    value = {'schema': 1, 'parameters': [], 'native_parameters': []}
    if fault == 'zero-native':
        value['native_parameters'] = [{'uuid': str(uuid.UUID(int=0)), 'parameter': parameter.hex()}]
    elif fault == 'unproven-overlap':
        value['parameters'] = [parameter.hex()]
        value['native_parameters'] = [{'uuid': str(GUID), 'parameter': parameter.hex()}]
    else:
        value['default_parameters'] = [parameter.hex()]
    assert metadata._write(metadata._path(tmp_path, 'verified-parameters'), json.dumps(value).encode())
    assert metadata._parameter_record(tmp_path) is None and not metadata.empty_parameter_cache(tmp_path)


def test_rotated_native_verified_values_keep_both_exact_owners_and_never_gain_baseline(tmp_path, protected):
    for parameter in (b'a' * 32, b'b' * 32):
        assert metadata.remember_parameter(tmp_path, parameter, native_guid=GUID)
    assert metadata.parameters(tmp_path) == (b'a' * 32, b'b' * 32)
    assert metadata.native_parameters(tmp_path) == ((GUID, b'a' * 32), (GUID, b'b' * 32))
    assert metadata.baseline_parameters(tmp_path) == () and metadata.empty_parameter_cache(tmp_path)


@pytest.mark.parametrize('native', [None, {}, [{'uuid': 'bad', 'parameter': 'aa'*32}],
    [{'uuid': str(GUID), 'parameter': 'aa'}]])
def test_malformed_protected_native_ownership_is_not_rewritten_as_default(native_voice, tmp_path, native):
    _, _, calls, _, prepare = native_voice
    path = metadata._path(tmp_path, 'verified-parameters')
    assert metadata._write(path, json.dumps({'schema': 1, 'parameters': [], 'native_parameters': native}).encode())
    before = path.read_bytes()
    with pytest.raises(PreparationFailure):
        prepare()
    assert not metadata.remember_parameter(tmp_path, b'd' * 32)
    assert path.read_bytes() == before and calls == []


def test_changed_publisher_modulus_and_parameter_need_no_software_or_feed_change(signer, tmp_path):
    first_wire, first_body = packet(signer, [(GUID, b'a' * 32)])
    first = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(first_wire, first_body), json.loads, {})
    changed_signer = RSA.generate(1024)
    next_wire, next_body = packet(changed_signer, [(GUID, b'b' * 32)])
    changed = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(next_wire, next_body), json.loads, {})
    assert first.native[GUID] == b'a' * 32 and changed.native[GUID] == b'b' * 32
    assert keys.restore(tmp_path, list(first.sources), 'global', (), json.loads).native[GUID] == b'a' * 32


def test_untried_uuid_revoked_in_b_cannot_return_through_legacy_feed(signer, tmp_path, monkeypatch, protected):
    parameter = bytes(range(32))
    wire, body = packet(signer, [(GUID, parameter)])
    first = keys.current(tmp_path, BASE, VERSION, 'global', (), fetcher(wire, body), json.loads, {})
    assert first.native[GUID] == parameter and not metadata.parameters(tmp_path)
    disabled = json.dumps({'Hash': '', 'Key': '', 'Random': '', 'UpdateTime': 0}).encode()
    second = keys.current(tmp_path, BASE, VERSION, 'global', (parameter,), fetcher(disabled, b''), json.loads, {})
    assert not second.native and tuple(second) == (parameter,)
    original = native_package(parameter)
    monkeypatch.setattr(pak, 'block', lambda url, total, offset, count: bytes(original[offset:offset+count]))
    with pytest.raises(PreparationFailure) as error:
        release._package(tmp_path, ('revoked-owner', len(original), 'revoked'), second)
    assert error.value.code == 'archive_parameters_missing'
    assert not metadata.parameters(tmp_path)


@pytest.fixture
def native_discovery(signer, tmp_path, monkeypatch):
    wire, body = packet(signer, [(GUID, b'k' * 32)])
    resource = BASE.replace('OwnedPublisherRoot123', 'OwnedResourceRoot123')
    mix = BASE.replace('OwnedPublisherRoot123', 'OwnedKeyRouteRoot123')
    cdn = 'https://owned.aki-game.net/prod/client/'
    calls = []
    class Bootstrap:
        def member(self, name):
            assert name == 'Client/Config/Kuro/KuroPublicConfig.ini'
            return b'InternalPrefix=https://aki-config-owned.aki-game.net\nUrlPath=OwnedBootstrapRoute123\n'
    monkeypatch.setattr(release, '_package', lambda *_: Bootstrap())
    monkeypatch.setattr(release, '_archive_parameters', lambda *_: (b'd' * 32,))
    monkeypatch.setattr(release, '_resource_inventory', lambda *a: ({'resource': '3.8.11'}, {}, {}))
    monkeypatch.setattr(release, 'launcher', lambda region: ('3.8.0', 'owned-launcher',
        {'Client/Content/Paks/pakchunk0-WindowsNoEditor.pak': (1024, 'a' * 32)}))
    bootstrap = {'default': {'ResUri': 'OwnedResourceRoot123', 'MixUri': 'OwnedKeyRouteRoot123',
                            'CdnUrl': [{'url': cdn, 'weight': '10'}]}}
    config = {'PackageVersion': VERSION, 'ResVersions': {}}
    def fetch(url, *, limit):
        calls.append(url)
        if url == 'https://aki-config-owned.aki-game.net/OwnedBootstrapRoute123/index.json':
            return json.dumps(bootstrap).encode()
        if url == resource + 'config.json': return json.dumps(config).encode()
        return fetcher(wire, body, base=mix)(url, limit=limit)
    monkeypatch.setattr(release, 'download', fetch)
    monkeypatch.setattr(release, '_native_key_download', fetch)
    return calls, resource, mix, wire, body, fetch


def test_actual_normal_discovery_uses_mixuri_and_packageversion_not_resource_revision(native_discovery, tmp_path):
    calls, resource, mix, wire, _, _ = native_discovery
    stamp, snapshot, inputs, pointers = release._current(tmp_path, 205)
    assert snapshot['versions']['resource'] == '3.8.11'
    assert dict(inputs.native) == {GUID: b'k' * 32}
    assert mix + 'KeyList_3.8.0.json' in calls
    assert all('KeyList_3.8.11' not in url and not url.startswith(resource + 'KeyList') for url in calls)
    assert pointers[mix + 'KeyList_3.8.0.json'] == wire and pointers[mix + 'KeyList.json'] == wire
    assert release._snapshot(tmp_path, stamp)['native_key_sources'] == list(inputs.sources)


def test_normal_pointer_recheck_rejects_keylist_update_before_descriptor_publication(native_discovery, tmp_path, monkeypatch):
    calls, _, mix, wire, _, fetch = native_discovery
    count = 0
    def changes(url, *, limit):
        nonlocal count
        if url == mix + 'KeyList_3.8.0.json':
            count += 1
            if count == 2: return wire + b' '
        return fetch(url, limit=limit)
    monkeypatch.setattr(release, 'download', changes)
    monkeypatch.setattr(release, '_native_key_download', changes)
    with pytest.raises(ValueError, match='updated'):
        release._current(tmp_path, 206)
    assert not list((tmp_path/'wuwa-publisher').glob('wuwa-*/release.json'))


@pytest.mark.parametrize('fault', ['outage', 'corrupt-packet', 'publication'])
def test_actual_language_worker_keeps_old_index_and_recording_on_native_refresh_failure(original, signer, monkeypatch, fault):
    from backend import language_worker as worker, wuthering_assets as assets
    tools, _, _, _, _ = original
    payload = release.build_language(tools, 'en', ['zh-Hans'])
    output = tools/'prepared-en.json'
    worker.write_payload('wuwa', payload, 'en', ['zh-Hans'], output)
    recording = tools/'saved-owned-recording.bin'
    recording.write_bytes(b'owned retained recording bytes')
    before, recorded = output.read_bytes(), recording.read_bytes()
    wire, body = packet(signer, [(GUID, b'k' * 32)])
    fetch = fetcher(wire, body + b'corrupt' if fault == 'corrupt-packet' else body)
    if fault == 'outage':
        def fetch(*args, **kwargs): raise OSError('Owned publisher outage')
    elif fault == 'publication':
        def interrupted(*args): raise OSError('Owned native-wire publication interruption')
        monkeypatch.setattr(keys, '_atomic_file', interrupted)
    def prepare(*args, **kwargs):
        keys.current(tools, BASE, VERSION, 'global', (), fetch, json.loads, {})
        return payload
    monkeypatch.setattr(assets, 'index_language', prepare)
    with pytest.raises(PreparationFailure) as error:
        worker.build('wuwa', None, tools, 'en', ['zh-Hans'], output)
    assert error.value.code == 'publisher_key_metadata_failed'
    assert output.read_bytes() == before and recording.read_bytes() == recorded
    assert not metadata.parameters(tools)
