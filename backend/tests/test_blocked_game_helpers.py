"""Build-only source quarantine failures not exercised by frozen refusals.

All archives/notices below are authored. No upstream constant or game is read.
"""
import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import zipfile

import pytest
from backend.runtime_bundle import RuntimeBundleError


def module(name):
    path = Path(__file__).resolve().parents[2] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location('fixture_' + name.replace('-', '_'), path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize('name,mode', [('../escape.cs', 0), ('same.cs', stat.S_IFLNK | 0o777)])
def test_source_archive_rejects_escapes_and_links_before_preparation(tmp_path, name, mode):
    prepare = module('prepare-blocked-game-helper')
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        info = zipfile.ZipInfo(name); info.external_attr = mode << 16
        zipped.writestr(info, b'owned source fixture')
    with pytest.raises((ValueError, RuntimeBundleError)):
        list(prepare.archive_members(archive))


def test_failed_or_changed_download_does_not_overwrite_a_private_input(tmp_path, monkeypatch):
    prepare = module('prepare-blocked-game-helper')
    target = tmp_path / 'private-source.cs'
    monkeypatch.setattr(prepare.urllib.request, 'urlopen', lambda *_a, **_k: io.BytesIO(b'wrong owned bytes'))
    with pytest.raises(ValueError, match='checksum'):
        prepare.acquire('https://example.test/owned', target, '0' * 64)
    assert not target.exists()
    target.write_bytes(b'preserved private fixture')
    with pytest.raises(ValueError, match='Existing build input differs'):
        prepare.acquire('https://example.test/owned', target, '0' * 64)
    assert target.read_bytes() == b'preserved private fixture'


def test_unknown_helper_kind_cannot_create_a_quarantine_root(tmp_path):
    prepare = module('prepare-blocked-game-helper')
    with pytest.raises(ValueError, match='Unknown'):
        prepare.prepare('../escape', tmp_path / 'private')
    assert list(tmp_path.iterdir()) == []


def test_authored_pak_has_independent_selected_bytes_and_bounded_adversarial_header(tmp_path):
    # The compiled helper must actually select this row; a startup-only pass or
    # silently extracting everything cannot satisfy the Windows probe.
    fixtures = module('game-helper-fixtures')
    root = tmp_path / 'authored'; fixtures.fixture(root)
    assert (root / 'owned.pak').read_bytes()[:4] == b'KPKA'
    assert hashlib.sha256(bytes(range(256))).hexdigest() == '40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880'
    assert fixtures.murmur32(b'', 0) == 0
    assert fixtures.murmur32(b'foo', 0) == 0xf6a5c420
    assert (root / 'oversized.pak').stat().st_size == 16
    with pytest.raises(ValueError, match='new owned'):
        fixtures.fixture(root)
