"""Actual authored source files/TOC/graph contracts, never a native build."""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
import weakref

import pytest

from backend.tests.test_runtime_experiment import recorder


@pytest.fixture
def source_toy(tmp_path, monkeypatch):
    m = recorder(monkeypatch)
    monkeypatch.setitem(sys.modules, 'record_runtime', m)
    root = tmp_path.resolve()
    source, evidence, output = (root / x for x in ('source', 'evidence', 'output'))
    for p in (source, evidence, output): p.mkdir()
    names = m.SOURCE_CONTROLS | m.SOURCE_WORKERS | {'backend/entry.py', 'backend/unused.py'}
    for name in names:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'' if name == 'scripts/__init__.py' else b'# authored source \xe6\xbc\xa2\xe5\xad\x97\r\n')
    value = {'source_commit': 'a'*40, 'build_id': 'authored-source-map', 'profile': 'runtime-experiment',
        'components': [], 'resources': [{'path': 'scripts/check-capture-readiness.py',
            'sha256': hashlib.sha256((source/'scripts/check-capture-readiness.py').read_bytes()).hexdigest()}]}
    manifest = root / 'inputs.json'; manifest.write_text(json.dumps(value))
    snapshots = []
    def snapshot(path, expected):
        assert path == source and expected == value['source_commit']
        snapshots.append(True)
        return {'head': expected, 'clean': True, 'sourceStatus': 'available', 'sourceIssue': None}
    monkeypatch.setattr(m, 'source_snapshot', snapshot)
    monkeypatch.setattr(m, 'source_tracked', lambda _: sorted(names))
    m.begin_project_sources(value, source, evidence, manifest)
    native = {key: value[key] for key in ('source_commit', 'build_id', 'profile')}
    native['build_inputs'] = m.native_file_identity(manifest)
    (output/m.NATIVE_SOURCE_FINAL).write_text(json.dumps(native))
    return SimpleNamespace(m=m, root=root, source=source, evidence=evidence, output=output,
        value=value, manifest=manifest, names=names, snapshots=snapshots)


def observer(t):
    return t.m.ProjectSourceObservation(t.value, t.source, t.evidence, t.manifest)


def analysis(t, *, pure=(), scripts=(), nodes=None):
    return SimpleNamespace(pure=list(pure), scripts=list(scripts),
        graph=SimpleNamespace(find_node=lambda name: (nodes or {}).get(name)))


def complete(t, o=None):
    o = o or observer(t)
    for name in ('main', 'asr'):
        o.observe_analysis(name, analysis(t, pure=[('backend.entry', str(t.source/'backend/entry.py'), 'PYMODULE')],
            scripts=[('entry', str(t.source/'backend/entry.py'), 'PYSOURCE')]))
    o.finish()
    return t.m.finalize_project_sources(t.value, t.source, t.evidence, t.output, t.manifest)


def test_fixed_script_workers_and_empty_package_are_recorded_from_actual_roles(source_toy):
    t=source_toy; o=observer(t)
    rows=[('worker'+str(i),str(t.source/name),'PYMODULE') for i,name in enumerate(sorted(t.m.SOURCE_WORKERS))
        if name != 'scripts/check-capture-readiness.py']
    o.observe_analysis('main',analysis(t,pure=rows));o.observe_analysis('asr',analysis(t));o.finish()
    report=t.m.finalize_project_sources(t.value,t.source,t.evidence,t.output,t.manifest)
    assert t.m.validate_source_report(report) is report
    records={x['path']:x for x in report['records']}
    assert records['scripts/__init__.py']['raw']['bytes']==0
    assert records['scripts/check-capture-readiness.py']['roles']==['runtime-script-resource']
    assert set(t.m.SOURCE_WORKERS)<=set(records) and 'backend/unused.py' not in records
    assert all(x['raw']['bytes']>x['canonical_lf']['bytes'] for n,x in records.items() if n!='scripts/__init__.py')
    assert report['source_before_sha256']==report['source_after_sha256']


def test_same_project_origin_merges_main_asr_script_and_pure_roles(source_toy):
    t=source_toy; report=complete(t)
    row=next(x for x in report['records'] if x['path']=='backend/entry.py')
    assert row['roles']==['asr-pure','asr-script','main-pure','main-script']
    assert 'backend/unused.py' not in {x['path'] for x in report['records']}
    assert report['compiled_code_identity']=='unverified' and report['r19_complete'] is False


