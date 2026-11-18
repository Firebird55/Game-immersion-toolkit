"""Quoted original Global configuration carriers, without profile selection."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .publisher_transport import STRONG_ETAG
from . import infinity_nikki_build_stage as build
from . import infinity_nikki_chunks as chunks
from . import infinity_nikki_inventory as inventory

POLICY='infinitynikki-global-configuration-sources/1'
STAGES={'global-configuration-packages','global-configuration-source'}
SUFFIXES=('.pak','.sig','.ucas','.udirhash','.utoc')
GATE=('The original configuration package files are verified. Their current native-compatible '
      'indices, selected ordered INI members and profile/keychain ownership still require preparation. '
      'No language library has been activated.')
QUOTE=('Download the official configuration package and its declared companion files. '
       'The size includes complete shared carriers, unused mixed content and generation checks; '
       'no optional voice package is selected. Index/settings/text/voice preparation follows separately.')


def _check(value):
    if not value:raise GameDataError('publisher_configuration_source_unverified',
        'Could not verify the current official configuration package source.')


def _path(ctx,digest,suffix='json'):
    _check(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and suffix in {'json','data'})
    path=Path(ctx.cache_directory).absolute()/'infinitynikki-global-configuration'/(digest+'.'+suffix)
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


def _selection(provider,previous,ctx):
    _,artifact,manifests=build._retained(provider,previous,ctx)
    descriptor,_=build._selection(provider,artifact,ctx)
    name='Default_Ini_'+descriptor['DefaultVersion']+'_P'
    candidates=[]
    for source,manifest in zip(('base','fastpatch'),manifests):
        files={file.name:file for file in manifest.files}
        if name+'.pak' in files:
            _check(all(name+suffix in files for suffix in SUFFIXES))
            candidates.append((source,manifest,manifest.plan([name+suffix for suffix in SUFFIXES])))
        else:
            _check(not any(name+suffix in files for suffix in SUFFIXES))
    if len(candidates)!=1:
        raise GameDataError('publisher_configuration_precedence_unresolved',
            'The current configuration package owner or update ordering still needs verification. Existing data is retained.',409)
    source,manifest,selection=candidates[0]
    _check(0<len(selection.chunks)<=64 and 221<=selection.files[0].size<=64*1024**2 and
           selection.retained_file_bytes<=80*1024**2)
    return source,manifest,selection


def _artifact_selection(provider,artifact,ctx):
    _check(isinstance(artifact,dict) and set(artifact)=={'policy','request','build_handle','source','pins'} and
           artifact['policy']==POLICY and artifact['request']==ctx.request.json())
    build._foundation()._handle(artifact['build_handle'],ctx.request)
    _check(artifact['build_handle']['stage']=='global-build-source')
    source,manifest,selection=_selection(provider,artifact['build_handle'],ctx)
    _check(artifact['source']==source and isinstance(artifact['pins'],list) and len(artifact['pins'])==len(selection.chunks))
    for pin,owner in zip(artifact['pins'],selection.chunks):
        _check(isinstance(pin,dict) and set(pin)=={'guid','url','total','etag','prefix'} and
               pin['guid']==owner.guid and pin['url']==owner.url and pin['total']==owner.packed_bytes and
               isinstance(pin['etag'],str) and STRONG_ETAG.fullmatch(pin['etag']) and
               isinstance(pin['prefix'],str) and re.fullmatch('[0-9a-f]{64}',pin['prefix']))
    return manifest,selection


def _quote(provider,artifact,handle,ctx):
    manifest,selection=_artifact_selection(provider,artifact,ctx)
    wire=selection.wire_bytes+32*len(selection.chunks)
    disk=wire+selection.retained_file_bytes+selection.temporary_decoded_bytes+len(build._json(artifact))+128*1024
    return GameDataPlan('global-configuration-'+manifest.source_sha256[:16],wire,disk,handle,
        runtime_available=True,stage='global-configuration-packages',message=QUOTE)


def _retained(provider,handle,ctx):
    receipt=_read(ctx,handle['receipt_sha256'])
    _check(isinstance(receipt,dict) and set(receipt)=={'policy','request','artifact_sha256','files','carriers'} and
           receipt['policy']==POLICY and receipt['request']==ctx.request.json())
    artifact=_read(ctx,receipt['artifact_sha256'])
    _,selection=_artifact_selection(provider,artifact,ctx)
    _check(isinstance(receipt['files'],list) and len(receipt['files'])==len(selection.files) and
           isinstance(receipt['carriers'],list) and len(receipt['carriers'])==len(selection.chunks))
    for row,owner,pin in zip(receipt['carriers'],selection.chunks,artifact['pins']):
        _check(isinstance(row,dict) and set(row)=={'guid','transfer','decoded_sha1_verified'} and
               row['guid']==owner.guid and row['decoded_sha1_verified'] is True and isinstance(row['transfer'],dict))
        info=row['transfer']
        _check(info.get('source_url_sha256')==build._sha(owner.url.encode()) and info.get('bytes')==owner.packed_bytes and
               isinstance(info.get('sha256'),str) and re.fullmatch('[0-9a-f]{64}',info['sha256']) and
               info.get('response_etag')==pin['etag'] and info.get('original_range') is None)
    for row,file in zip(receipt['files'],selection.files):
        _check(isinstance(row,dict) and set(row)=={'name','sha256','bytes'} and row['name']==file.name and row['bytes']==file.size)
        path=_path(ctx,row['sha256'],'data');_check(path.is_file() and path.stat().st_size==file.size)
        raw=path.read_bytes();_check(build._sha(raw)==row['sha256'] and hashlib.sha1(raw).digest()==file.sha1)
    return receipt,artifact,selection


def plan(provider,previous,ctx):
    ctx.check()
    if previous['stage']=='global-configuration-source':
        from .infinity_nikki_settings_index import plan_members
        return plan_members(provider,previous,ctx)
    if previous['stage']=='global-configuration-packages':
        old=_read(ctx,previous['receipt_sha256']);_artifact_selection(provider,old,ctx)
        previous=old['build_handle']
    _check(previous['stage']=='global-build-source')
    source,_,selection=_selection(provider,previous,ctx)
    transport=provider.transport_factory(ctx,hosts=set(inventory.RESOURCE_HOSTS))
    pins=[]
    for owner in selection.chunks:
        prefix,info=transport.fetch_bytes(owner.url,limit=32,expected_size=32,kind='metadata',
            original_range=(0,32,owner.packed_bytes))
        _check(info.response_etag is not None and STRONG_ETAG.fullmatch(info.response_etag))
        pins.append({'guid':owner.guid,'url':owner.url,'total':owner.packed_bytes,'etag':info.response_etag,'prefix':prefix.hex()})
    artifact={'policy':POLICY,'request':ctx.request.json(),'build_handle':previous,'source':source,'pins':pins}
    digest=_store(ctx,artifact)
    handle={'policy':build._foundation().POLICY,'request':ctx.request.json(),
        'stage':'global-configuration-packages','receipt_sha256':digest}
    return _quote(provider,artifact,handle,ctx)


def download(provider,consent,ctx):
    if consent.handle['stage']=='global-configuration-source':
        _retained(provider,consent.handle,ctx)
        raise GameDataError('publisher_configuration_index_reader_unresolved',GATE,409)
    _check(consent.stage==consent.handle['stage']=='global-configuration-packages')
    artifact=_read(ctx,consent.handle['receipt_sha256'])
    _check(consent==_quote(provider,artifact,consent.handle,ctx))
    _,selection=_artifact_selection(provider,artifact,ctx)
    transport=provider.transport_factory(ctx,hosts=set(inventory.RESOURCE_HOSTS))
    root=_path(ctx,consent.handle['receipt_sha256']).parent
    carriers=[];records=[];decoded={}
    with tempfile.TemporaryDirectory(dir=root,prefix='pending-') as folder:
        for pin,owner in zip(artifact['pins'],selection.chunks):
            target=Path(folder)/(owner.guid+'.chunk')
            info=transport.download_to(owner.url,target,limit=owner.packed_bytes,expected_size=owner.packed_bytes,
                kind='asset',headers={'If-Match':pin['etag']})
            raw=target.read_bytes();_check(raw[:32].hex()==pin['prefix'])
            decoded[owner.guid]=chunks.decode_chunk(raw,owner)
            after,_=transport.fetch_bytes(owner.url,limit=32,expected_size=32,kind='metadata',
                original_range=(0,32,owner.packed_bytes),headers={'If-Match':pin['etag']})
            _check(after.hex()==pin['prefix'])
            carriers.append({'guid':owner.guid,'transfer':info.json(),'decoded_sha1_verified':True})
        for file in selection.files:
            raw=chunks.read_small_file(file,decoded.__getitem__);digest=build._sha(raw)
            target=Path(folder)/(digest+'.data');build._foundation()._save(target,raw)
            records.append({'name':file.name,'sha256':digest,'bytes':len(raw)})
        ctx.check()
        for row in records:
            target=Path(folder)/(row['sha256']+'.data');destination=_path(ctx,row['sha256'],'data')
            if destination.exists():_check(build._sha(destination.read_bytes())==row['sha256'])
            else:build._foundation().atomic_replace(target,destination)
        digest=_store(ctx,{'policy':POLICY,'request':ctx.request.json(),'artifact_sha256':consent.handle['receipt_sha256'],
            'files':records,'carriers':carriers})
        ctx.check()
    return PreparationStage({'policy':build._foundation().POLICY,'request':ctx.request.json(),
        'stage':'global-configuration-source','receipt_sha256':digest},GATE)


def restore(provider,handle,ctx):
    if handle['stage']=='global-configuration-source':_retained(provider,handle,ctx)
    else:_artifact_selection(provider,_read(ctx,handle['receipt_sha256']),ctx)
    raise GameDataError('publisher_configuration_index_reader_unresolved',GATE,409)
