"""Authored original metadata/ranges through the real service and transport."""
import hashlib
import json
from pathlib import Path
import re
import struct
from xml.etree import ElementTree as E
import zlib
from types import SimpleNamespace
from dataclasses import replace

from Crypto.Cipher import AES
import pytest

from backend import nte_native_baseline as baseline, nte_toolchain, runtime_bundle
from backend import nte_updater_source as source
from backend.game_data import GameDataService
from backend.nte_game_data import NteGameDataProvider
from backend.tests.test_nte_game_data import originals, finish, REQUEST
from backend.tests.test_nte_native_baseline import source as baseline_source
from backend.tests.test_nte_toolchain import fixture as runtime_fixture
from backend.tests.test_nte_updater_source import packed
from backend.tests.test_publisher_transport import Response
from backend.tests.test_nte_publisher_pak import package, signature, KEY


class Originals:
    def __init__(self, tmp_path, monkeypatch, *, dense=False, selected_metadata=False):
        self.sdk = originals(monkeypatch)
        self.old_native, old_manifest = baseline_source(monkeypatch)
        self.current_native = self.old_native+b'new original overlay'
        layout, _ = runtime_fixture(tmp_path/'host', monkeypatch)
        monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
        monkeypatch.setattr(nte_toolchain, 'discover_layout', lambda: layout)
        self.root = layout.cache_root/'game-provider'
        cache = self.root/'nte/cache/tools/nte-publisher/format'
        params = source.resolve(source.plan(fetch=self.sdk.fetch), cache, fetch=self.sdk.fetch)
        rows = ([(f'owned-{i:05}.locres', b'authored text', 0, False, False) for i in range(6000)] if dense else
                [('owned.locres', b'authored original text\n'*18000, 0, False, False)])
        archive = package(rows)
        sig, toc = signature(archive), b'authored whole global TOC'
        data = {'Client/Unfamiliar/Original.DLL': self.current_native,
                'Client/WindowsNoEditor/HT/Content/Paks/Original.sig': sig,
                'Client/WindowsNoEditor/HT/Content/Paks/Original.pak': archive,
                'Client/WindowsNoEditor/HT/Content/Paks/global.utoc': toc}
        self.forbidden_assets = set()
        self.metadata_archives = {}
        if selected_metadata:
            specs = {
                'study': ('Content/Localization/Game/ja/', 'Game.locres'),
                'target': ('Content/Localization/Game/en/', 'Game.locres'),
                'other-locale': ('Content/Localization/Game/ko/', 'Game.locres'),
                'registry': ('', 'AssetRegistry.bin'),
                'subtitles': ('Content/SrtFile/FFMpeg/Story/', 'owned.srt'),
                'voice': ('Content/WwiseAudio/Media/Japanese/', '123.wem')}
            for label, (folder, name) in specs.items():
                raw = package([(name, (label+' original source\n').encode()*18000, 0, False, False)], folder=folder)
                owner = 'Client/WindowsNoEditor/HT/Content/Paks/'+label+'.pak'
                data[owner], data[owner[:-4]+'.sig'] = raw, signature(raw)
                self.metadata_archives[label] = self.url('PC_100', hashlib.md5(raw).hexdigest(), len(raw))
            from backend.tests.test_nte_publisher_iostore import fixture as iostore
            global_toc, global_ucas = iostore(global_toc=True)
            ordinary_toc, ordinary_ucas = iostore()
            data.update({
                'Client/WindowsNoEditor/HT/Content/Paks/global.utoc': global_toc,
                'Client/WindowsNoEditor/HT/Content/Paks/global.ucas': global_ucas,
                'Client/WindowsNoEditor/HT/Content/Paks/owned.utoc': ordinary_toc,
                'Client/WindowsNoEditor/HT/Content/Paks/owned.ucas': ordinary_ucas})
        self.expected_index_members = sum(name.endswith(('.sig', '.utoc')) for name in data)+2
        xml = E.Element('ResList', version='1.2.3', tag='baseTag')
        for name, raw in data.items():
            E.SubElement(xml, 'Res', filename=name, filesize=str(len(raw)), md5=hashlib.md5(raw).hexdigest())
        if not selected_metadata:
            E.SubElement(xml, 'Res', filename='Client/WindowsNoEditor/HT/Content/Paks/global.ucas',
                         filesize='500000', md5='b'*32)
        xml = E.tostring(xml)
        compressed = zlib.compress(xml); pad = 16-len(compressed)%16
        envelope = b'PatcherXML0\0'+struct.pack('<I', len(xml))+AES.new(params.key, AES.MODE_CBC, params.iv).encrypt(
            compressed+bytes([pad])*pad)
        cfg = ('<Config><ResVersion>1.2.3</ResVersion><BaseVerson><Res Tag="baseTag" version="1.2.3" '
               'ResSize="5"/></BaseVerson><Extra><listHash>'+hashlib.md5(xml).hexdigest()+'</listHash></Extra></Config>').encode()
        branch = 'https://ntecdn1.perfectworld.com/clientRes/PC_100/Version/Windows'
        self.metadata = {source.VERSION_URL: self.sdk.version_body,
                         self.sdk.manifest_url: E.tostring(self.sdk.root),
                         branch+'/config.xml': cfg,
                         branch+'/version/1.2.3/ResList.bin.zip': packed('ResList.bin', envelope),
                         baseline.BASELINE['manifest_url']: old_manifest}
        self.objects = {}
        for raw in data.values():
            self.add_object('PC_100', hashlib.md5(raw).hexdigest(), raw)
        # The original baseline fixture owns exactly 11 prefix bytes.
        old_url = self.url(baseline.BASELINE['branch'], 'e'*32, len(self.old_native)+11)
        self.objects[old_url] = bytes(11)+self.old_native
        self.calls, self.corrupt = [], False
        from backend import nte_publisher
        description = ('Neverness to Everness (global) 0x'+KEY.hex()+'\n').encode()
        pin = ('a'*40, hashlib.sha256(description).hexdigest())
        monkeypatch.setattr(nte_publisher, 'NATIVE_ARCHIVE', pin)
        (cache/(pin[0]+'-'+pin[1]+'.txt')).write_bytes(description)

    @staticmethod
    def url(branch, digest, size):
        owner = digest+'.'+str(size)
        return 'https://ntecdn1.perfectworld.com/clientRes/'+branch+'/Res/'+digest[0]+'/'+owner

    def add_object(self, branch, digest, raw):
        self.objects[self.url(branch, digest, len(raw))] = raw

    def open(self, request, **_):
        url, selected = request.full_url, request.get_header('Range')
        self.calls.append({'url': url, 'range': selected})
        if selected:
            assert url not in self.forbidden_assets, 'An unselected locale or voice member was fetched'
            match = re.fullmatch(r'bytes=(\d+)-(\d+)', selected); assert match
            start, end = map(int, match.groups()); original = self.objects[url]
            raw = original[start:end+1]
            if self.corrupt:
                raw = bytes([raw[0]^1])+raw[1:]
            return Response(raw, status=206, url=url, headers={
                'Content-Length': str(len(raw)), 'Content-Range': f'bytes {start}-{end}/{len(original)}'})
        assert url in self.metadata, 'Unplanned SDK/community/media request'
        return Response(self.metadata[url], url=url)

    def service(self):
        return GameDataService(self.root, {'nte': NteGameDataProvider(platform='windows', opener=self.open)})


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_real_service_plans_original_member_sizes_before_ranges_and_never_activates_indices(tmp_path, monkeypatch, mode):
    original = Originals(tmp_path, monkeypatch); service = original.service()
    try:
        plan = service.plan('nte', {**REQUEST, 'content_mode': mode})['game']
        assert plan['revision'].startswith('nte-indices-') and plan['can_download']
        assert not any(call['range'] for call in original.calls)
        assert plan['download_bytes'] < 1000000
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        state = finish(service)
        assert state['job']['status'] == 'needs_plan' and state['job']['downloaded_bytes'] == plan['download_bytes']
        assert state['state'] != 'ready' and not (original.root/'nte/current.json').exists()
        assert len([call for call in original.calls if call['range']]) == original.expected_index_members
        following = service.plan('nte', {**REQUEST, 'content_mode': mode})['game']
        assert following['can_download'] and following['revision'].startswith('nte-ranges-')
        # Cache-only preflight has not read any original archive body.
        assert len([call for call in original.calls if call['range']]) == original.expected_index_members
        service.download('nte', {'plan_id': following['plan_id'], 'revision': following['revision']})
        state = finish(service)
        assert state['job']['status'] == 'needs_plan' and state['job']['downloaded_bytes'] == following['download_bytes']
        complete = service.plan('nte', {**REQUEST, 'content_mode': mode})['game']
        assert not complete['can_download'] and complete['download_bytes'] is None
        assert complete['revision'].startswith('nte-archive-blocks-')
        assert state['state'] != 'ready' and not (original.root/'nte/current.json').exists()
        assert not list((original.root/'nte/cache').rglob('complete.ucas'))
    finally:
        service.close()