def test_conflicting_origin_for_same_toc_name_is_refused(source_toy):
    t=source_toy;o=observer(t)
    with pytest.raises(t.m.SourceInputError,match='invalid-identity'):
        o.observe_analysis('main',analysis(t,pure=[('entry',str(t.source/'backend/entry.py'),'PYMODULE'),
            ('entry',str(t.source/'backend/unused.py'),'PYMODULE')]))


def test_changed_closed_worker_table_cannot_expand_source_eligibility(source_toy,monkeypatch):
    from backend.runtime_bundle import CHILD_TARGETS
    t=source_toy;before=(t.evidence/t.m.SOURCE_BASELINE).read_bytes()
    monkeypatch.setitem(CHILD_TARGETS,'authored-unreviewed',('module','scripts.unreviewed'))
    monkeypatch.setattr(t.m,'source_text_identity',lambda *a,**k:pytest.fail('Read source after target identity changed'))
    with pytest.raises(t.m.SourceInputError,match='invalid-identity'):
        t.m.begin_project_sources(t.value,t.source,t.evidence,t.manifest)
    assert (t.evidence/t.m.SOURCE_BASELINE).read_bytes()==before


@pytest.mark.parametrize('kind',['unknown-script','outside','cache-only'])
def test_unknown_script_target_refuses_before_unknown_metadata_or_open(source_toy,monkeypatch,kind):
    t=source_toy;o=observer(t)
    path={'unknown-script':t.source/'scripts/private-unlisted.py','outside':t.root/'private.py',
        'cache-only':t.source/'backend/__pycache__/entry.pyc'}[kind]
    original=[Path.stat,Path.lstat,Path.open];access=[]
    def guard(function):
        def call(p,*args,**kwargs):
            if p==path:access.append(True);pytest.fail('Unknown origin IO')
            return function(p,*args,**kwargs)
        return call
    for label,function in zip(('stat','lstat','open'),original):monkeypatch.setattr(Path,label,guard(function))
    with pytest.raises(t.m.SourceInputError,match='unmapped-origin'):
        o.observe_analysis('main',analysis(t,pure=[('unknown',str(path),'PYMODULE')]))
    assert not access and not (t.output/t.m.SOURCE_PUBLIC).exists()


def test_pinned_namespace_graph_node_is_counted_generated_without_file_io(source_toy):
    from PyInstaller.lib.modulegraph.modulegraph import NamespacePackage
    t=source_toy;o=observer(t);node=NamespacePackage('authored.namespace');node.filename='-'
    o.observe_analysis('main',analysis(t,pure=[('authored.namespace','-','PYMODULE')],nodes={'authored.namespace':node}))
    o.observe_analysis('asr',analysis(t));o.finish()
    report=t.m.finalize_project_sources(t.value,t.source,t.evidence,t.output,t.manifest)
    assert report['excluded_origin_counts']=={'supplier':0,'builtin':0,'namespace_generated':1}
    assert all(x['path']!='-' for x in report['records'])


@pytest.mark.parametrize('origin',['-',None,''])
def test_dash_or_none_with_wrong_graph_type_is_unavailable(source_toy,origin):
    t=source_toy;o=observer(t)
    fake=type('NamespacePackage',(),{'identifier':'fake','filename':'-','code':None})()
    with pytest.raises(t.m.SourceInputError,match='unmapped-origin'):
        o.observe_analysis('main',analysis(t,pure=[('fake',origin,'PYMODULE')],nodes={'fake':fake}))


def test_namespace_marker_never_becomes_builtin_or_source_bytes(source_toy):
    from PyInstaller.lib.modulegraph.modulegraph import BuiltinModule
    t=source_toy;o=observer(t);node=BuiltinModule('authored_builtin')
    with pytest.raises(t.m.SourceInputError,match='unmapped-origin'):
        o.observe_analysis('main',analysis(t,pure=[('authored_builtin','-','PYMODULE')],nodes={'authored_builtin':node}))


@pytest.mark.parametrize('change',['source','manifest','baseline','toc'])
def test_before_after_source_or_manifest_change_refuses_publication(source_toy,change):
    t=source_toy;o=observer(t);main=analysis(t,pure=[('entry',str(t.source/'backend/entry.py'),'PYMODULE')])
    o.observe_analysis('main',main);o.observe_analysis('asr',analysis(t))
    if change=='toc':main.pure.append(('unseen','-','PYMODULE'))
    if change=='toc':
        with pytest.raises(t.m.SourceInputError):o.finish()
    else:
        o.finish()
        target={'source':t.source/'backend/entry.py','manifest':t.manifest,'baseline':t.evidence/t.m.SOURCE_BASELINE}[change]
        target.write_bytes(target.read_bytes()+b' ')
        with pytest.raises(t.m.SourceInputError):
            t.m.finalize_project_sources(t.value,t.source,t.evidence,t.output,t.manifest)
    assert not (t.output/t.m.SOURCE_PUBLIC).exists()


