"""Ordinary source->SDK/wrapper->whole-manifest fixtures, not a game snapshot."""
from dataclasses import replace
import hashlib
import json
import struct
from urllib.parse import parse_qs

import pytest

from backend import infinity_nikki_build_stage as build
from backend import infinity_nikki_chunks as chunks
from backend import infinity_nikki_native as native
from backend import infinity_nikki_release as release
from backend.game_data_protocol import GameDataError,PreparationStage,SnapshotSource
from backend.tests.test_infinity_nikki_sdk_stage import Fixture as Launcher,apk_fixture
from backend.tests.test_infinity_nikki_release import sdk_fixture,encoded_config,sdk_response,fixture_cipher
from backend.tests.test_infinity_nikki_chunks import fixture as manifest_fixture,ROOT
from backend.tests.test_infinity_nikki_native import wrap
from backend.tests.test_publisher_transport import Response
from backend.publisher_transport import PublisherTransport


class Fixture(Launcher):
    def __init__(self,path,apk,monkeypatch,*,mode='text'):
        self.config={**sdk_fixture(False,False),'gameAuditConfig':{},'gameConfig':{}}
        def resources():
            encoded,identity=encoded_config(json.dumps(self.config).encode())
            member=b'MZ'+b'\0'*62+struct.pack('>I',len(encoded))+encoded+struct.pack('>I',len(identity))+identity
            return member,identity,encoded
        super().__init__(path,apk,monkeypatch,mode=mode,resource_factory=resources)
        self.reply_error=False
        self.bad_wrapper=False
        self.bad_manifest=False
        self.manifest_cancel=False
        self.body_urls=[]
        self.generation(0)

    def generation(self,number):
        version=str(3400+number)
        self.version,self.patch=version,str(number+1)
        self.build_url=ROOT+f'/BuildVersion/Windows/BuildVersion_{version}.{self.patch}.json'
        fields={'DefaultVersion':version,'FastPatchVersion':self.patch,'Region':'1','Channel':'3','Role':'0'}
        material=native.extract_wrapper_material(self.native,expected_native_sha256=hashlib.sha256(self.native).hexdigest())
        self.wrapped=wrap(json.dumps(fields).encode(),material.seed_utf16,material.suffix)
        self.packet={'game_config_apk':{'apk_version':'3000'},'game_config_patch':{'region':4,'channel':3,'role':0,
            'extra':{'cdn_url':self.build_url+';'+self.build_url.replace('x6oversea-client.','x6oversea-client-backup.')}}}
        base,*_=manifest_fixture(revision=number)
        patch={**base,'FileManifestList':[base['FileManifestList'][-1]]}
        self.manifest_urls=chunks.manifest_sources(self.build_url,fields)
        self.manifests=dict(zip(self.manifest_urls,(json.dumps(base).encode(),json.dumps(patch).encode())))
        self.manifest_etags={url:f'"authored-{number}-{i}"' for i,url in enumerate(self.manifest_urls)}

    def transport(self,ctx,*,hosts):
        assert ctx is self.ctx and set(hosts)<={'passport.infoldgames.com',*release.REGIONS['global'][1:],
            'infinitynikki.infoldgames.com','infinitynikki.nuanpaper.com','x6cn-game-apk.papegames.com',
            'x6oversea-client.infoldgames.com','x6oversea-client-backup.infoldgames.com'}
        owner=self
        class Transport(PublisherTransport):
            def fetch_bytes(self,*args,**kwargs):
                owner.kinds.append(kwargs['kind']);return super().fetch_bytes(*args,**kwargs)
            def consume_stream(self,*args,**kwargs):
                owner.kinds.append(kwargs['kind']);return super().consume_stream(*args,**kwargs)
            def download_to(self,*args,**kwargs):
                owner.kinds.append(kwargs['kind']);return super().download_to(*args,**kwargs)
        return Transport(ctx,hosts=hosts,opener=self.open)

    def open(self,request,**options):
        url=request.full_url
        if url.startswith('https://passport.infoldgames.com/'):
            self.calls.append((url,None))
            assert request.get_method()=='POST'
            assert not any(k.lower() in {'authorization','cookie'} for k,_ in request.header_items())
            params=parse_qs(request.data.decode());stamp=int(params['timestamp'][0])
            cipher,block=fixture_cipher(self.config['appConfig'],stamp,False,False)
            sealed=bytes.fromhex(params['data'][0]) if stamp%2==0 else __import__('base64').b64decode(params['data'][0])
            plain=cipher.decrypt(sealed)
            assert json.loads(plain[:-plain[-1]])['DOID']==''
            data=b'{"code":1002,"data":""}' if self.reply_error else sdk_response(self.config['appConfig'],stamp,False,False,self.packet)
            return Response(data,headers={'Content-Length':str(len(data))},url=url)
        if url==self.build_url:
            self.calls.append((url,None))
            raw=b'changed-owner' if self.bad_wrapper else self.wrapped
            return Response(raw,headers={'Content-Length':str(len(raw))},url=url)
        if url not in self.manifests:return super().open(request,**options)
        span=request.get_header('Range');self.calls.append((url,span))
        raw=self.manifests[url]
        headers={'ETag':self.manifest_etags[url],'Content-Length':str(len(raw))}
        if span:
            lo,hi=map(int,span.removeprefix('bytes=').split('-'))
            headers['Content-Range']=f'bytes {lo}-{hi}/{len(raw)}';raw=raw[lo:hi+1]
            headers['Content-Length']=str(len(raw))
            return Response(raw,status=206,headers=headers,url=url)
        self.body_urls.append(url)
        if self.bad_manifest:raw=b'!'+raw[1:]
        owner=self
        class Stream(Response):
            def read(self,size=-1):
                result=super().read(size)
                if owner.manifest_cancel:owner.ctx.cancel.set()
                return result
        return Stream(raw,headers=headers,url=url)

    def source_stage(self):return self.download(self.launcher_plan()).restore_handle

    def manifest_plan(self):
        previous=self.source_stage()
        self.context('plan').stage_handle=previous
        return self.provider.plan(self.request,self.ctx)


