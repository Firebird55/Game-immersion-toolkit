"""Recovery uses protected, original-package-verified inputs; never feed guesses."""
import hashlib
import json
import struct

import pytest
from Crypto.Cipher import AES

from backend import lexirise, wuthering_metadata as metadata, wuthering_release as release
from backend import wuthering_release_pak as pak
from backend.preparation_errors import PreparationFailure


@pytest.fixture
def protected(monkeypatch):
    def envelope(raw, decrypt=False):
        if decrypt:
            if not raw.startswith(b'authored-protected-envelope:'):
                raise ValueError('Invalid synthetic protection')
            return raw.removeprefix(b'authored-protected-envelope:')[::-1]
        return b'authored-protected-envelope:' + raw[::-1]
    monkeypatch.setattr(lexirise, '_protect', envelope)


def encrypted_package(parameter):
    def i(value): return struct.pack('<i', value)
    def text(value):
        raw = value.encode() + b'\0'
        return i(len(raw)) + raw
    def aligned(raw): return raw + bytes(-len(raw) % 16)
    directory = aligned(i(1) + text('voices/') + i(1) + text('a.wem') + i(0))
    encoded = struct.pack('<IBII', 0xa0000000, 0, 16, 32)
    main = aligned(text('../../../Client/') + i(1) + bytes(8) + i(1) + bytes(36) + i(1)
        + struct.pack('<QQ', 512, len(directory)) + hashlib.sha1(directory).digest() + i(len(encoded)) + encoded)
    data = bytearray(1024)
    cipher = AES.new(parameter, AES.MODE_ECB)
    data[128:128+len(main)] = cipher.encrypt(main)
    data[512:512+len(directory)] = cipher.encrypt(directory)
    footer = pak.MAGIC + struct.pack('<IQQ', 12, 128, len(main)) + hashlib.sha1(main).digest()
    data[819] = 1
    data[820:820+len(footer)] = footer
    return data


def test_only_a_complete_original_directory_validation_authorizes_recovery(tmp_path, monkeypatch, protected):
    key, guess = bytes(range(32)), b'x' * 32
    data = encrypted_package(key)
    monkeypatch.setattr(pak, 'block', lambda url, size, pos, count: bytes(data[pos:pos+count]))
    package = release._package(tmp_path, ('original', len(data), 'first'), (guess, key))
    assert package.verified_parameter == key
    assert metadata.parameters(tmp_path) == (key,)
    assert guess not in metadata.parameters(tmp_path)
    with pytest.raises(PreparationFailure) as failure:
        release._package(tmp_path, ('unknown-key-original', len(data), 'unknown'), (guess,))
    assert failure.value.code == 'archive_parameters_missing'
    assert metadata.parameters(tmp_path) == (key,)
    envelope = metadata._path(tmp_path, 'verified-parameters').read_bytes()
    assert key.hex().encode() not in envelope
    # Matching the mount prefix alone is insufficient: the actual main SHA fails.
    data[128 + 40] ^= 1
    # A new declared native digest must not reuse the already authenticated old
    # plaintext. An unchanged digest could legitimately reuse those old bytes.
    magic = data.rfind(pak.MAGIC)
    data[magic+24:magic+44] = hashlib.sha1(b'new unauthenticated main').digest()
    with pytest.raises(ValueError):
        release._package(tmp_path, ('changed-original', len(data), 'second'), (guess, key))
    assert metadata._path(tmp_path, 'verified-parameters').read_bytes() == envelope


def test_exact_native_index_reuse_across_packages_keeps_current_cipher_authentication(tmp_path, monkeypatch):
    first, second = bytes(range(32)), b'k' * 32
    originals = {'first': encrypted_package(first), 'second': encrypted_package(second)}
    reads = []
    def block(url, total, offset, size):
        reads.append((url, offset, size))
        return bytes(originals[url][offset:offset+size])
    monkeypatch.setattr(pak, 'block', block)
    source = pak.Package('first', len(originals['first']), 'source-identity', tmp_path, (first,))
    retained = {p.name: p.read_bytes() for p in source.cache.iterdir()}
    reads.clear()
    # Identical native plaintext indices can belong to a differently encrypted
    # original. Even with both objects cached, the wrong key remains a refusal.
    with pytest.raises(PreparationFailure) as error:
        pak.Package('second', len(originals['second']), 'new-identity', tmp_path, (first,))
    assert error.value.code == 'archive_parameters_missing'
    assert not (source.cache.parent/'new-identity').exists()
    reads.clear()
    current = pak.Package('second', len(originals['second']), 'new-identity', tmp_path, (second,))
    assert current.verified_parameter == second
    assert [(offset, size) for _, offset, size in reads] == [(512, 512), (128, 16)]
    assert {p.name: p.read_bytes() for p in current.cache.iterdir()} == retained
    assert {p.name: p.read_bytes() for p in source.cache.iterdir()} == retained
    assert current.locations(wanted={'Client/voices/a.wem'}) == {'Client/voices/a.wem': 0}