def test_unsafe_parent_is_rejected_before_descendant_stat_lstat_or_open(source_toy,monkeypatch):
    t=source_toy;o=observer(t);folder=t.source/'backend';old=t.source/'old-backend';folder.rename(old)
    folder.symlink_to(old,target_is_directory=True);leaf=folder/'entry.py';access=[]
    def guard(function):
        def call(p,*a,**k):
            if p==leaf:access.append(True);pytest.fail('Linked-parent descendant metadata')
            return function(p,*a,**k)
        return call
    for name in ('stat','lstat','open'):monkeypatch.setattr(Path,name,guard(getattr(Path,name)))
    with pytest.raises(t.m.SourceInputError):o.observe_analysis('main',analysis(t,pure=[('entry',str(leaf),'PYMODULE')]))
    assert access==[]


def test_source_stream_close_fault_retains_original_object_and_error(source_toy,monkeypatch):
    t=source_toy;path=t.source/'backend/entry.py';original=Path.open;error=OSError('authored-private-close')
    refs=[]
    class Fault:
        def __init__(self,raw):self.raw=raw
        def fileno(self):return self.raw.fileno()
        def read(self,n):return self.raw.read(n)
        def close(self):raise error
    def opened(p,*a,**k):
        raw=original(p,*a,**k)
        if p!=path:return raw
        value=Fault(raw);refs.append(weakref.ref(value));return value
    monkeypatch.setattr(Path,'open',opened)
    try:
        with pytest.raises(t.m.SourceInputError,match='cleanup-unconfirmed'):t.m.source_text_identity(path)
        assert refs[0]() is t.m._SOURCE_HELD[-1][0] and t.m._SOURCE_HELD[-1][2] is error
        assert not refs[0]().raw.closed and not (t.output/t.m.SOURCE_PUBLIC).exists()
    finally:
        if refs and refs[0]() is not None:refs[0]().raw.close()


@pytest.mark.parametrize('field,value',[('rights_approval',0),('source_clean_after',1),('records_sha256','0'*64),('analyses',{'main':'observed'}),('extra','private')])
def test_source_report_closed_types_caps_and_no_overwrite_readback(source_toy,field,value):
    t=source_toy;report=complete(t);bad=deepcopy(report);bad[field]=value
    with pytest.raises(t.m.SourceInputError):t.m.validate_source_report(bad)
    path=t.output/t.m.SOURCE_PUBLIC;before=path.read_bytes()
    with pytest.raises(t.m.SourceInputError):t.m.source_write(t.output,t.m.SOURCE_PUBLIC,{'private':'never published'})
    assert path.read_bytes()==before


def test_code_cache_identity_remains_unverified_even_with_stable_origins(source_toy):
    t=source_toy;o=observer(t);main=analysis(t,pure=[('entry',str(t.source/'backend/entry.py'),'PYMODULE')])
    main.code_cache={'entry':compile('raise RuntimeError("authored unrelated code")','authored','exec')}
    o.observe_analysis('main',main);o.observe_analysis('asr',analysis(t));o.finish()
    report=t.m.finalize_project_sources(t.value,t.source,t.evidence,t.output,t.manifest)
    assert report['compiled_code_identity']=='unverified' and 'compiled bytecode' in report['coverage']


@pytest.mark.parametrize('issue',['hidden-index-entries','git-source-transforms','unset','filter','ident','working-tree-encoding'])
def test_source_visibility_flags_and_transform_states_never_claim_clean(source_toy,issue):
    t=source_toy
    value={'head':t.value['source_commit'],'clean':True,'sourceStatus':'unavailable','sourceIssue':issue}
    with pytest.raises(t.m.SourceInputError):t.m.validate_source_snapshot(value,t.value['source_commit'])
    value['sourceStatus']='available'
    with pytest.raises(t.m.SourceInputError):t.m.validate_source_snapshot(value,t.value['source_commit'])