@pytest.mark.parametrize('mode',['text','text-audio'])
def test_current_sdk_and_native_wrapper_quote_whole_manifests_and_preserve_region_namespaces(tmp_path,apk_fixture,monkeypatch,mode):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch,mode=mode)
    plan=fixture.manifest_plan()
    assert plan.stage=='global-build-manifests' and plan.runtime_available and plan.source_proof is None
    assert plan.download_bytes==sum(len(raw)+32 for raw in fixture.manifests.values())
    assert fixture.body_urls==[] and 'audio' not in fixture.kinds
    artifact=build._read(fixture.ctx,plan.handle['receipt_sha256'])
    fields,packet=build._selection(fixture.provider,artifact,fixture.ctx)
    assert packet['game_config_patch']['region']==4 and fields['Region']=='1'
    result=fixture.download(plan)
    assert isinstance(result,PreparationStage) and not isinstance(result,SnapshotSource)
    assert result.restore_handle['stage']=='global-build-source'
    assert fixture.body_urls==list(fixture.manifest_urls)
    retained=build._retained(fixture.provider,result.restore_handle,fixture.ctx)
    assert [len(source.files) for source in retained[2]]==[3,1]
    before=len(fixture.calls)
    fixture.context('plan').stage_handle=result.restore_handle
    with pytest.raises(GameDataError) as next_stage:fixture.provider.plan(fixture.request,fixture.ctx)
    assert next_stage.value.code=='publisher_configuration_precedence_unresolved' and len(fixture.calls)==before
    with pytest.raises(GameDataError) as failure:fixture.provider.restore(result.restore_handle,fixture.context('restore'))
    assert failure.value.code=='publisher_configuration_reader_unresolved' and len(fixture.calls)==before


def test_new_normal_generation_comes_from_fresh_sdk_build_and_manifest_fields(tmp_path,apk_fixture,monkeypatch):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    first=fixture.manifest_plan()
    fixture.generation(1)
    fixture.context('plan').stage_handle=first.handle
    second=fixture.provider.plan(fixture.request,fixture.ctx)
    assert first.revision!=second.revision and first.handle!=second.handle
    assert build._read(fixture.ctx,second.handle['receipt_sha256'])['build_url']==fixture.build_url
    assert isinstance(fixture.download(second),PreparationStage)


