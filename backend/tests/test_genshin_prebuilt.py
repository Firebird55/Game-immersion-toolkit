"""Compiler-free original containers ship generic software and complete notices."""
import json
from pathlib import Path

import pytest

from backend import prebuilt_readers as readers
from backend.preparation_errors import PreparationFailure
from backend.tests.test_prebuilt_readers import digest, helper_fixture, save


def fixture(tmp_path, monkeypatch, platform='win-x64'):
    monkeypatch.setattr(readers, 'host_platform', lambda: platform)
    layout, home, manifest = helper_fixture(tmp_path, 'genshin', platform)
    source, notice = b'authored generic codec software fixture', b'authored complete MIT notice fixture'
    pins = {'software_sha256': digest(source), 'license_sha256': digest(notice)}
    monkeypatch.setattr(readers, 'GENSHIN_SOFTWARE', pins)
    manifest['source_inputs']['packaging/genshin-reader/upstream/BlbUtils.cs'] = digest(source)
    manifest['source_inputs']['packaging/genshin-reader/AnimeStudio-LICENSE.txt'] = digest(notice)
    receipt = json.loads((home / 'build-receipt.json').read_text())
    receipt['source_inputs'] = manifest['source_inputs']; receipt['software_inputs'] = pins
    content = {'build-receipt.json': json.dumps(receipt).encode(), 'notices/AnimeStudio-LICENSE.txt': notice}
    for name, data in content.items():
        (home / name).write_bytes(data)
        manifest['files'][name] = {'bytes': len(data), 'sha256': digest(data)}
    manifest['purpose'] = 'original-container-data-only'; manifest['software_inputs'] = pins
    return save(layout, home, manifest), home, manifest


@pytest.mark.parametrize('platform', ['win-x64', 'linux-x64', 'darwin-arm64'])
def test_frozen_genshin_helper_only_authorizes_bounded_private_file_data(tmp_path, monkeypatch, platform):
    layout, home, _ = fixture(tmp_path, monkeypatch, platform)
    helper = readers.prebuilt_reader('genshin', layout=layout)
    private = tmp_path.resolve()
    assert helper.original_container_command(private / 'input', private / 'parameters', private / 'output')[1] == 'decode'
    for paths in [(private / 'input', private / 'parameters', private / 'input'), (Path('relative'), private / 'p', private / 'o')]:
        with pytest.raises(PreparationFailure): helper.original_container_command(*paths)
    with pytest.raises(PreparationFailure): helper.command(['decode'])
    with pytest.raises(PreparationFailure): helper.original_metadata_command('metadata', private / 'i', private / 'o')


@pytest.mark.parametrize('change', ['notice', 'source', 'receipt', 'private-parameters'])
def test_rehashed_outer_manifest_cannot_replace_software_notices_or_embed_parameters(tmp_path, monkeypatch, change):
    layout, home, manifest = fixture(tmp_path, monkeypatch)
    if change == 'source':
        manifest['source_inputs']['packaging/genshin-reader/upstream/BlbUtils.cs'] = '9' * 64
    else:
        name = {'notice': 'notices/AnimeStudio-LICENSE.txt', 'receipt': 'build-receipt.json',
                'private-parameters': 'private/codec.json'}[change]
        data = b'changed fixture data'
        if change == 'receipt':
            value = json.loads((home / name).read_text()); value['software_inputs'] = {}; data = json.dumps(value).encode()
        path = home / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        manifest['files'][name] = {'bytes': len(data), 'sha256': digest(data)}
    layout = save(layout, home, manifest)
    with pytest.raises(PreparationFailure): readers.prebuilt_reader('genshin', layout=layout)


def test_frozen_software_and_full_license_match_the_reviewed_source_inputs():
    policy = json.loads(Path('packaging/genshin-reader/inputs.json').read_text())
    assert readers.GENSHIN_SOFTWARE == {'software_sha256': policy['software']['sha256'], 'license_sha256': policy['license']['sha256']}
    assert digest(Path('packaging/genshin-reader/upstream/BlbUtils.cs').read_bytes()) == policy['software']['sha256']
    assert digest(Path('packaging/genshin-reader/AnimeStudio-LICENSE.txt').read_bytes()) == policy['license']['sha256']