def test_existing_git_visibility_helpers_detect_owned_index_flags_and_unset_attributes(tmp_path,monkeypatch):
    m=recorder(monkeypatch); helper=(Path(__file__).resolve().parents[2]/'scripts/check-evidence.mjs').read_bytes()
    original_run=subprocess.run
    env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
    for case in ('assume-unchanged','skip-worktree','filter','ident','working-tree-encoding'):
        source=tmp_path.resolve()/case; (source/'scripts').mkdir(parents=True);(source/'backend').mkdir()
        (source/'scripts/check-evidence.mjs').write_bytes(helper);(source/'backend/entry.py').write_bytes(b'# owned source\n')
        for args in (['init','-q'],['-c','core.attributesFile='+os.devnull,'add','scripts/check-evidence.mjs','backend/entry.py']):
            result=original_run(['git',*args],cwd=source,env=env,capture_output=True,timeout=5)
            assert result.returncode==0,'Owned Git fixture preparation failed'
        if case in ('assume-unchanged','skip-worktree'):
            result=original_run(['git','update-index','--'+case,'backend/entry.py'],cwd=source,env=env,capture_output=True,timeout=5)
            assert result.returncode==0,'Owned Git fixture flag setup failed'
        else:
            # Add happens before the authored attribute exists: no filter or
            # encoding driver is executed even in this private fixture.
            (source/'.gitattributes').write_text('backend/entry.py -'+case+'\n')
        observed=[]
        def run(args,**kw):
            result=original_run(args,env=env,**kw)
            observed.append(json.loads(result.stdout));return result
        with monkeypatch.context()as patch:
            patch.setattr(m.subprocess,'run',run)
            with pytest.raises(m.SourceInputError):m.source_snapshot(source,'a'*40)
        assert observed==[{'head':None,'clean':False,'sourceStatus':'unavailable',
            'sourceIssue':'hidden-index-entries'if case in('assume-unchanged','skip-worktree')else'git-source-transforms'}]


@pytest.mark.parametrize('bad',[[],None,{'private-authored-key':['private-authored-value']}])
def test_malformed_private_baseline_is_a_closed_refusal_without_public_map(source_toy,bad):
    t=source_toy;(t.evidence/t.m.SOURCE_BASELINE).write_text(json.dumps(bad))
    with pytest.raises(t.m.SourceInputError,match='invalid-identity') as caught:observer(t)
    assert 'private-authored' not in str(caught.value) and not(t.output/t.m.SOURCE_PUBLIC).exists()


def test_source_header_and_baseline_key_type_substitutions_are_closed(source_toy):
    t=source_toy
    for value in ({**t.value,'source_commit':1},{**t.value,'build_id':['private-authored']},None):
        with pytest.raises(t.m.SourceInputError,match='invalid-identity'):t.m.source_headers(value)
    bad=deepcopy(t.m.source_json(t.evidence/t.m.SOURCE_BASELINE)['files']);bad[1]=next(iter(bad.values()))
    with pytest.raises(t.m.SourceInputError,match='invalid-identity'):t.m.validate_source_baseline_files(bad)


def test_missing_baseline_required_source_pipeline_refuses_before_native_constructor(source_toy,monkeypatch):
    t=source_toy;(t.evidence/t.m.SOURCE_BASELINE).unlink()
    repository=Path(__file__).resolve().parents[2]
    monkeypatch.setenv('PROXY_RUNTIME_BUILD_INPUTS',str(t.manifest));monkeypatch.setenv('PROXY_RUNTIME_EVIDENCE_ROOT',str(t.evidence))
    hooks=SimpleNamespace(collect_data_files=lambda *_a,**_k:[],collect_dynamic_libs=lambda *_a,**_k:[],collect_submodules=lambda *_a,**_k:[],copy_metadata=lambda *_a,**_k:[])
    monkeypatch.setitem(sys.modules,'PyInstaller.utils.hooks',hooks)
    monkeypatch.setitem(sys.modules,'PyInstaller.config',SimpleNamespace(CONF={'workpath':str(t.root)}))
    def forbidden(*a,**k):pytest.fail('Native/freezer caller reached without required source baseline')
    monkeypatch.setattr(t.m,'NativeCollectionObservation',forbidden)
    with pytest.raises(t.m.SourceInputError):
        runpy.run_path(str(repository/'packaging/runtime-bundle/runtime.spec'),init_globals={'SPECPATH':str(repository/'packaging/runtime-bundle'),'DISTPATH':str(t.output),'Analysis':forbidden,'PYZ':forbidden,'EXE':forbidden,'COLLECT':forbidden})