def test_original_plain_build_json_needs_no_wrapper_parameter_or_native_decode(tmp_path,apk_fixture,monkeypatch):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    previous=fixture.source_stage()
    fields={'DefaultVersion':fixture.version,'FastPatchVersion':fixture.patch,'Region':'1','Channel':'3','Role':'0'}
    fixture.wrapped=json.dumps(fields).encode()
    monkeypatch.setattr(native,'extract_wrapper_material',lambda *a,**kw:pytest.fail('A plain document must not acquire a wrapper key.'))
    fixture.context('plan').stage_handle=previous
    plan=fixture.provider.plan(fixture.request,fixture.ctx)
    assert isinstance(fixture.download(plan),PreparationStage)


@pytest.mark.parametrize('raw',[b'{"DefaultVersion":"3400","DefaultVersion":"3400","FastPatchVersion":"1"}',
    b'{"DefaultVersion":"3400","FastPatchVersion":"1","extra":NaN}',
    b'{"DefaultVersion":"3401","FastPatchVersion":"1"}',b'{"DefaultVersion":3400,"FastPatchVersion":"1"}',b'{"broken":'])
def test_plain_build_ambiguity_invalid_json_or_pointer_mismatch_stops_before_manifest_quote(tmp_path,apk_fixture,monkeypatch,raw):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch);previous=fixture.source_stage()
    fixture.wrapped=raw
    fixture.context('plan').stage_handle=previous
    with pytest.raises(GameDataError):fixture.provider.plan(fixture.request,fixture.ctx)
    assert fixture.body_urls==[] and not any('/PaperHttpChunkInstall.manifest' in url for url,_ in fixture.calls)


@pytest.mark.parametrize('change',['download_bytes','required_disk_bytes','revision','artifact'])
def test_modified_quote_or_source_fails_before_whole_manifest_transfer(tmp_path,apk_fixture,monkeypatch,change):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    plan=fixture.manifest_plan();before=len(fixture.calls)
    if change=='artifact':
        path=build._path(fixture.ctx,plan.handle['receipt_sha256']);path.write_bytes(path.read_bytes()+b' ')
    else:plan=replace(plan,**{change:'other' if change=='revision' else getattr(plan,change)+1})
    with pytest.raises(GameDataError):fixture.download(plan)
    assert len(fixture.calls)==before and fixture.body_urls==[]


@pytest.mark.parametrize('failure',['etag','corrupt','cancelled'])
def test_partial_manifest_update_keeps_existing_data_and_cleans_staging(tmp_path,apk_fixture,monkeypatch,failure):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch);plan=fixture.manifest_plan()
    previous=tmp_path/'previous-caption-and-recording.dat';previous.write_bytes(b'authored old data')
    if failure=='etag':fixture.manifest_etags[fixture.manifest_urls[0]]='"changed"'
    if failure=='corrupt':fixture.bad_manifest=True
    if failure=='cancelled':fixture.manifest_cancel=True
    with pytest.raises(GameDataError):fixture.download(plan)
    assert previous.read_bytes()==b'authored old data'
    assert not list((fixture.ctx.cache_directory/'infinitynikki-global-build').glob('*.manifest'))
    assert not list(fixture.ctx.cache_directory.rglob('*.part'))


@pytest.mark.parametrize('failure',['sdk','wrapper'])
def test_missing_sdk_or_wrapper_parameters_never_become_a_format_change_or_ready_claim(tmp_path,apk_fixture,monkeypatch,failure):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch);previous=fixture.source_stage()
    fixture.reply_error=failure=='sdk';fixture.bad_wrapper=failure=='wrapper'
    fixture.context('plan').stage_handle=previous
    with pytest.raises(GameDataError) as error:fixture.provider.plan(fixture.request,fixture.ctx)
    assert 'format changed' not in str(error.value).lower() and fixture.body_urls==[]
    if failure=='wrapper':assert error.value.code=='publisher_wrapper_owner_unresolved'


def test_changed_retained_manifest_is_rejected_before_network(tmp_path,apk_fixture,monkeypatch):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    result=fixture.download(fixture.manifest_plan())
    path=next((fixture.ctx.cache_directory/'infinitynikki-global-build').glob('*.manifest'))
    path.write_bytes(path.read_bytes()+b'changed')
    before=len(fixture.calls)
    fixture.context('plan').stage_handle=result.restore_handle
    with pytest.raises(GameDataError):fixture.provider.plan(fixture.request,fixture.ctx)
    assert len(fixture.calls)==before