def test_changed_official_declaration_blocks_before_native_or_index_transfer(tmp_path, monkeypatch):
    original = Originals(tmp_path, monkeypatch); service = original.service()
    try:
        plan = service.plan('nte', REQUEST)['game']
        original.metadata[source.VERSION_URL] += b'changed'
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        state = finish(service)
        assert state['job']['status'] == 'failed' and state['state'] != 'ready'
        assert not any(call['range'] for call in original.calls)
        assert not (original.root/'nte/current.json').exists()
    finally:
        service.close()


def test_corrupt_original_range_never_publishes_a_native_or_ready_library(tmp_path, monkeypatch):
    original = Originals(tmp_path, monkeypatch); service = original.service()
    try:
        plan = service.plan('nte', REQUEST)['game']; original.corrupt = True
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        state = finish(service)
        assert state['job']['status'] == 'failed' and state['state'] != 'ready'
        assert not list((original.root/'nte/cache').rglob('*.native'))
        assert not (original.root/'nte/current.json').exists()
    finally:
        service.close()


@pytest.mark.parametrize('fault', ['source', 'block', 'description'])
def test_archive_stage_rejects_changed_source_or_corrupt_blocks_without_activating(tmp_path, monkeypatch, fault):
    original = Originals(tmp_path, monkeypatch); service = original.service()
    try:
        def acquire(plan):
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
            return finish(service)
        assert acquire(service.plan('nte', REQUEST)['game'])['job']['status'] == 'needs_plan'
        plan = service.plan('nte', REQUEST)['game']
        before = len([call for call in original.calls if call['range']])
        if fault == 'source': original.metadata[source.VERSION_URL] += b'changed'
        elif fault == 'block': original.corrupt = True
        else:
            from backend import nte_publisher
            revision, digest = nte_publisher.NATIVE_ARCHIVE
            (original.root/'nte/cache/tools/nte-publisher/format'/f'{revision}-{digest}.txt').write_bytes(b'changed')
        state = acquire(plan)
        assert state['job']['status'] == 'failed' and state['state'] != 'ready'
        assert not list((original.root/'nte/cache/tools/nte-publisher/ranges').rglob('*.chunk'))
        assert not (original.root/'nte/current.json').exists()
        assert len([call for call in original.calls if call['range']]) == before+int(fault == 'block')
    finally:
        service.close()