@pytest.mark.parametrize('unknown',[False,True])
def test_actual_spec_source_pipeline_positive_and_unknown_refusal_before_native_work(source_toy,monkeypatch,unknown):
    t=source_toy;repository=Path(__file__).resolve().parents[2];native_calls=[]
    monkeypatch.setenv('PROXY_RUNTIME_BUILD_INPUTS',str(t.manifest));monkeypatch.setenv('PROXY_RUNTIME_EVIDENCE_ROOT',str(t.evidence))
    hooks=SimpleNamespace(collect_data_files=lambda *_a,**_k:[],collect_dynamic_libs=lambda *_a,**_k:[],collect_submodules=lambda *_a,**_k:[],copy_metadata=lambda *_a,**_k:[])
    monkeypatch.setitem(sys.modules,'PyInstaller.utils.hooks',hooks)
    monkeypatch.setitem(sys.modules,'PyInstaller.config',SimpleNamespace(CONF={'workpath':str(t.root)}))
    # This fixture has no PE/native payload. Only the actual source observer is
    # under test; native callbacks are tripwires for its failure ordering.
    class NativeNotTested:
        def __init__(self,*a):pass
        def observe_analysis(self,*a):native_calls.append('analysis')
        def observe_generated(self,*a):native_calls.append('generated')
        def finish(self):native_calls.append('finish')
    monkeypatch.setattr(t.m,'NativeCollectionObservation',NativeNotTested)
    def selected(*a,**k):
        path=t.source/('scripts/unreviewed.py'if unknown else'backend/entry.py')
        value=analysis(t,pure=[('entry',str(path),'PYMODULE')],scripts=[('entry',str(t.source/'backend/entry.py'),'PYSOURCE')])
        value.datas,value.binaries=[],[]
        return value
    def pyz(*a):
        if unknown:pytest.fail('PYZ ran after an unknown source')
        return None
    args={'SPECPATH':str(t.source/'packaging/runtime-bundle'),'DISTPATH':str(t.output),'Analysis':selected,'PYZ':pyz,'EXE':lambda *a,**k:SimpleNamespace(name='authored-not-native'),'COLLECT':lambda *a,**k:None}
    if unknown:
        with pytest.raises(t.m.SourceInputError,match='unmapped-origin'):runpy.run_path(str(repository/'packaging/runtime-bundle/runtime.spec'),init_globals=args)
        assert native_calls==[] and not(t.evidence/t.m.SOURCE_OBSERVATION).exists()
    else:
        runpy.run_path(str(repository/'packaging/runtime-bundle/runtime.spec'),init_globals=args)
        report=t.m.finalize_project_sources(t.value,t.source,t.evidence,t.output,t.manifest)
        assert t.m.check_project_sources(t.value,t.source,t.evidence,t.output,t.manifest)==report
        assert native_calls==['analysis','generated','analysis','generated','finish']


def test_sink_close_fault_has_no_public_name_and_retains_actual_stream(source_toy,monkeypatch):
    t=source_toy;original=Path.open;refs=[];error=OSError('authored sink close')
    class Fault:
        def __init__(self,raw):self.raw=raw
        def fileno(self):return self.raw.fileno()
        def write(self,raw):return self.raw.write(raw)
        def flush(self):return self.raw.flush()
        def close(self):raise error
    def opened(path,*a,**k):
        raw=original(path,*a,**k)
        if not(path.parent==t.output and path.name.endswith('.private')):return raw
        value=Fault(raw);refs.append(weakref.ref(value));return value
    monkeypatch.setattr(Path,'open',opened)
    try:
        with pytest.raises(t.m.SourceInputError,match='cleanup-unconfirmed'):t.m.source_write(t.output,t.m.SOURCE_PUBLIC,{'authored':'private'})
        assert not(t.output/t.m.SOURCE_PUBLIC).exists() and refs[0]() is t.m._SOURCE_HELD[-1][0]
        assert t.m._SOURCE_HELD[-1][1] is error and not refs[0]().raw.closed
    finally:
        if refs and refs[0]() is not None:refs[0]().raw.close()


def test_source_file_and_aggregate_caps_refuse_before_content_read(source_toy,monkeypatch):
    t=source_toy;path=t.source/'backend/entry.py';path.write_bytes(b'authored bounded content')
    with pytest.raises(t.m.SourceInputError,match='limit-exceeded'):t.m.source_read(path,limit=4)
    report=complete_after_restoring_source(t,path)
    report['records'][0]['raw']['bytes']=t.m.SOURCE_LIMIT+1
    with pytest.raises(t.m.SourceInputError):t.m.validate_source_report(report)


def complete_after_restoring_source(t,path):
    path.write_bytes(b'# authored source \xe6\xbc\xa2\xe5\xad\x97\r\n')
    return complete(t)
