"""Owned synthetic PAK plans and runtime injection; no game data or native tools."""
from dataclasses import replace

import pytest

from backend import wuthering_release_pak as pak
from backend.wuthering_portable_pak import PortablePackage, _missing_oodle
from backend.wuthering_preflight import manifest_upper_bound, selection_plan
from backend.preparation_errors import PreparationFailure
from backend.publisher_crypto import DesktopPublisherCrypto
from backend.tests.test_wuthering_metadata import encrypted_package
from backend.tests.test_wuthering_multiblock import compressed_member


def test_index_plan_has_no_body_io_and_matches_actual_native_ranges():
    package, original = compressed_member(b'Zlib')
    range_reader, calls = package.range, []
    package.range = lambda *args: pytest.fail('Preflight must not read member headers or bodies')
    plan = package.member_plan(0)
    assert plan.plain_bytes == len(original) and plan.compression == 'Zlib'
    def read(offset, count):
        calls.append((offset, count))
        return range_reader(offset, count)
    package.range = read
    assert package.extract(0) == original
    assert calls == list(plan.ranges)
    summary = selection_plan([('owned-package', plan), ('owned-package', plan)],
                             metadata_max_bytes=500, derived_output_max_bytes=1000)
    assert summary['member_count'] == summary['owner_count'] == 1
    assert summary['download_body_max_bytes'] == 500 + sum(count for _, count in calls)
    assert summary['original_plaintext_bytes'] == len(original)
    assert summary['retained_payload_and_derived_max_bytes'] == len(original) + 1000


def test_portable_constructor_uses_only_explicit_range_provider(tmp_path, monkeypatch):
    key = bytes(range(32)); original = encrypted_package(key); calls = []
    monkeypatch.setattr(pak, 'block', lambda *args: pytest.fail('No implicit desktop network'))
    monkeypatch.setattr(pak.subprocess, 'run', lambda *args, **kwargs: pytest.fail('No desktop process'))
    def read(url, size, offset, count):
        assert url == 'owned' and size == len(original)
        calls.append((offset, count))
        return bytes(original[offset:offset+count])
    calls_to_crypto = []

    class HostCrypto:
        def block_cipher(self, algorithm, mode, value, data):
            assert (algorithm, mode, value) == ('AES', 'ECB', key)
            calls_to_crypto.append(len(data))
            return DesktopPublisherCrypto().block_cipher(algorithm, mode, value, data)

    monkeypatch.setattr(pak, 'DesktopPublisherCrypto', lambda: pytest.fail('No implicit desktop cryptography'))
    package = PortablePackage('owned', len(original), 'owned', tmp_path, (key,), range_reader=read,
                              crypto=HostCrypto(), verified_default_parameters=())
    assert calls_to_crypto == [16, calls[2][1], calls[3][1]]
    assert package.verified_parameter == key
    assert package.locations(wanted={'Client/voices/a.wem'}) == {'Client/voices/a.wem': 0}
    before = list(calls)
    assert package.member_plan(0).plain_bytes == 16 and calls == before


@pytest.mark.parametrize('output', ['valid', 'missing', 'short', 'wrong-type'])
def test_portable_oodle_adapter_never_falls_back_to_desktop(monkeypatch, output):
    package, original = compressed_member(b'Oodle')
    provider = package.range
    package.__class__ = PortablePackage
    del package.range
    package.url = 'owned'; package._range_reader = lambda url, size, offset, count: provider(offset, count)
    def decode(blocks):
        assert len(blocks) == 2 and all(frame[:2] == b'\xcc\x06' for frame, _ in blocks)
        if output == 'short': return original[:-1]
        if output == 'wrong-type': return bytearray(original)
        return original
    package.oodle_decoder = _missing_oodle if output == 'missing' else decode
    monkeypatch.setattr(pak, '_oodle', lambda *args: pytest.fail('No implicit desktop codec'))
    monkeypatch.setattr(pak.subprocess, 'run', lambda *args, **kwargs: pytest.fail('No desktop process'))
    if output == 'valid':
        assert package.extract(0) == original
    else:
        with pytest.raises(PreparationFailure if output == 'missing' else ValueError):
            package.extract(0)


@pytest.mark.parametrize('fault', ['negative-position', 'owner-bounds', 'negative-reservation', 'conflicting-owner'])
def test_plans_refuse_unbounded_or_conflicting_metadata(fault):
    package, _ = compressed_member(b'Zlib')
    plan = package.member_plan(0)
    with pytest.raises(ValueError):
        if fault == 'negative-position': package.member_plan(-1)
        elif fault == 'owner-bounds': replace(plan, owner_bytes=plan.offset + plan.header_bytes)
        elif fault == 'negative-reservation': selection_plan([('a', plan)], metadata_max_bytes=-1, derived_output_max_bytes=0)
        else:
            other = replace(plan, owner_bytes=plan.owner_bytes+1)
            selection_plan([('a', plan), ('a', other)], metadata_max_bytes=0, derived_output_max_bytes=0)


def test_duplicate_compression_names_keep_exact_native_method_index():
    package, original = compressed_member(b'Zlib')
    package.methods = [b'Zlib', b'Zlib']
    assert package.member_plan(0).compression_index == 1
    assert package.extract(0) == original


def test_manifest_ceiling_uses_selected_channels_without_claiming_installed_size():
    snapshot = {'root': 'https://original.invalid/zip',
                'base': {'base.pak': [1024, 'a' * 32]},
                'products': {'resource/BaseFiles/text.pak': ['https://original.invalid/text.pak', 500, 'b' * 40],
                             'ja/BaseFiles/audio.pak': ['https://original.invalid/ja.pak', 900, 'c' * 40],
                             'en/BaseFiles/audio.pak': ['https://original.invalid/en.pak', 700, 'd' * 40]}}
    result = manifest_upper_bound(snapshot, ('resource', 'ja'))
    assert result['owner_count'] == 3 and result['all_selected_archive_bytes'] == 2424
    assert result['installed_disk_size_known'] is False
    snapshot['products']['ja/PatchFiles/audio.pak'] = ['https://original.invalid/ja.pak', 900, 'c' * 40]
    assert manifest_upper_bound(snapshot, ('resource', 'ja')) == result
    snapshot['products']['ja/PatchFiles/audio.pak'][1] += 1
    with pytest.raises(ValueError, match='Conflicting'):
        manifest_upper_bound(snapshot, ('resource', 'ja'))
