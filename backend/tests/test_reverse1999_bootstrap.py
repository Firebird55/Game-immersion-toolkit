"""Authored Unity-layout fixtures; no original game data or game keys."""
import hashlib
import struct

import pytest

from backend import reverse1999_bootstrap as bootstrap


def integer(value):
    return struct.pack('<i', value)


def aligned(raw):
    return raw + b'\0' * (-len(raw) % 4)


def string(raw):
    if isinstance(raw, str):
        raw = raw.encode()
    return aligned(integer(len(raw)) + raw)


def fixture(*, revision='111.0.1065', branch='109', fields=None, config=True,
            unity='2022.3.62f2', overlap=False):
    fields = fields if fields is not None else [('appbuildid', '73'), ('voicebranch', branch),
                                               ('resversion', revision), ('appversion', '0.0.1')]
    objects = [(49, string(name) + string(value)) for name, value in fields]
    if config:
        objects.append((114, b'\0' * 28 + string('bluepoch') + integer(8) + b'owned123'))
    metadata = unity.encode() + b'\0' + integer(19) + b'\0' + integer(2)
    for class_id in (49, 114):
        metadata += integer(class_id) + b'\0' + struct.pack('<h', -1)
        if class_id == 114:
            metadata += b'\0' * 16
        metadata += b'\0' * 16
    metadata += integer(len(objects))
    payload = b''
    for index, (class_id, data) in enumerate(objects):
        metadata += b'\0' * (-(48 + len(metadata)) % 4)
        offset = 0 if overlap and index == 1 else len(payload)
        metadata += struct.pack('<qqIi', index + 1, offset, len(data), (49, 114).index(class_id))
        payload += data
    metadata += integer(0) * 3 + b'\0'  # scripts, externals, reference types, user information
    data_start = 48 + len(metadata)
    header = b'\0' * 8 + struct.pack('>I', 22) + b'\0' * 8
    header += struct.pack('>IQQQ', len(metadata), data_start + len(payload), data_start, 0)
    return header + metadata + payload


def read(raw, revision='111.0.1065'):
    return bootstrap.read(raw, expected_revision=revision, expected_sha256=hashlib.sha256(raw).hexdigest())


def test_original_bootstrap_metadata_and_opaque_configuration_are_data_only():
    result = read(fixture())
    assert (result.build_id, result.voice_branch, result.resource_revision) == (73, 109, '111.0.1065')
    assert result.publisher_app_version == '0.0.1'  # not the public launcher version
    assert result.game_config_payload == b'owned123'
    assert 'owned123' not in repr(result)


def test_normal_build_branch_resource_and_unity_patch_change_without_adapter_change():
    result = read(fixture(revision='112.0.1', branch='110', unity='2022.3.65f1'), '112.0.1')
    assert result.voice_branch == 110 and result.resource_revision == '112.0.1'


def test_original_release_identity_and_independent_hash_are_required():
    raw = fixture()
    with pytest.raises(ValueError, match='SHA256'):
        bootstrap.read(raw, expected_revision='111.0.1065', expected_sha256=None)
    with pytest.raises(ValueError, match='hash mismatch'):
        bootstrap.read(raw, expected_revision='111.0.1065', expected_sha256='0' * 64)
    with pytest.raises(ValueError, match='resource identity'):
        read(raw, '112.0.1')


@pytest.mark.parametrize('transform', [
    lambda raw: raw[:8] + struct.pack('>I', 23) + raw[12:],
    lambda raw: raw[:16] + b'\1' + raw[17:],
    lambda raw: raw[:24] + struct.pack('>Q', len(raw) + 1) + raw[32:],
    lambda raw: raw[:32] + struct.pack('>Q', len(raw) + 1) + raw[40:],
    lambda raw: raw[:20] + struct.pack('>I', 2**24) + raw[24:],
    lambda raw: raw[:64] + b'\1' + raw[65:],  # unsupported embedded type trees
    lambda raw: raw[:-1],
])
def test_changed_serialization_and_corrupt_bounds_fail_before_consumption(transform):
    with pytest.raises((ValueError, UnicodeError)):
        read(transform(fixture()))


@pytest.mark.parametrize('options', [
    {'config': False},
    {'branch': ''},
    {'branch': '109.0'},
    {'overlap': True},
    {'fields': [('appbuildid', '73'), ('voicebranch', '109'), ('resversion', '111.0.1065'),
                ('appversion', '0.0.1'), ('voicebranch', '110')]},
    {'fields': [('appbuildid', '73'), ('voicebranch', '109'), ('resversion', '111.0.1065')]},
])
def test_missing_duplicate_or_ambiguous_bootstrap_fields_do_not_become_defaults(options):
    with pytest.raises(ValueError):
        read(fixture(**options))
