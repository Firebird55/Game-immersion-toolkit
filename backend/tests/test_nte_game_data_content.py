"""Authored original metadata/ranges through the real service and transport."""
import hashlib
import json
from pathlib import Path
import re
import struct
from xml.etree import ElementTree as E
import zlib

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


class Originals:
    def __init__(self, tmp_path, monkeypatch):
        self.sdk = originals(monkeypatch)
        self.old_native, old_manifest = baseline_source(monkeypatch)
        self.current_native = self.old_native+b'new original overlay'
        layout, _ = runtime_fixture(tmp_path/'host', monkeypatch)
        monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
        monkeypatch.setattr(nte_toolchain, 'discover_layout', lambda: layout)
        self.root = layout.cache_root/'game-provider'
        cache = self.root/'nte/cache/tools/nte-publisher/format'
        params = source.resolve(source.plan(fetch=self.sdk.fetch), cache, fetch=self.sdk.fetch)
        sig, toc = b'authored whole SIG', b'authored whole global TOC'
        data = {'Client/Unfamiliar/Original.DLL': self.current_native,
                'Client/WindowsNoEditor/HT/Content/Paks/Original.sig': sig,
                'Client/WindowsNoEditor/HT/Content/Paks/global.utoc': toc}
        xml = E.Element('ResList', version='1.2.3', tag='baseTag')
        for name, raw in data.items():
            E.SubElement(xml, 'Res', filename=name, filesize=str(len(raw)), md5=hashlib.md5(raw).hexdigest())
        E.SubElement(xml, 'Res', filename='Client/WindowsNoEditor/HT/Content/Paks/Original.pak',
                     filesize='1000000', md5='a'*32)
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
        assert len([call for call in original.calls if call['range']]) == 4
        following = service.plan('nte', {**REQUEST, 'content_mode': mode})['game']
        assert not following['can_download'] and following['download_bytes'] is None
        assert following['revision'].startswith('nte-archive-blocks-')
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
