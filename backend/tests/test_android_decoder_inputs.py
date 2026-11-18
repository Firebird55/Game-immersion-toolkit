"""Source/receipt tampering must fail before any native compilation or loading."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('android_decoder_builder', ROOT / 'scripts/build-android-data-decoders.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_authenticated_source_never_accepts_extra_changed_or_linked_members(tmp_path):
    archive = tmp_path / 'original.tar.gz'
    with tarfile.open(archive, 'w:gz') as output:
        member = tarfile.TarInfo('original/src/value.c');member.size = 8
        output.addfile(member, io.BytesIO(b'original'))
    policy = {'bytes': archive.stat().st_size, 'sha256': builder.sha(archive), 'root': 'original/src'}
    extracted = tmp_path / 'source'
    assert builder.source_tree(archive, extracted, policy) == extracted / 'original/src'
    extra = extracted / 'extra.c';extra.write_text('substituted')
    with pytest.raises(ValueError, match='Unexpected'): builder.source_tree(archive, extracted, policy)
    extra.unlink();(extracted / 'original/src/value.c').write_text('changed')
    with pytest.raises(ValueError, match='changed'): builder.source_tree(archive, extracted, policy)
    with pytest.raises(ValueError, match='receipt'):
        builder.source_tree(archive, tmp_path / 'other', {**policy, 'sha256': '0' * 64})
    linked = tmp_path / 'linked.tar.gz'
    with tarfile.open(linked, 'w:gz') as output:
        member = tarfile.TarInfo('original/src/link');member.type = tarfile.SYMTYPE;member.linkname = '../outside'
        output.addfile(member)
    with pytest.raises(ValueError, match='Unsafe'):
        builder.source_tree(linked, tmp_path / 'links', {**policy, 'bytes': linked.stat().st_size, 'sha256': builder.sha(linked)})


def test_closed_decoder_bundle_requires_every_exact_notice_and_library(tmp_path):
    policy = json.loads((ROOT / 'packaging/android/native-decoders.json').read_text())
    ndk = json.loads((ROOT / 'packaging/android/python-dependencies.json').read_text())['ndk']
    recipe = {'policy_sha256':builder.sha(ROOT / 'packaging/android/native-decoders.json'),
        'transport_sha256':builder.sha(ROOT / 'packaging/android/app/src/main/cpp/x64_decoder.c'),
        'builder_sha256':builder.sha(ROOT / 'scripts/build-android-data-decoders.py'),
        'source_sha256':policy['capstone']['sha256'],
        'ndk_policy_sha256':hashlib.sha256(builder.canonical(ndk)).hexdigest()}
    libraries, licenses = {}, {}
    for abi in policy['abis']:
        path = tmp_path / 'jniLibs' / abi / policy['library'];path.parent.mkdir(parents=True);path.write_bytes(b'authored-software-input')
        libraries[abi] = {'bytes':path.stat().st_size,'sha256':builder.sha(path),
            'entry':'lib/' + abi + '/' + policy['library'],'minimum_load_alignment':16384}
    for index, name in enumerate(policy['capstone']['licenses']):
        name = 'native-decoder-licenses/' + str(index) + '-' + Path(name).name
        path = tmp_path / 'assets' / name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'authored-license-fixture')
        licenses[name] = {'bytes':path.stat().st_size,'sha256':builder.sha(path)}
    manifest = {'schema':'toolkit-android-native-decoders-v1','recipe':recipe,
        'source_sha256':policy['capstone']['sha256'],'ndk':policy['ndk'],'api':policy['api'],
        'ndk_archive_sha256':ndk['sha256'],'ndk_inventory_sha256':'a' * 64,
        'library':policy['library'],'original_client_execution':False,'libraries':libraries,'licenses':licenses}
    path = tmp_path / 'assets/native-decoder-manifest.json';path.write_bytes(builder.canonical(manifest))
    builder.verify_bundle(tmp_path)
    audit_spec = importlib.util.spec_from_file_location('android_apk_decoder_audit', ROOT / 'scripts/verify-android-apk.py')
    audit = importlib.util.module_from_spec(audit_spec);audit_spec.loader.exec_module(audit)
    manifest.update(version=policy['capstone']['version'], source=policy['capstone']['source'])
    def packaged(changed=None, compression=zipfile.ZIP_STORED):
        selected = json.loads(json.dumps(manifest))
        if changed: changed(selected)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('assets/native-decoder-manifest.json', builder.canonical(selected))
            for name in licenses: archive.writestr('assets/' + name, (tmp_path / 'assets' / name).read_bytes())
            for abi in libraries:
                archive.writestr(libraries[abi]['entry'], (tmp_path / 'jniLibs' / abi / policy['library']).read_bytes(), compress_type=compression)
        return zipfile.ZipFile(io.BytesIO(output.getvalue()))
    native_files = {receipt['entry']: {'sha256':receipt['sha256']} for receipt in libraries.values()}
    with packaged() as archive: audit.verify_decoder(archive, native_files, ROOT)
    for changed in (
        lambda value: value['recipe'].update(builder_sha256='f' * 64),
        lambda value: value.update(ndk_archive_sha256='f' * 64),
        lambda value: value.update(ndk_inventory_sha256='!' * 64),
        lambda value: value.update(version='5.0.6'),
        lambda value: value['licenses'].pop(next(iter(licenses))),
    ):
        with packaged(changed) as archive, pytest.raises(ValueError): audit.verify_decoder(archive, native_files, ROOT)
    with packaged(compression=zipfile.ZIP_DEFLATED) as archive, pytest.raises(ValueError):
        audit.verify_decoder(archive, native_files, ROOT)
    notice = tmp_path / 'assets' / next(iter(licenses));raw = notice.read_bytes();notice.write_bytes(b'changed')
    with pytest.raises(ValueError, match='notice'): builder.verify_bundle(tmp_path)
    notice.write_bytes(raw)
    extra = tmp_path / 'jniLibs/arm64-v8a/unreviewed.so';extra.write_bytes(b'not allowed')
    with pytest.raises(ValueError, match='Unexpected'): builder.verify_bundle(tmp_path)
    extra.unlink()
    library = tmp_path / 'jniLibs/arm64-v8a' / policy['library'];library.write_bytes(b'replaced')
    with pytest.raises(ValueError, match='receipt'): builder.verify_bundle(tmp_path)


def test_every_committed_workflow_build_supplies_authenticated_decoder_inputs():
    invocations = []
    for path in (ROOT / '.github/workflows').glob('*.yml'):
        for line in path.read_text().splitlines():
            if './scripts/build-android-app.ps1 ' in line:
                invocations.append(line)
                assert '-NdkArchive ' in line, path.name
                assert '-PublisherCryptoSourceArchive ' in line, path.name
                assert '-DecoderSourceArchive ' in line or '-DownloadDecoderSource' in line, path.name
    assert invocations, 'The actual hosted APK build must exercise the pinned decoder closure'
