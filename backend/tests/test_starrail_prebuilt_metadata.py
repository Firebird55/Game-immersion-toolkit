"""Compiler-free metadata closure and GPL corresponding-source regressions."""
import io
import json
from pathlib import Path
import zipfile

import pytest

from backend import prebuilt_readers as readers
from backend.preparation_errors import PreparationFailure
from backend.tests.test_prebuilt_readers import digest, helper_fixture, save


def starrail_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(readers, 'host_platform', lambda: 'win-x64')
    layout, home, manifest = helper_fixture(tmp_path, 'starrail')
    content = {'Iced.dll': b'authored managed decoder fixture',
        'corresponding-source/hsr-metadata-source.zip': b'authored GPL source fixture',
        'corresponding-source/iced-source.zip': b'authored MIT source fixture',
        'notices/HSRGlobalMetadata-LICENSE.txt': b'authored GPL notice fixture',
        'notices/Iced-LICENSE.txt': b'authored MIT notice fixture'}
    pins = dict(zip(readers.STARRAIL_SOFTWARE, map(digest, (
        content['corresponding-source/hsr-metadata-source.zip'], content['corresponding-source/iced-source.zip'],
        b'authored decoder package fixture', content['Iced.dll']))))
    monkeypatch.setattr(readers, 'STARRAIL_SOFTWARE', pins)
    monkeypatch.setattr(readers, 'STARRAIL_NOTICES', {n: digest(content[n]) for n in readers.STARRAIL_NOTICES})
    source = b'authored exact corresponding source fixture'
    policy = json.dumps({'metadata': {'sha256': pins['metadata_source_sha256'], 'files': {'Reader.cs': digest(source)}}}).encode()
    manifest['source_inputs'] = {name: digest(policy if name == 'packaging/starrail-reader/inputs.json' else source)
                               for name in readers._source_names('starrail')}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name in manifest['source_inputs']:
            archive.writestr(name, policy if name == 'packaging/starrail-reader/inputs.json' else source)
    content['corresponding-source/owned-source.zip'] = output.getvalue()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('LICENSE', content['notices/HSRGlobalMetadata-LICENSE.txt'])
        archive.writestr('HSRGlobalMetadata/Reader.cs', source)
    content['corresponding-source/hsr-metadata-source.zip'] = output.getvalue()
    receipt = json.loads((home / 'build-receipt.json').read_text())
    receipt['source_inputs'] = manifest['source_inputs']
    receipt['software_inputs'] = pins
    content['build-receipt.json'] = json.dumps(receipt).encode()
    for name, data in content.items():
        path = home / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        manifest['files'][name] = {'bytes': len(data), 'sha256': digest(data)}
    manifest['software_inputs'] = pins
    manifest['purpose'] = 'original-metadata-data-only'
    return save(layout, home, manifest), home, manifest


def test_star_rail_only_authorizes_bounded_data_operations(tmp_path, monkeypatch):
    layout, home, _ = starrail_fixture(tmp_path, monkeypatch)
    helper = readers.prebuilt_reader('starrail', layout=layout)
    private = tmp_path.resolve()
    assert helper.original_metadata_command('metadata', private / 'inputs', private / 'new') == [
        str(home / 'StarRailMetadata.exe'), 'metadata', str(private / 'inputs'), str(private / 'new')]
    assert helper.original_metadata_command('disassemble', private / 'input', private / 'request', private / 'output')[1] == 'disassemble'
    assert helper.original_metadata_command('native-graph', private / 'input', private / 'request', private / 'output')[1] == 'native-graph'
    for operation, paths in [('execute', [private]), ('metadata', [private]), ('metadata', [Path('relative'), private])]:
        with pytest.raises(PreparationFailure):
            helper.original_metadata_command(operation, *paths)
    with pytest.raises(PreparationFailure):
        helper.command(['metadata'])
    with pytest.raises(PreparationFailure):
        helper.runtime_identity_command()


@pytest.mark.parametrize('change', ['source-byte', 'missing-source', 'new-decoder', 'changed-license', 'receipt-only', 'duplicate-source'])
def test_rehashed_outer_manifest_cannot_change_frozen_software_or_corresponding_source(tmp_path, monkeypatch, change):
    layout, home, manifest = starrail_fixture(tmp_path, monkeypatch)
    name = {'new-decoder': 'Iced.dll', 'changed-license': 'notices/Iced-LICENSE.txt',
            'receipt-only': 'build-receipt.json'}.get(change, 'corresponding-source/owned-source.zip')
    path = home / name
    if change == 'receipt-only':
        receipt = json.loads(path.read_text()); receipt['software_inputs'] = {}; data = json.dumps(receipt).encode()
    elif change in {'new-decoder', 'changed-license'}:
        data = b'changed frozen software input'
    else:
        with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
            originals = [(item.filename, archive.read(item)) for item in archive.infolist()]
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for i, (member, source) in enumerate(originals):
                if change == 'missing-source' and i == 0:
                    continue
                archive.writestr(member, b'changed source' if change == 'source-byte' and i == 0 else source)
            if change == 'duplicate-source':
                with pytest.warns(UserWarning):
                    archive.writestr(member, source)
        data = output.getvalue()
    path.write_bytes(data); manifest['files'][name] = {'bytes': len(data), 'sha256': digest(data)}
    layout = save(layout, home, manifest)
    with pytest.raises(PreparationFailure):
        readers.prebuilt_reader('starrail', layout=layout)


def test_star_rail_delivery_pins_match_build_source_policy():
    pins = json.loads(Path('packaging/starrail-reader/inputs.json').read_text())
    assert readers.STARRAIL_SOFTWARE == {
        'metadata_source_sha256': pins['metadata']['sha256'], 'decoder_source_sha256': pins['decoder']['sha256'],
        'decoder_package_sha256': pins['decoder']['package']['sha256'],
        'decoder_assembly_sha256': pins['decoder']['package']['dll_sha256']}
    assert readers.STARRAIL_NOTICES['notices/HSRGlobalMetadata-LICENSE.txt'] == pins['metadata']['license_sha256']
    assert readers.STARRAIL_NOTICES['notices/Iced-LICENSE.txt'] == pins['decoder']['package']['license_sha256']
