"""Normal settings-stage fixtures; zlib stand-ins do not claim Oodle decoding."""
from dataclasses import replace
import zlib

import pytest

from backend import infinity_nikki_settings_stage as settings
from backend import publisher_oodle
from backend.game_data_protocol import GameDataError,PreparationStage,SnapshotSource
from backend.tests.test_infinity_nikki_configuration_stage import Fixture as Packages,apk_fixture

INI=b'''[/Script/X6Game.X6PackageSettings]
CMSApiUrl="https://authored.invalid"
ClientID=fixture
ClientKey=authored fixture only
+Items=one
-Items=two
ClientID=second ordered assignment
'''


class Fixture(Packages):
    def settings_payload(self,numbered):return INI

    def __init__(self,*args,**kwargs):
        monkeypatch=args[2] if len(args)>2 else kwargs['monkeypatch']
        super().__init__(*args,**kwargs)
        owner=self
        class Codec:
            identity={'schema':'authored-test-codec/1'}
            def decode(self,blocks,*,work,check):
                owner.codec_calls+=1;check()
                result=b''.join(zlib.decompress(raw) for method,raw,size in blocks)
                if owner.codec_failure=='cancel':owner.ctx.cancel.set();check()
                if owner.codec_failure=='throw':raise GameDataError('publisher_codec_failed','Authored codec failure.')
                if owner.codec_failure=='corrupt':return b'!'+result[1:]
                return result
        self.codec=Codec();self.codec_calls=0;self.codec_failure=None
        monkeypatch.setattr(publisher_oodle,'create_compression',lambda **kw:self.codec if kw['platform']=='windows' else None)

    def member_plan(self):
        result=self.download(self.configuration_plan())
        self.context('plan').stage_handle=result.restore_handle
        return self.provider.plan(self.request,self.ctx)


@pytest.mark.parametrize('mode',['text','text-audio'])
def test_original_members_use_actual_plan_download_receipt_restore_and_keep_assignments_ordered(tmp_path,apk_fixture,monkeypatch,mode):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch,mode=mode)
    plan=fixture.member_plan();before=len(fixture.calls)
    assert plan.runtime_available and plan.stage=='global-settings-members' and plan.download_bytes==0
    assert plan.required_disk_bytes>=len(INI) and plan.source_proof is None and fixture.codec_calls==0
    result=fixture.download(plan)
    assert isinstance(result,PreparationStage) and not isinstance(result,SnapshotSource)
    assert result.restore_handle['stage']=='global-settings-source' and fixture.codec_calls==1
    _,artifact,documents=settings.retained(fixture.provider,result.restore_handle,fixture.ctx)
    entries=documents[0][0]['entries']
    assert [e['value'] for e in entries if e['key']=='ClientID']==['fixture','second ordered assignment']
    assert [e['operator'] for e in entries if e['key']=='Items']==['+','-']
    assert artifact['request']['content_mode']==mode and len(fixture.calls)==before
    fixture.context('plan').stage_handle=result.restore_handle
    gate=fixture.provider.plan(fixture.request,fixture.ctx)
    assert gate.stage=='global-settings-source' and not gate.runtime_available and gate.source_proof is None
    with pytest.raises(GameDataError) as error:fixture.provider.restore(result.restore_handle,fixture.context('restore'))
    assert error.value.code=='publisher_settings_profile_unresolved' and len(fixture.calls)==before


@pytest.mark.parametrize('failure',['throw','corrupt','cancel','changed-codec','consent'])
def test_decoder_failure_or_changed_consent_never_commits_settings_or_damages_old_data(tmp_path,apk_fixture,monkeypatch,failure):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch);plan=fixture.member_plan()
    old=tmp_path/'previous-data';old.write_bytes(b'keep previous data')
    if failure=='changed-codec':fixture.codec.identity={'schema':'different-codec'}
    elif failure=='consent':plan=replace(plan,required_disk_bytes=plan.required_disk_bytes+1)
    else:fixture.codec_failure=failure
    before=len(fixture.calls)
    with pytest.raises(GameDataError):fixture.download(plan)
    assert old.read_bytes()==b'keep previous data' and len(fixture.calls)==before
    root=fixture.ctx.cache_directory/'infinitynikki-global-settings'
    assert not list(root.glob('*.ini')) and not list(root.glob('pending-*'))


def test_retained_member_corruption_is_checked_without_decoder_or_network(tmp_path,apk_fixture,monkeypatch):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch)
    result=fixture.download(fixture.member_plan());before=(len(fixture.calls),fixture.codec_calls)
    path=next((fixture.ctx.cache_directory/'infinitynikki-global-settings').glob('*.ini'))
    path.write_bytes(path.read_bytes()+b'changed')
    fixture.context('plan').stage_handle=result.restore_handle
    with pytest.raises(GameDataError):fixture.provider.plan(fixture.request,fixture.ctx)
    assert (len(fixture.calls),fixture.codec_calls)==before


def test_pending_requote_refreshes_capability_identity_before_work(tmp_path,apk_fixture,monkeypatch):
    fixture=Fixture(tmp_path,apk_fixture,monkeypatch);first=fixture.member_plan()
    fixture.codec.identity={'schema':'new-authored-toolkit-codec'}
    fixture.context('plan').stage_handle=first.handle
    second=fixture.provider.plan(fixture.request,fixture.ctx)
    assert first.handle!=second.handle and fixture.codec_calls==0
    assert isinstance(fixture.download(second),PreparationStage)


@pytest.mark.parametrize('raw',[b'not an INI',b'[Other]\nx=y',b'[/Script/X6Game.X6PackageSettings]\nx\x00=y',
    b'[/Script/X6Game.X6PackageSettings]\n=value'])
def test_unknown_settings_schema_does_not_silently_skip_unparsed_lines(raw):
    with pytest.raises(GameDataError):settings.ordered_document(raw)


def test_utf16_sections_operators_and_duplicate_assignments_are_preserved():
    documents=settings.ordered_document(INI.decode().encode('utf-16'))
    assert len(documents)==1 and len(documents[0]['entries'])==6
