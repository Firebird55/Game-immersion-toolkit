"""Ordinary manifest->complete configuration-carrier stage; authored data only."""
from dataclasses import replace
import hashlib
import json
import zlib

import pytest

from backend import infinity_nikki_configuration_stage as configuration
from backend.game_data_protocol import GameDataError,PreparationStage,SnapshotSource
from backend.tests.test_infinity_nikki_build_stage import Fixture as Build,apk_fixture
from backend.tests.test_infinity_nikki_chunks import A,WINDOW,blob,number,chunk
from backend.tests.test_infinity_nikki_pak import fixture as archive_fixture
from backend.tests.test_publisher_transport import Response


class Fixture(Build):
    def generation(self,numbered):
        super().generation(numbered)
        pak,_=archive_fixture(revision=numbered,mount='../../../X6Game/Config/',
            specs=[('DefaultX6PackageSettings.ini',b'authored settings'+bytes([numbered]),True)])
        self.files=dict(zip(('pak','sig','ucas','udirhash','utoc'),(pak,b'authored-signature',b'ucas',b'hash',b'utoc')))
        self.basename='Default_Ini_'+self.version+'_P'
        rows=[];body=bytearray()
        for suffix,raw in self.files.items():
            offset=len(body);body.extend(raw)
            rows.append({'Filename':self.basename+'.'+suffix,'FileHash':blob(hashlib.sha1(raw).digest()),
                'FileChunkParts':[{'Guid':A,'Offset':number(offset,4),'Size':number(len(raw),4)}]})
        offset=len(body);body.extend(b'unused mixed movie content')
        rows.append({'Filename':'UnselectedMovie.pak','FileHash':blob(hashlib.sha1(body[offset:]).digest()),
            'FileChunkParts':[{'Guid':A,'Offset':number(offset,4),'Size':number(len(body)-offset,4)}]})
        data=bytes(body).ljust(WINDOW,b'\0');rolling=0x12345678+numbered
        self.carrier=chunk(data,A,rolling)
        manifest=json.loads(self.manifests[self.manifest_urls[0]])
        manifest.update(FileManifestList=rows,ChunkHashList={A:number(rolling,8)},
            ChunkShaList={A:hashlib.sha1(data).hexdigest().upper()},DataGroupList={A:number(87,1)},
            ChunkFilesizeList={A:number(len(self.carrier),8)})
        self.manifests[self.manifest_urls[0]]=json.dumps(manifest).encode()
        root=self.manifest_urls[0].rsplit('/',1)[0]
        self.carrier_url=root+f'/ChunksV3/87/{rolling:016X}_{A}.chunk'
        self.carrier_etag='"authored-config-'+str(numbered)+'"'
        self.carrier_reads=[];self.bad_carrier=False;self.cancel_carrier=False

    def open(self,request,**options):
        if request.full_url!=self.carrier_url:return super().open(request,**options)
        span=request.get_header('Range');self.calls.append((request.full_url,span))
        self.carrier_reads.append(span)
        data=self.carrier
        headers={'ETag':self.carrier_etag,'Content-Length':str(len(data))}
        if span:
            assert span=='bytes=0-31';headers['Content-Range']=f'bytes 0-31/{len(data)}'
            headers['Content-Length']='32';return Response(data[:32],status=206,headers=headers,url=request.full_url)
        if self.bad_carrier:data=data[:-1]+bytes([data[-1]^1])
        owner=self
        class Stream(Response):
            def read(self,size=-1):
                value=super().read(size)
                if owner.cancel_carrier:owner.ctx.cancel.set()
                return value
        return Stream(data,headers=headers,url=request.full_url)

    def build_source(self):return self.download(self.manifest_plan()).restore_handle

    def configuration_plan(self):
        self.context('plan').stage_handle=self.build_source()
        return self.provider.plan(self.request,self.ctx)

    def replace_pak(self,raw):
        old=self.files['pak'];assert len(raw)==len(old)
        decoded=zlib.decompress(self.carrier[62:]);assert decoded.startswith(old)
        decoded=raw+decoded[len(old):]
        manifest=json.loads(self.manifests[self.manifest_urls[0]])
        rolling=int.from_bytes(bytes(int(manifest['ChunkHashList'][A][i:i+3]) for i in range(0,24,3)),'little')
        self.carrier=chunk(decoded,A,rolling)
        manifest['FileManifestList'][0]['FileHash']=blob(hashlib.sha1(raw).digest())
        manifest['ChunkShaList'][A]=hashlib.sha1(decoded).hexdigest().upper()
        manifest['ChunkFilesizeList'][A]=number(len(self.carrier),8)
        self.manifests[self.manifest_urls[0]]=json.dumps(manifest).encode();self.files['pak']=raw


