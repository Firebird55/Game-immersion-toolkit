"""Official metadata planning/retention without publisher code or live network."""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import struct
from xml.etree import ElementTree as E
from zipfile import ZIP_STORED, ZipFile
import zlib

import pytest
from Crypto.Cipher import AES

from backend import nte_updater_source as source
from backend.tests.test_nte_original_updater import authored_sdk


def packed(name, data):
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        archive.writestr(name, data)
    return output.getvalue()


class Originals:
    def __init__(self, version='1.2.3.4', sdk=None):
        self.version, self.requests = version, []
        self.base = source.VERSION_URL.rsplit('/', 1)[0]
        self.product = version + '_1'
        self.manifest_url = self.base + '/' + self.product + '/AllFiles.xml'
        self.version_body = ('[VERSION]\nVersion='+version+'\nFileListURL='+self.manifest_url+'\n').encode()
        self.root = E.Element('All_Files')
        E.SubElement(self.root, 'ProductVersion', Version=self.product)
        E.SubElement(self.root, 'Url', BaseUrl=self.base)
        configuration = json.dumps({'appId': 'authored-demo',
            'gameResUrl': ['https://ntecdn1.perfectworld.com/clientRes'], 'branchName': 'PC_100'}).encode()
        self.bodies = {}
        self.add('/PatcherSDK_x64.dll', sdk or authored_sdk())
        self.add('/ResFilesM/123/PatcherConfig/PatcherConfig.json', configuration)

    def add(self, path, body):
        archive = packed(path.rsplit('/', 1)[1], body)
        self.bodies[self.base+'/'+self.product+path+'.zip'] = archive
        E.SubElement(self.root, 'File', Path=path, Size=str(len(body)), Checksum=hashlib.md5(body).hexdigest(),
                     ZipSize=str(len(archive)), ZipChecksum=hashlib.md5(archive).hexdigest())

    def fetch(self, url, *, limit):
        self.requests.append(url)
        if url == source.VERSION_URL: result = self.version_body
        elif url == self.manifest_url: result = E.tostring(self.root)
        else: result = self.bodies[url]
        assert len(result) <= limit
        return result


def test_plan_exposes_exact_sdk_cost_before_any_payload_and_cached_resolve_never_downloads_keys(tmp_path):
    original = Originals()
    plan = source.plan(fetch=original.fetch)
    assert original.requests == [source.VERSION_URL, original.manifest_url]
    assert plan.costs(tmp_path) == {'compressed_bytes': sum(len(value) for value in original.bodies.values()),
        'decoded_bytes': sum(item.size for item in plan.artifacts), 'cached_compressed_bytes': 0, 'audio_bytes': 0}
    candidate = source.resolve(plan, tmp_path, fetch=original.fetch)
    assert candidate.key == (b'authored-demofixture!')[:16]
    assert plan.costs(tmp_path)['compressed_bytes'] == 0
    def forbidden(*args, **kwargs): raise AssertionError('Retained source attempted a network/key lookup')
    assert source.resolve(plan, tmp_path, fetch=forbidden) == candidate
    source.recheck(plan, fetch=original.fetch)