@pytest.mark.parametrize('invalid', ['corrupt', 'size', 'digest'])
def test_other_package_cache_must_match_exact_native_hash_and_size(tmp_path, monkeypatch, invalid):
    key = bytes(range(32))
    original = encrypted_package(key)
    monkeypatch.setattr(pak, 'block', lambda url, size, pos, count: bytes(original[pos:pos+count]))
    seeded = pak.Package('first', len(original), 'source', tmp_path, (key,))
    paths = list(seeded.cache.iterdir())
    for path in paths:
        data = path.read_bytes()
        if invalid == 'digest':
            path.rename(path.with_name(hashlib.sha1(b'wrong native digest' + data).hexdigest()))
        else:
            path.write_bytes(data + b'x' if invalid == 'size' else bytes([data[0] ^ 1]) + data[1:])
    reads = []
    def ranged(url, total, offset, size):
        reads.append((offset, size)); return bytes(original[offset:offset+size])
    monkeypatch.setattr(pak, 'block', ranged)
    current = pak.Package('second', len(original), 'current', tmp_path, (key,))
    assert len(reads) == 4  # Both original objects were required, beyond footer/key sample.
    assert current.verified_parameter == key
    assert all(hashlib.sha1(p.read_bytes()).hexdigest() == p.name for p in current.cache.iterdir())


def test_reused_index_publication_is_atomic_and_failure_keeps_existing_bytes(tmp_path, monkeypatch):
    from pathlib import Path
    key = bytes(range(32)); original = encrypted_package(key)
    monkeypatch.setattr(pak, 'block', lambda url, total, pos, count: bytes(original[pos:pos+count]))
    source = pak.Package('first', len(original), 'source', tmp_path, (key,))
    # The first object requested by the native footer is the main index.
    magic = original.rfind(pak.MAGIC)
    main_hash = original[magic+24:magic+44].hex()
    target = source.cache.parent/'current'/main_hash
    target.parent.mkdir(); target.write_bytes(b'keep the preexisting incomplete cache')
    before = target.read_bytes(); replace = Path.replace
    def interrupted(path, destination):
        if destination == target:
            assert path.name == 'download' and hashlib.sha1(path.read_bytes()).hexdigest() == main_hash
            raise OSError('Authored atomic-publication interruption')
        return replace(path, destination)
    monkeypatch.setattr(Path, 'replace', interrupted)
    with pytest.raises(OSError, match='atomic-publication'):
        pak.Package('second', len(original), 'current', tmp_path, (key,))
    assert target.read_bytes() == before
    assert list(target.parent.iterdir()) == [target]


def test_initial_seed_outage_reuses_verified_parameters_without_authorizing_candidates(tmp_path, monkeypatch, protected):
    from backend import wuthering_initial_seed as seed
    known, fresh = b'a' * 32, b'b' * 32
    assert metadata.remember_parameter(tmp_path, known)
    monkeypatch.setattr(seed, 'parameters', lambda *a, **k: (fresh,))
    assert release._archive_parameters(tmp_path) == (known, fresh)
    assert metadata.parameters(tmp_path) == (known,)
    def unavailable(*a, **k): raise OSError('Authored source outage')
    monkeypatch.setattr(seed, 'parameters', unavailable)
    assert release._archive_parameters(tmp_path) == (known,)
    with pytest.raises(PreparationFailure) as failure:
        release._archive_parameters(tmp_path / 'empty')
    assert failure.value.code == 'game_metadata_unavailable'


def test_new_validated_key_is_added_atomically_and_existing_host_state_survives_failure(tmp_path, monkeypatch, protected):
    old, new = b'a' * 32, b'b' * 32
    assert metadata.remember_parameter(tmp_path, old)
    path = metadata._path(tmp_path, 'verified-parameters'); retained = path.read_bytes()
    from backend import protected_storage
    def interrupted(*a, **k): raise OSError('Interrupted protected write')
    monkeypatch.setattr(protected_storage, 'private_write', interrupted)
    assert not metadata.remember_parameter(tmp_path, new)
    assert path.read_bytes() == retained and metadata.parameters(tmp_path) == (old,)
    assert not metadata.parameters(tmp_path / 'another-region-cache')


@pytest.mark.parametrize('corrupt', [b'damaged', b'authored-protected-envelope:' + b'{}'[::-1]])
def test_invalid_or_another_host_envelope_cannot_authorize_parameters(tmp_path, protected, corrupt):
    path = metadata._path(tmp_path, 'verified-parameters'); path.parent.mkdir(parents=True)
    path.write_bytes(corrupt)
    assert not metadata.parameters(tmp_path)


def test_pinned_format_survives_a_fresh_reader_and_rejects_changed_source(tmp_path, monkeypatch, protected):
    import base64
    raw = (b'const ENTRY_KEY: &str = "' + base64.b64encode(b'a' * 16)
           + b'"; const ENTRY_IV: &str = "' + base64.b64encode(b'b' * 16) + b'";')
    digest = hashlib.sha256(raw).hexdigest(); monkeypatch.setattr(release, 'FORMAT_SHA', digest)
    monkeypatch.setattr(release, 'download', lambda *a, **k: raw)
    release._format.cache_clear()
    try:
        assert release._format(tmp_path) == (b'a' * 16, b'b' * 16)
        release._format.cache_clear()
        monkeypatch.setattr(release, 'download', lambda *a, **k: pytest.fail('Retained pinned source needs no network'))
        assert release._format(tmp_path) == (b'a' * 16, b'b' * 16)
        assert metadata.format_source(tmp_path, '0' * 64) is None
        assert not metadata.remember_format(tmp_path, raw + b'changed', digest)
        assert metadata.format_source(tmp_path, digest) == raw
    finally:
        release._format.cache_clear()