@pytest.mark.parametrize('mode',['text','text-audio'])
def test_whole_owned_config_carrier_cost_and_files_are_verified_without_profile_or_ready(tmp_path,apk_fixture,monkeypatch,mode):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch,mode=mode)
    plan=fixture.configuration_plan()
    assert plan.stage=='global-configuration-packages' and plan.runtime_available and plan.source_proof is None
    assert plan.download_bytes==len(fixture.carrier)+32 and fixture.carrier_reads==['bytes=0-31']
    assert 'mixed content' in plan.message and 'audio' not in fixture.kinds
    result=fixture.download(plan)
    assert isinstance(result,PreparationStage) and not isinstance(result,SnapshotSource)
    assert result.restore_handle['stage']=='global-configuration-source'
    receipt,_,_=configuration._retained(fixture.provider,result.restore_handle,fixture.ctx)
    assert len(receipt['files'])==5
    for row in receipt['files']:
        assert configuration._path(fixture.ctx,row['sha256'],'data').read_bytes()==fixture.files[row['name'].rsplit('.',1)[1]]
    assert fixture.carrier_reads==['bytes=0-31',None,'bytes=0-31']
    before=len(fixture.calls);fixture.context('plan').stage_handle=result.restore_handle
    from backend.infinity_nikki_pak import Archive
    monkeypatch.setattr(Archive,'read_many',lambda *a,**kw:pytest.fail('Index planning must not decode settings members.'))
    gate=fixture.provider.plan(fixture.request,fixture.ctx)
    assert not gate.runtime_available and gate.stage=='global-configuration-source' and gate.source_proof is None
    assert gate.required_disk_bytes==len(b'authored settings\0') and gate.download_bytes==0
    assert '1 settings members' in gate.message and 'Oodle' in gate.message
    with pytest.raises(GameDataError) as error:fixture.provider.restore(result.restore_handle,fixture.context('restore'))
    assert error.value.code=='publisher_configuration_index_reader_unresolved' and len(fixture.calls)==before


@pytest.mark.parametrize('failure',['etag','corrupt','cancel','consent','file-hash'])
def test_failed_acquisition_preserves_old_data_and_never_activates_package(tmp_path,apk_fixture,monkeypatch,failure):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    if failure=='file-hash':
        manifest=json.loads(fixture.manifests[fixture.manifest_urls[0]])
        manifest['FileManifestList'][0]['FileHash']=blob(bytes(20))
        fixture.manifests[fixture.manifest_urls[0]]=json.dumps(manifest).encode()
    plan=fixture.configuration_plan()
    previous=tmp_path/'existing-language-data';previous.write_bytes(b'previous data')
    if failure=='etag':fixture.carrier_etag='"changed"'
    if failure=='corrupt':fixture.bad_carrier=True
    if failure=='cancel':fixture.cancel_carrier=True
    if failure=='consent':plan=replace(plan,download_bytes=plan.download_bytes+1)
    with pytest.raises(GameDataError):fixture.download(plan)
    assert previous.read_bytes()==b'previous data'
    root=fixture.ctx.cache_directory/'infinitynikki-global-configuration'
    assert not list(root.glob('*.data')) and not list(root.glob('pending-*'))


@pytest.mark.parametrize('failure',['ambiguous','missing-companion'])
def test_unknown_owner_or_overlay_precedence_never_picks_a_profile_or_package(tmp_path,apk_fixture,monkeypatch,failure):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    if failure=='ambiguous':fixture.manifests[fixture.manifest_urls[1]]=fixture.manifests[fixture.manifest_urls[0]]
    else:
        data=json.loads(fixture.manifests[fixture.manifest_urls[0]])
        data['FileManifestList'].pop(1);fixture.manifests[fixture.manifest_urls[0]]=json.dumps(data).encode()
    with pytest.raises(GameDataError):fixture.configuration_plan()
    assert fixture.carrier_reads==[]


def test_retained_file_corruption_is_checked_offline_before_requote(tmp_path,apk_fixture,monkeypatch):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    result=fixture.download(fixture.configuration_plan())
    target=next((fixture.ctx.cache_directory/'infinitynikki-global-configuration').glob('*.data'))
    target.write_bytes(target.read_bytes()+b'changed')
    before=len(fixture.calls);fixture.context('plan').stage_handle=result.restore_handle
    with pytest.raises(GameDataError):fixture.provider.plan(fixture.request,fixture.ctx)
    assert len(fixture.calls)==before


def test_pending_source_requote_uses_actual_new_validator_without_old_consent(tmp_path,apk_fixture,monkeypatch):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    first=fixture.configuration_plan()
    fixture.carrier_etag='"new-owned-validator"'
    fixture.context('plan').stage_handle=first.handle
    second=fixture.provider.plan(fixture.request,fixture.ctx)
    assert first.handle!=second.handle and second.download_bytes==first.download_bytes
    with pytest.raises(GameDataError):fixture.download(first)
    assert isinstance(fixture.download(second),PreparationStage)


@pytest.mark.parametrize('failure',['dynamic-guid','index-integrity'])
def test_actual_archive_compatibility_is_required_after_file_integrity(tmp_path,apk_fixture,monkeypatch,failure):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    raw=bytearray(fixture.files['pak'])
    if failure=='dynamic-guid':raw[-221]=1
    else:
        import struct
        index=struct.unpack_from('<Q',raw,len(raw)-221+25)[0];raw[index]^=1
    fixture.replace_pak(bytes(raw))
    result=fixture.download(fixture.configuration_plan())
    if failure=='dynamic-guid':
        from backend import infinity_nikki_pak_material
        monkeypatch.setattr(infinity_nikki_pak_material,'extract_default_pak_material',
            lambda *a,**kw:pytest.fail('A nonzero GUID must not be tested with the default producer.'))
    before=len(fixture.calls);fixture.context('plan').stage_handle=result.restore_handle
    with pytest.raises(GameDataError) as error:fixture.provider.plan(fixture.request,fixture.ctx)
    expected='publisher_dynamic_keychain_unresolved' if failure=='dynamic-guid' else 'publisher_configuration_index_unresolved'
    assert error.value.code==expected and len(fixture.calls)==before
