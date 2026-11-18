"""Normal source-owned settings-member preparation; no regional CMS selection."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

from .game_data_protocol import GameDataError,GameDataPlan,PreparationStage
from .private_data_paths import _no_links
from . import infinity_nikki_build_stage as build
from . import infinity_nikki_configuration_stage as configuration
from . import infinity_nikki_settings_index as index

POLICY='infinitynikki-global-settings-members/1'
STAGES={'global-settings-members','global-settings-source'}
GATE=('Original settings members and ordered assignments are prepared. Effective regional '
      'settings, CMS response/current-keychain validation and text/voice preparation remain. '
      'No language library has been activated.')
QUOTE=('Prepare the original settings files already present in the verified configuration package. '
       'No additional download is required. Ordered settings are retained without selecting a regional '
       'profile or contacting CMS; text and voice require later preparation.')


def _check(value):
    if not value:raise GameDataError('publisher_settings_unverified',
        'Could not verify the current official settings members. Existing data is retained.')


class _Plain:
    identity={'schema':'toolkit-uncompressed-settings/1'}
    def decode(self,blocks,**options):
        _check(not blocks);return b''


def compression(provider,methods):
    if methods==['None']:return _Plain()
    if any(method not in ('None','Oodle') for method in methods):return None
    from .publisher_oodle import create_compression
    return create_compression(platform=provider.platform)


def _path(ctx,digest,suffix='json'):
    _check(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and suffix in {'json','ini'})
    path=Path(ctx.cache_directory).absolute()/'infinitynikki-global-settings'/(digest+'.'+suffix)
    _no_links(path)
    return path


def _store(ctx,value):
    raw=build._json(value);_check(len(raw)<=1024**2)
    digest=build._sha(raw);ctx.check();build._foundation()._save(_path(ctx,digest),raw)
    return digest


def _read(ctx,digest):
    path=_path(ctx,digest);_check(path.is_file() and 0<path.stat().st_size<=1024**2)
    raw=path.read_bytes();_check(build._sha(raw)==digest)
    return json.loads(raw,object_pairs_hook=build.release._unique_object)


def ordered_document(raw):
    """Preserve section/assignment order and operators; never merge profiles."""
    _check(isinstance(raw,bytes) and 0<len(raw)<=128*1024)
    try:
        text=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
        _check('\0' not in text)
        sections=[];current=None
        for number,line in enumerate(text.splitlines(),1):
            value=line.strip()
            if not value or value.startswith((';','#')):continue
            if value.startswith('[') and value.endswith(']'):
                name=value[1:-1];_check(bool(name));current={'name':name,'line':number,'entries':[]};sections.append(current)
            else:
                _check(current is not None and '=' in value)
                key,value=value.split('=',1);key=key.strip();_check(bool(key))
                operator=key[0] if key[0] in '+-.!' else ''
                bare=key[1:] if operator else key;_check(bool(bare))
                current['entries'].append({'key':bare,'operator':operator,'value':value.strip(),'line':number})
        _check(any(section['name']=='/Script/X6Game.X6PackageSettings' for section in sections))
        return sections
    except (UnicodeError,RecursionError) as error:
        raise GameDataError('publisher_settings_schema_unresolved',
            'The current original settings encoding or assignment schema still needs verification.',409) from error


def _description(selected):
    row,_,paths,entries,decoded,methods=selected
    return {'pak_sha256':row['sha256'],'decoded_bytes':decoded,'methods':methods,
        'members':[{'path':path,'bytes':entry.expanded_bytes} for path,entry in zip(paths,entries)]}


def _quote(artifact,handle):
    return GameDataPlan('global-settings-'+artifact['selection']['pak_sha256'][:16],0,
        artifact['selection']['decoded_bytes']+len(build._json(artifact))+128*1024,handle,
        runtime_available=True,stage='global-settings-members',message=QUOTE)


def begin(provider,previous,ctx,*,selected=None,codec=None):
    selected=selected or index.selection(provider,previous,ctx)
    codec=codec or compression(provider,selected[-1])
    if codec is None:raise GameDataError('publisher_codec_unavailable','The owned settings decoder is unavailable.',409)
    artifact={'policy':POLICY,'request':ctx.request.json(),'configuration_handle':previous,
        'selection':_description(selected),'codec_identity':codec.identity}
    digest=_store(ctx,artifact)
    handle={'policy':build._foundation().POLICY,'request':ctx.request.json(),
        'stage':'global-settings-members','receipt_sha256':digest}
    return _quote(artifact,handle)


def _artifact(ctx,handle):
    artifact=_read(ctx,handle['receipt_sha256'])
    _check(isinstance(artifact,dict) and set(artifact)=={'policy','request','configuration_handle','selection','codec_identity'} and
        artifact['policy']==POLICY and artifact['request']==ctx.request.json())
    build._foundation()._handle(artifact['configuration_handle'],ctx.request)
    _check(artifact['configuration_handle']['stage']=='global-configuration-source')
    return artifact


def retained(provider,handle,ctx):
    receipt=_read(ctx,handle['receipt_sha256'])
    _check(isinstance(receipt,dict) and set(receipt)=={'policy','request','artifact_sha256','members'} and
        receipt['policy']==POLICY and receipt['request']==ctx.request.json())
    artifact=_artifact(ctx,{'receipt_sha256':receipt['artifact_sha256']})
    configuration._retained(provider,artifact['configuration_handle'],ctx)
    _check(isinstance(receipt['members'],list) and len(receipt['members'])==len(artifact['selection']['members']))
    documents=[]
    for row,owner in zip(receipt['members'],artifact['selection']['members']):
        _check(isinstance(row,dict) and set(row)=={'path','bytes','sha256','member_sha1','member_sha1_verified'} and
            row['path']==owner['path'] and row['bytes']==owner['bytes'] and row['member_sha1_verified'] is True)
        path=_path(ctx,row['sha256'],'ini');_check(path.is_file() and path.stat().st_size==row['bytes'])
        raw=path.read_bytes();_check(build._sha(raw)==row['sha256'] and hashlib.sha1(raw).hexdigest()==row['member_sha1'])
        documents.append(ordered_document(raw))
    # Sensitive source values remain private data. The return is never a DTO.
    return receipt,artifact,documents


def plan(provider,previous,ctx):
    ctx.check()
    if previous['stage']=='global-settings-source':
        retained(provider,previous,ctx)
        return GameDataPlan('global-settings-profile-reader',0,0,previous,stage='global-settings-source',message=GATE)
    artifact=_artifact(ctx,previous)
    return begin(provider,artifact['configuration_handle'],ctx)


def download(provider,consent,ctx):
    if consent.handle['stage']=='global-settings-source':
        retained(provider,consent.handle,ctx)
        raise GameDataError('publisher_settings_profile_unresolved',GATE,409)
    _check(consent.stage==consent.handle['stage']=='global-settings-members')
    artifact=_artifact(ctx,consent.handle);_check(consent==_quote(artifact,consent.handle))
    selected=index.selection(provider,artifact['configuration_handle'],ctx)
    _check(_description(selected)==artifact['selection'])
    codec=compression(provider,selected[-1])
    if codec is None:raise GameDataError('publisher_codec_unavailable','The owned settings decoder is unavailable.',409)
    _check(codec.identity==artifact['codec_identity'])
    _,archive,paths,entries,_,_=selected
    root=_path(ctx,consent.handle['receipt_sha256']).parent;records=[]
    with tempfile.TemporaryDirectory(dir=root,prefix='pending-') as folder:
        raw_members=archive.read_many(paths,decompress=lambda blocks:codec.decode(blocks,work=Path(folder),check=ctx.check))
        _check(len(raw_members)==len(paths))
        for path,entry,raw in zip(paths,entries,raw_members):
            ctx.check();_check(len(raw)==entry.expanded_bytes);ordered_document(raw)
            digest=build._sha(raw);build._foundation()._save(Path(folder)/(digest+'.ini'),raw)
            records.append({'path':path,'bytes':len(raw),'sha256':digest,'member_sha1':hashlib.sha1(raw).hexdigest(),
                'member_sha1_verified':True})
        ctx.check()
        for row in records:
            source=Path(folder)/(row['sha256']+'.ini');destination=_path(ctx,row['sha256'],'ini')
            if destination.exists():_check(build._sha(destination.read_bytes())==row['sha256'])
            else:build._foundation().atomic_replace(source,destination)
        digest=_store(ctx,{'policy':POLICY,'request':ctx.request.json(),'artifact_sha256':consent.handle['receipt_sha256'],
            'members':records})
        ctx.check()
    return PreparationStage({'policy':build._foundation().POLICY,'request':ctx.request.json(),
        'stage':'global-settings-source','receipt_sha256':digest},GATE)


def restore(provider,handle,ctx):
    if handle['stage']=='global-settings-source':retained(provider,handle,ctx)
    else:
        artifact=_artifact(ctx,handle);configuration._retained(provider,artifact['configuration_handle'],ctx)
    raise GameDataError('publisher_settings_profile_unresolved',GATE,409)
