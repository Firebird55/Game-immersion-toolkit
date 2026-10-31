"""Acceptance evidence must follow actual suppliers and immutable payloads."""
import base64
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('desktop_input_review', Path(__file__).resolve().parents[2] / 'scripts/review-desktop-inputs.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def wheel(path, *, tamper=False, vendor=False):
    files = {'fixture/__init__.py': b'VALUE = 1\n',
        'fixture/native.dll': b'MZ\0\0authored supplier',
        'fixture-1.0.dist-info/METADATA': b'Name: fixture\nVersion: 1.0\nLicense-Expression: MIT\n',
        'fixture-1.0.dist-info/licenses/LICENCE': b'Authored complete permission and copyright fixture.'}
    if vendor:
        files['fixture/vendor/other-1.0.dist-info/METADATA'] = b'Name: other\nVersion: 1.0\n'
        files['fixture/vendor/other-1.0.dist-info/RECORD'] = b'Nested inert metadata'
    record = io.StringIO()
    writer = csv.writer(record, lineterminator='\n')
    for name, data in files.items():
        writer.writerow([name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='), len(data)])
    writer.writerow(['fixture-1.0.dist-info/RECORD', '', ''])
    files['fixture-1.0.dist-info/RECORD'] = record.getvalue().encode()
    if tamper:
        files['fixture/native.dll'] = b'MZ\0\0changed supplier!'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return files


def runtime(tmp_path, files, **receipt):
    root = tmp_path / 'runtime'
    root.mkdir()
    inventory = []
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        inventory.append({'path': name, 'bytes': len(data), 'sha256': review.sha(data)})
    return review.Review(root, {'files': inventory, **receipt}, 'windows-x64')


def test_actual_record_and_nested_vendor_metadata(tmp_path):
    path = tmp_path / 'fixture.whl'
    files = wheel(path, vendor=True)
    evidence = review.wheel_evidence(path)
    assert evidence['name'] == 'fixture'
    assert evidence['files']['fixture/native.dll'] == review.sha(files['fixture/native.dll'])
    assert 'fixture-1.0.dist-info/licenses/LICENCE' in evidence['notices']


def test_tampered_record_fails_even_with_valid_metadata(tmp_path):
    path = tmp_path / 'fixture.whl'
    wheel(path, tamper=True)
    with pytest.raises(ValueError, match='RECORD'):
        review.wheel_evidence(path)


def test_empty_component_list_cannot_certify_wheels(tmp_path):
    value = runtime(tmp_path, {}, components=[])
    with pytest.raises(ValueError, match='component list'):
        value.wheelhouse(tmp_path)


def test_target_lock_markers_and_omitted_dependency(tmp_path):
    value = runtime(tmp_path, {}, components=[{'name': 'fixture', 'version': '1.0'}, {'name': 'windows-only', 'version': '2.0'}])
    snapshot = SimpleNamespace(files={'requirements.lock.txt': b"fixture==1.0\nwindows-only==2.0; sys_platform == 'win32'\nlinux-only==3.0; sys_platform == 'linux'\n",
                                    'packaging/desktop/build-requirements.lock.txt': b'# no extra\n'})
    value.locked_components(snapshot)
    value.receipt['components'].pop()
    with pytest.raises(ValueError, match='source locks'):
        value.locked_components(snapshot)


def test_full_notice_required_and_supplier_native_bytes_matched(tmp_path):
    path = tmp_path / 'fixture.whl'
    files = wheel(path)
    component = {'name': 'fixture', 'version': '1.0', 'artifact_sha256': review.digest(path)}
    value = runtime(tmp_path, {'_internal/native.dll': files['fixture/native.dll']}, components=[component])
    value.wheelhouse(tmp_path)
    value.native_inventory()
    assert value.checks['complete_notices']['blockers'][0]['code'] == 'wheel-notices'
    assert not value.checks['native_inputs']['blockers']
    assert value.native_files[0]['origins']


def test_licence_directory_does_not_make_runtime_code_a_notice():
    assert review.notice_member('fixture.dist-info/licenses/AUTHORS')
    assert review.notice_member('vendor/COPYING')
    assert not review.notice_member('packaging/licenses/_spdx.py')


def test_source_eol_equivalence_does_not_accept_source_edits():
    assert review.source_matches(b'line\n', review.sha(b'line\r\n'), 'LICENSE.txt')
    assert not review.source_matches(b'line\n', review.sha(b'other\r\n'), 'LICENSE.txt')
    assert not review.source_matches(b'\0line\n', review.sha(b'\0line\r\n'), 'binary')


@pytest.mark.parametrize('field', ['build_id', 'helpers', 'python_version'])
def test_observation_metadata_is_bound_but_source_mismatch_reported(field):
    inputs = {'owned.py': review.sha(b'changed')}
    receipt = {'source_commit': 'a' * 40, 'build_id': 'fixture',
        'source_inputs_sha256': review.sha(json.dumps(inputs, sort_keys=True).encode())}
    observed = {**receipt, 'schema': 'proxy-desktop-observed-build-v1', 'source_inputs': inputs}
    assert review.verify_observation(receipt, observed, SimpleNamespace(files={'owned.py': b'original'})) == ['owned.py']
    with pytest.raises(ValueError, match=field):
        review.verify_observation(receipt, {**observed, field: 'forged'}, SimpleNamespace(files={}))


def test_source_archive_missing_blocks_notices_and_source(tmp_path):
    value = runtime(tmp_path, {})
    pins = {'components': [{'name': 'fixture', 'archive': 'fixture.tar.gz', 'sha256': '0' * 64}]}
    value.collection(pins, 'native', {'fixture'})
    assert value.checks['complete_notices']['blockers']
    assert value.checks['corresponding_sources']['blockers']


def test_audio_recipe_cannot_certify_neighboring_prebuilt_windows_dll(tmp_path):
    recipe = b'# owned recipe\n'
    source = b'pinned source archive fixture'
    files = {'_internal/codecs/audio/sources/build-audio-runtime.py': recipe,
        '_internal/codecs/audio/sources/ffmpeg.tar.gz': source,
        '_internal/codecs/audio/ffmpeg.exe': b'MZ\0\0owned ffmpeg',
        '_internal/codecs/audio/vgmstream-cli.exe': b'MZ\0\0supplier vgmstream'}
    value = runtime(tmp_path, files)
    value.receipt['native_resources'] = [{'files': [{**entry, 'path': entry['path'].removeprefix('_internal/')} for entry in value.inventory.values()],
        'build_recipe_sha256': review.sha(recipe),
        'components': [{'name': 'ffmpeg', 'archive': 'ffmpeg.tar.gz', 'sha256': review.sha(source)},
                       {'name': 'lame', 'archive': 'ffmpeg.tar.gz', 'sha256': review.sha(source)}]}]
    pins = {name: {'archive': 'ffmpeg.tar.gz', 'sha256': review.sha(source)} for name in ('ffmpeg', 'lame')}
    value.resources(SimpleNamespace(files={'scripts/build-audio-runtime.py': recipe,
        'packaging/codecs/audio-runtime.json': json.dumps(pins).encode()}))
    value.native_inventory()
    assert value.native_files[0]['origins']
    assert value.checks['native_inputs']['blockers'][0]['files'] == ['_internal/codecs/audio/vgmstream-cli.exe']


def test_unpinned_archive_cannot_supply_native_identity(tmp_path):
    path = tmp_path / 'supplier.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('native.dll', b'MZ\0\0supplier')
    value = runtime(tmp_path, {})
    with pytest.raises(ValueError, match='not pinned'):
        value.native_archives([path], set())
    value.native_archives([path], {review.digest(path)})
    assert review.sha(b'MZ\0\0supplier') in value.origins


def test_signed_nuget_sha512_pin_supports_real_member_identity(tmp_path):
    path = tmp_path / 'supplier.nupkg'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('runtime/native.dll', b'MZ\0\0supplier')
    value = runtime(tmp_path, {})
    trusted = base64.b64encode(hashlib.sha512(path.read_bytes()).digest()).decode()
    value.native_archives([path], {trusted})
    assert review.sha(b'MZ\0\0supplier') in value.origins


def test_inventory_digest_uses_exact_paths_and_directory_graph():
    first = {'files': [{'path': 'one', 'sha256': '0' * 64}], 'directories': []}
    assert review.inventory_digest(first) != review.inventory_digest({**first, 'directories': ['empty']})