def test_large_encrypted_index_and_directory_require_separate_explicit_plans(tmp_path, monkeypatch):
    original = Originals(tmp_path, monkeypatch, dense=True); service = original.service()
    try:
        rounds = []
        for _ in range(8):
            before = len([call for call in original.calls if call['range']])
            plan = service.plan('nte', REQUEST)['game']
            assert len([call for call in original.calls if call['range']]) == before
            if not plan['can_download']:
                assert plan['revision'].startswith('nte-archive-blocks-')
                break
            rounds.append(plan['revision'].split('-')[1])
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
            state = finish(service)
            assert state['job']['status'] == 'needs_plan'
            assert state['job']['downloaded_bytes'] == plan['download_bytes']
            assert not (original.root/'nte/current.json').exists()
        else:
            pytest.fail('Bounded authored index did not converge')
        assert rounds[0] == 'indices' and len(rounds) >= 4
        assert set(rounds[1:]) == {'ranges'}
        assert not list((original.root/'nte/cache').rglob('*.wem'))
    finally:
        service.close()


def test_missing_initial_description_is_explicit_without_community_or_asset_reads(tmp_path, monkeypatch):
    original = Originals(tmp_path, monkeypatch); service = original.service()
    try:
        plan = service.plan('nte', REQUEST)['game']
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        assert finish(service)['job']['status'] == 'needs_plan'
        from backend import nte_publisher
        revision, digest = nte_publisher.NATIVE_ARCHIVE
        (original.root/'nte/cache/tools/nte-publisher/format'/f'{revision}-{digest}.txt').unlink()
        before = len([call for call in original.calls if call['range']])
        following = service.plan('nte', REQUEST)['game']
        assert not following['can_download'] and following['download_bytes'] is None
        assert following['revision'].startswith('nte-initial-description-')
        assert len([call for call in original.calls if call['range']]) == before
        assert not (original.root/'nte/current.json').exists()
    finally:
        service.close()