def test_source_pointer_change_keeps_prior_inputs_and_rejects_stale_activation(tmp_path):
    old, new = Originals(), Originals('1.2.3.5', authored_sdk().replace(b'fixture!', b'changed!'))
    plan = source.plan(fetch=old.fetch)
    previous = source.resolve(plan, tmp_path, fetch=old.fetch)
    before = {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    with pytest.raises(ValueError): source.recheck(plan, fetch=new.fetch)
    assert before == {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    def forbidden(*args, **kwargs): raise AssertionError('Historical inputs queried latest')
    assert source.resolve(plan, tmp_path, fetch=forbidden) == previous


def test_interrupted_new_artifact_publication_does_not_remove_completed_prior_inputs(tmp_path, monkeypatch):
    old, new = Originals(), Originals('1.2.3.5', authored_sdk().replace(b'fixture!', b'changed!'))
    before = source.plan(fetch=old.fetch)
    completed = source.resolve(before, tmp_path, fetch=old.fetch)
    later = source.plan(fetch=new.fetch)
    original_replace = Path.replace
    def interrupted(path, target):
        if path.name == 'receipt.json': raise OSError('Simulated interrupted publication')
        return original_replace(path, target)
    monkeypatch.setattr(Path, 'replace', interrupted)
    with pytest.raises(OSError): source.resolve(later, tmp_path, fetch=new.fetch)
    monkeypatch.setattr(Path, 'replace', original_replace)
    assert source.resolve(before, tmp_path, fetch=lambda *_a, **_k: pytest.fail('Old source download')) == completed
    assert any(source.retained(tmp_path, item) is None for item in later.artifacts)
    repaired = source.resolve(later, tmp_path, fetch=new.fetch)
    assert repaired.key != completed.key


def test_wrong_source_receipt_or_payload_cannot_be_reused_as_a_completed_input(tmp_path):
    original = Originals(); plan = source.plan(fetch=original.fetch)
    source.resolve(plan, tmp_path, fetch=original.fetch)
    item = next(row for row in plan.artifacts if row.role == 'sdk')
    receipt = tmp_path/'original-updater/artifacts'/item.identity/'receipt.json'
    body = json.loads(receipt.read_bytes()); body['artifact']['member'] = 'Another.dll'
    receipt.write_text(json.dumps(body), encoding='utf-8')
    assert source.retained(tmp_path, item) is None
    assert plan.costs(tmp_path)['compressed_bytes'] == item.packed_size
    def forbidden(*args, **kwargs):
        raise AssertionError('Repair requires original acquisition')
    with pytest.raises(AssertionError):
        source.resolve(plan, tmp_path, fetch=forbidden)


@pytest.mark.parametrize('change', ['wrong-host', 'wrong-version', 'duplicate-sdk', 'unsafe-path', 'oversized-sdk'])
def test_original_manifest_rejects_ambiguous_or_unowned_native_inputs(change):
    original = Originals()
    if change == 'wrong-host': original.version_body = original.version_body.replace(b'ntecdn1.perfectworld.com', b'example.invalid')
    elif change == 'wrong-version': original.root.find('ProductVersion').set('Version', '9.9.9.9_1')
    elif change == 'duplicate-sdk': original.add('/PatcherSDK_x64.dll', authored_sdk())
    elif change == 'unsafe-path': original.root.findall('File')[0].set('Path', '/../PatcherSDK_x64.dll')
    else: original.root.findall('File')[0].set('Size', str(source.MAX_PAYLOAD + 1))
    with pytest.raises(ValueError): source.plan(fetch=original.fetch)
    assert not any(url.endswith('.zip') for url in original.requests)


def test_declared_zip_checksum_is_checked_before_unpacking_any_member(tmp_path):
    original = Originals(); plan = source.plan(fetch=original.fetch)
    item = next(row for row in plan.artifacts if row.role == 'sdk')
    corrupted = bytearray(original.bodies[item.url]); corrupted[-1] ^= 1
    original.bodies[item.url] = bytes(corrupted)
    with pytest.raises(ValueError): source.acquire(tmp_path, item, fetch=original.fetch)
    assert source.retained(tmp_path, item) is None


def test_original_member_crc_is_enforced_even_when_transport_checksum_matches(tmp_path):
    original = Originals(); plan = source.plan(fetch=original.fetch)
    item = next(row for row in plan.artifacts if row.role == 'sdk')
    raw = bytearray(original.bodies[item.url])
    raw[30 + len(item.member) + 3] ^= 1
    original.bodies[item.url] = bytes(raw)
    advertised = replace(item, packed_md5=hashlib.md5(raw).hexdigest())
    with pytest.raises(ValueError): source.acquire(tmp_path, advertised, fetch=original.fetch)
    assert source.retained(tmp_path, advertised) is None


def resource_manifest():
    xml = (b'<ResList version="1.2.3" tag="baseTag"><Res filename="Client/WindowsNoEditor/HT/Content/test.pak" '
           b'filesize="5" md5="0123456789abcdef0123456789abcdef"/></ResList>')
    raw = zlib.compress(xml)
    padding = 16 - len(raw) % 16
    # Deliberately authored material, unrelated to any actual publisher key.
    body = AES.new(b'authored-demofix', AES.MODE_CBC, b'fixture-iv000000').encrypt(raw + bytes([padding]) * padding)
    return packed('ResList.bin', b'PatcherXML0\0' + struct.pack('<I', len(xml)) + body), hashlib.md5(xml).hexdigest()


def test_background_bootstrap_failure_reports_planned_bytes_without_acquiring_a_payload(tmp_path):
    original = Originals(); plan = source.plan(fetch=original.fetch)
    with pytest.raises(source.BootstrapRequired) as rejected:
        source.resolve_retained(plan, tmp_path)
    assert rejected.value.code == 'bootstrap_required' and rejected.value.previous_snapshot_retained
    assert rejected.value.costs['compressed_bytes'] == plan.costs(tmp_path)['compressed_bytes']
    assert original.requests == [source.VERSION_URL, original.manifest_url]


def test_normal_official_manifest_route_does_not_fall_back_to_external_keys_on_bootstrap_miss(tmp_path, monkeypatch):
    from backend import nte_community_metadata as community, nte_release as release
    original = Originals()
    monkeypatch.setattr(release, 'download', original.fetch)
    def forbidden(*args, **kwargs): raise AssertionError('Official bootstrap was replaced by a community key')
    monkeypatch.setattr(release, '_parameters', forbidden)
    monkeypatch.setattr(community, 'download', forbidden)
    archive, checksum = resource_manifest()
    with pytest.raises(source.BootstrapRequired):
        release._manifest(archive, 'nte-global', 'PC_100', '1.2.3', {'baseTag': '1.2.3'}, checksum,
            tmp_path/'community', {}, official_cache=tmp_path/'official', allow_community_fallback=True)
    assert not any(url.endswith('.zip') for url in original.requests)


def test_complete_original_manifest_approval_and_historical_reopen_do_not_query_latest(tmp_path, monkeypatch):
    original = Originals(); plan = source.plan(fetch=original.fetch)
    source.resolve(plan, tmp_path, fetch=original.fetch)
    archive, checksum = resource_manifest()
    result, reference = source.approve(plan, tmp_path, archive, 'nte-global', 'PC_100', '1.2.3',
                                      {'baseTag': '1.2.3'}, checksum, fetch=original.fetch)
    assert len(result[0]) == 1
    def forbidden(*args, **kwargs): raise AssertionError('Historical receipt consulted latest data')
    monkeypatch.setattr(source, 'download', forbidden)
    receipt = source.check_reference(reference, tmp_path, result=result)
    assert receipt['declared_xml_md5'] == checksum
    assert source.parameters_for_reference(reference, tmp_path)[0] == b'authored-demofix'
    path = tmp_path/'original-updater/approvals'/(reference['proof_sha256']+'.json')
    saved = path.read_bytes(); path.unlink()
    with pytest.raises(ValueError): source.check_reference(reference, tmp_path)
    path.write_bytes(saved)
    assert source.check_reference(reference, tmp_path) == receipt


def test_wrong_original_checksum_or_source_switch_never_publishes_an_approval(tmp_path):
    original = Originals(); plan = source.plan(fetch=original.fetch)
    source.resolve(plan, tmp_path, fetch=original.fetch)
    archive, checksum = resource_manifest()
    for bad_checksum, fetch in [('0'*32, original.fetch), (checksum, Originals('1.2.3.5').fetch)]:
        with pytest.raises(ValueError):
            source.approve(plan, tmp_path, archive, 'nte-global', 'PC_100', '1.2.3',
                           {'baseTag': '1.2.3'}, bad_checksum, fetch=fetch)
        assert not list((tmp_path/'original-updater/approvals').glob('*.json'))


def test_original_configuration_cannot_approve_another_game_branch(tmp_path):
    original = Originals(); plan = source.plan(fetch=original.fetch)
    source.resolve(plan, tmp_path, fetch=original.fetch)
    archive, checksum = resource_manifest()
    with pytest.raises(ValueError):
        source.approve(plan, tmp_path, archive, 'nte-global', 'PC_101', '1.2.3',
                       {'baseTag': '1.2.3'}, checksum, fetch=original.fetch)
    assert not list((tmp_path/'original-updater/approvals').glob('*.json'))


def test_activation_recheck_compares_the_exact_original_updater_approval(tmp_path, monkeypatch):
    from backend import nte_publisher as publisher, nte_metadata_profile as profiles
    reference = {'kind': source.APPROVAL, 'proof_sha256': 'a'*64}
    value = {'region': 'nte-global', 'branch': 'PC_100', 'version': '1.2.3',
             'files': {}, 'sections': {}, 'publisher_files': {}, 'original_updater': reference,
             '_materialized': {'profile': {}, 'header': {}}}
    observed = {key: item for key, item in value.items() if key != '_materialized'}
    monkeypatch.setattr(publisher, 'snapshot', lambda *_: value)
    monkeypatch.setattr(profiles, 'validate_payload', lambda *_: None)
    monkeypatch.setattr(publisher, '_discovery', lambda *_a, **_k: observed)
    publisher.validate_prepared(tmp_path, {'publisher_snapshot': 'owned-complete'}, recheck=True)
    observed['original_updater'] = {**reference, 'proof_sha256': 'b'*64}
    with pytest.raises(ValueError, match='changed'):
        publisher.validate_prepared(tmp_path, {'publisher_snapshot': 'owned-complete'}, recheck=True)


def test_context_owned_discovery_never_uses_global_download_or_parameter_hooks(tmp_path, monkeypatch):
    import base64
    from backend import nte_release as release
    original = Originals(); plan = source.plan(fetch=original.fetch)
    source.resolve(plan, tmp_path, fetch=original.fetch)
    archive, checksum = resource_manifest()
    entry = 'https://ntecdn1.perfectworld.com/clientRes/publish_PC/Version/Windows/config.xml'
    root = 'https://ntecdn1.perfectworld.com/clientRes/PC_100/Version/Windows'
    pointer = base64.b64encode(json.dumps({'branchName': 'PC_100'}).encode()).decode()
    cfg = ('<Config><ResVersion>1.2.3</ResVersion><BaseVerson><Res Tag="baseTag" version="1.2.3" '
           'ResSize="5"/></BaseVerson><Extra><listHash>'+checksum+'</listHash></Extra></Config>').encode()
    declared = {entry: ('<Config><ResConfig>'+pointer+'</ResConfig></Config>').encode(),
                root+'/config.xml': cfg, root+'/version/1.2.3/ResList.bin.zip': archive}
    reads = []
    def fetch(url, *, limit):
        reads.append(url)
        if url not in declared:
            return original.fetch(url, limit=limit)
        assert len(declared[url]) <= limit
        return declared[url]
    def forbidden(*_a, **_k): pytest.fail('Discovery escaped the context-owned transport')
    monkeypatch.setattr(release, 'download', forbidden)
    monkeypatch.setattr(release, '_parameters', forbidden)
    proof = {}
    branch, version, files, _ = release.discover('nte-global', official_cache=tmp_path,
                                                metadata_out=proof, fetch=fetch)
    assert (branch, version, len(files)) == ('PC_100', '1.2.3', 1)
    assert reads[:3] == list(declared)
    assert proof['kind'] == source.APPROVAL