def test_more_normal_update_indexes_continue_in_bounded_stages_and_reject_foreign_ranges():
    from backend import nte_game_data_ranges as ranges
    from backend.game_data_protocol import GameDataError
    source = SimpleNamespace(checksums=bytes(4*128), item=SimpleNamespace(size=128*65536))
    owners = {f'original-{i}.pak': source for i in range(40)}
    wanted = [{'pak': name, 'first': 0, 'stop': 64} for name in owners]
    batch = ranges._batch(owners, wanted)
    assert len(batch) == 16 and ranges._cost(owners, batch) == 64*1024**2
    assert len(ranges._batch(owners, wanted[len(batch):])) == 16
    for records in ([{**wanted[0], 'pak': 'foreign.pak'}], [{**wanted[0], 'first': True}],
                    [{**wanted[0], 'stop': 129}], [wanted[0], wanted[0]],
                    [{**wanted[0], 'extra': 'unproved'}]):
        with pytest.raises(GameDataError): ranges._cost(owners, records)


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_selected_locale_metadata_has_exact_owner_plan_and_no_member_reads_during_preflight(tmp_path, monkeypatch, mode):
    from backend import nte_publisher_pak as pak
    original = Originals(tmp_path, monkeypatch, selected_metadata=True); service = original.service()
    request = {**REQUEST, 'content_mode': mode}
    try:
        for _ in range(8):
            plan = service.plan('nte', request)['game']
            private = service.plans[plan['plan_id']]['plan'].handle
            if private.get('selection', {}).get('purpose') == 'selected-text-metadata':
                break
            assert plan['can_download']
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
            assert finish(service)['job']['status'] == 'needs_plan'
        else:
            pytest.fail('Original index metadata did not finish')
        assert private['selection']['members_count'] == 4
        original.forbidden_assets.update(original.metadata_archives[label] for label in ('other-locale', 'voice'))
        monkeypatch.setattr(pak.Archive, 'read', lambda *_: pytest.fail('Preflight read a member'))
        monkeypatch.setattr(pak.Archive, '_parts', lambda *_: pytest.fail('Preflight requested body parts'))
        monkeypatch.setattr(pak.Archive, '_expand_oodle', lambda *_: pytest.fail('Preflight decoded a member'))
        before = len([call for call in original.calls if call['range']])
        repeated = service.plan('nte', request)['game']
        assert repeated['revision'] == plan['revision'] and repeated['download_bytes'] == plan['download_bytes']
        assert len([call for call in original.calls if call['range']]) == before
        service.download('nte', {'plan_id': repeated['plan_id'], 'revision': repeated['revision']})
        state = finish(service)
        assert state['job']['status'] == 'needs_plan'
        assert state['job']['downloaded_bytes'] == repeated['download_bytes']
        stage = json.loads((original.root/'nte/stage.json').read_bytes())
        from backend.nte_game_data_content import _identity
        assert stage['handle']['selection'] == private['selection']
        assert stage['handle']['plan_sha256'] == _identity(private)
        assert stage['handle']['ranges_sha256'] == _identity(private['ranges'])
        assert stage['handle']['transferred_bytes'] == repeated['download_bytes']
        selected = {call['url'] for call in original.calls if call['range'] and call['url'] in original.metadata_archives.values()}
        assert selected >= {original.metadata_archives[label] for label in ('study', 'target', 'registry', 'subtitles')}
        following = service.plan('nte', request)['game']
        assert following['can_download'] and following['revision'].startswith('nte-global-metadata-')
        before = len([call for call in original.calls if call['range']])
        service.download('nte', {'plan_id': following['plan_id'], 'revision': following['revision']})
        state = finish(service)
        assert state['job']['status'] == 'needs_plan' and state['job']['downloaded_bytes'] == following['download_bytes']
        assert len([call for call in original.calls if call['range']]) == before+1
        local = service.plan('nte', request)['game']
        assert not local['can_download'] and local['revision'].startswith('nte-local-metadata-')
        assert not (original.root/'nte/current.json').exists()
    finally:
        service.close()


def test_rehashed_wrong_member_selection_is_rejected_before_transfer_and_retains_prior_stage(tmp_path, monkeypatch):
    from backend.nte_game_data_content import _identity
    original = Originals(tmp_path, monkeypatch, selected_metadata=True); service = original.service()
    try:
        for _ in range(8):
            plan = service.plan('nte', REQUEST)['game']
            item = service.plans[plan['plan_id']]
            if item['plan'].handle.get('selection', {}).get('purpose') == 'selected-text-metadata':
                break
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
            assert finish(service)['job']['status'] == 'needs_plan'
        else: pytest.fail('Original indexes did not converge')
        previous = (original.root/'nte/stage.json').read_bytes()
        handle = json.loads(json.dumps(item['plan'].handle))
        handle['selection']['members_sha256'] = '0'*64
        item['plan'] = replace(item['plan'], handle=handle, revision='nte-ranges-'+_identity(handle))
        before = len([call for call in original.calls if call['range']])
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': item['plan'].revision})
        assert finish(service)['job']['status'] == 'failed'
        assert len([call for call in original.calls if call['range']]) == before
        assert (original.root/'nte/stage.json').read_bytes() == previous
        healthy = service.plan('nte', REQUEST)['game']
        assert healthy['can_download'] and healthy['revision'] == plan['revision']
        assert not (original.root/'nte/current.json').exists()
    finally:
        service.close()
