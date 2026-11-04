"""The external reporter never substitutes its backend or grants release acceptance."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'scripts/diagnose-native-reader-tag.py'


def module():
    spec = importlib.util.spec_from_file_location('tag_diagnostic', RUNNER)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def authored_checkout(tmp_path):
    source = tmp_path / 'tag'
    (source / 'backend').mkdir(parents=True)
    (source / 'backend/__init__.py').write_text('')
    (source / 'backend/marker.py').write_text("ORIGIN = 'tagged'\n")
    reporter = tmp_path / 'reporter/scripts/probe.py'
    reporter.parent.mkdir(parents=True)
    (reporter.parent.parent / 'backend').mkdir()
    (reporter.parent.parent / 'backend/__init__.py').write_text('')
    (reporter.parent.parent / 'backend/marker.py').write_text("raise AssertionError('wrong backend imported')\n")
    reporter.write_text('''
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.marker import ORIGIN
def probe(helper, resources, observation):
    assert ORIGIN == 'tagged'
    assert (ROOT / 'backend/marker.py').read_text().startswith('ORIGIN')
    return {'passed': True, 'authored_origin': ORIGIN}
''')
    return source, reporter


def isolated(script, *arguments):
    result = subprocess.run([sys.executable, '-I', '-c', script, str(RUNNER), *map(str, arguments)],
                            text=True, capture_output=True, timeout=30, check=True)
    return json.loads(result.stdout)


IMPORT = '''
import importlib.util,json,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('diagnostic',sys.argv[1])
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
'''


def test_external_probe_imports_only_tag_backend_and_cannot_approve_release(tmp_path):
    source, reporter = authored_checkout(tmp_path)
    before = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob('*.py')}
    result = isolated(IMPORT + '''
m.subprocess.check_output=lambda *a,**kw: m.SOURCE+'\\n'
print(json.dumps(m.diagnose(Path(sys.argv[2]),Path(sys.argv[2]),Path(sys.argv[2]),reporter=Path(sys.argv[3]))))
''', source, reporter)
    assert result['passed'] is True
    assert result['probe']['authored_origin'] == 'tagged'
    assert result['diagnostic_only'] is True
    assert result['release_eligible'] is False
    assert result['native_acceptance'] == 'not-established'
    assert result['tag'] == 'v0.23.0'
    assert len(result['reporter_sha256']) == 64
    assert before == {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob('*.py')}


def test_preimported_other_backend_is_refused(tmp_path):
    source, reporter = authored_checkout(tmp_path)
    result = isolated(IMPORT + '''
sys.path.insert(0,str(Path(sys.argv[3]).parents[1]))
import backend
m.subprocess.check_output=lambda *a,**kw: m.SOURCE+'\\n'
print(json.dumps(m.diagnose(Path(sys.argv[2]),Path(sys.argv[2]),Path(sys.argv[2]),reporter=Path(sys.argv[3]))))
''', source, reporter)
    assert result['passed'] is False
    assert result['error'] == 'diagnostic-loader-failed'
    assert 'wrong backend' not in json.dumps(result)


def test_reporter_inside_tag_checkout_is_refused(tmp_path):
    source, reporter = authored_checkout(tmp_path)
    internal = source / 'probe.py'
    internal.write_bytes(reporter.read_bytes())
    result = isolated(IMPORT + '''
m.subprocess.check_output=lambda *a,**kw: m.SOURCE+'\\n'
print(json.dumps(m.diagnose(Path(sys.argv[2]),Path(sys.argv[2]),Path(sys.argv[2]),reporter=Path(sys.argv[3]))))
''', source, internal)
    assert result['passed'] is False
    assert result['error'] == 'diagnostic-loader-failed'


def test_wrong_tag_commit_is_rejected_before_reporter_execution(tmp_path, monkeypatch):
    diagnostic = module()
    monkeypatch.setattr(diagnostic.subprocess, 'check_output', lambda *args, **kwargs: 'a' * 40)
    monkeypatch.setattr(diagnostic, 'load_reporter', lambda *args: pytest.fail('Unexpected reporter import'))
    result = diagnostic.diagnose(tmp_path, tmp_path, tmp_path)
    assert result['passed'] is False and result['error'] == 'tag-source-mismatch'


def test_external_report_preserves_fixed_failure_phase_without_acceptance(tmp_path):
    source, reporter = authored_checkout(tmp_path)
    reporter.write_text('''
def probe(helper, resources, observation):
    observation['phase'] = 'checkout-cleanliness'
    raise ValueError('private source path')
def failure_report(error, observation):
    return {'passed':False,'phase':observation['phase'],'reason':'source-checkout-dirty'}
''')
    result = isolated(IMPORT + '''
m.subprocess.check_output=lambda *a,**kw: m.SOURCE+'\\n'
print(json.dumps(m.diagnose(Path(sys.argv[2]),Path(sys.argv[2]),Path(sys.argv[2]),reporter=Path(sys.argv[3]))))
''', source, reporter)
    assert result['passed'] is False
    assert result['probe'] == {'passed': False, 'phase': 'checkout-cleanliness', 'reason': 'source-checkout-dirty'}
    assert 'private' not in json.dumps(result)


def metadata_repair_fixture(tmp_path):
    diagnostic = module()
    source = tmp_path / 'tag'
    source.mkdir()
    pkg = {'name': 'authored-tag', 'version': '0.23.0'}
    contents = {'package.json': json.dumps(pkg, indent=2) + '\r\n',
                'package-lock.json': json.dumps({'version': '0.23.0', 'packages': {'': pkg}}, indent=2) + '\r\n',
                'VERSION': '0.23.0\r\n',
                'release-version.json': json.dumps({'version': '0.23.0',
                    'releaseCommand': 'npm run release -- --version 0.23.0'}, indent=2) + '\r\n'}
    for name, value in contents.items():
        (source / name).write_bytes(value.replace('\r\n', '\n').replace('\n', '\r\n').encode())
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=source, text=True, stderr=subprocess.PIPE).strip()
    git('init', '-q')
    git('config', 'user.name', 'Authored CI Fixture')
    git('config', 'user.email', 'fixture@users.noreply.github.com')
    git('config', 'commit.gpgsign', 'false')
    git('config', 'core.autocrlf', 'false')
    git('add', '.')
    git('commit', '-qm', 'Authored immutable metadata')
    diagnostic.SOURCE = git('rev-parse', 'HEAD')
    expected = {name: (source / name).read_bytes() for name in diagnostic.METADATA}
    for name in diagnostic.METADATA:
        (source / name).write_bytes(b'changed by original preparation\n')
    original = {'schema': 'toolkit-unreal-tag-diagnostic-v1', 'diagnostic_only': True,
                'tag': diagnostic.TAG, 'source_commit': diagnostic.SOURCE, 'passed': False,
                'probe': {'phase': 'checkout-cleanliness', 'reason': 'source-checkout-dirty',
                          'changed_release_metadata': list(diagnostic.METADATA), 'other_changed': False}}
    report = tmp_path / 'original.json'
    report.write_text(json.dumps(original))
    return diagnostic, source, report, original, expected, git


def test_metadata_repair_restores_only_observed_files_and_real_preparer_preserves_clean_crlf(tmp_path):
    diagnostic, source, report, _, expected, git = metadata_repair_fixture(tmp_path)
    result = diagnostic.repair_metadata(source, report)
    assert result['passed'] is True and result['checkout_clean'] is True
    assert result['diagnostic_only'] is True and result['release_eligible'] is False
    assert result['native_acceptance'] == 'not-established'
    assert len(result['preparer_sha256']) == 64
    assert git('status', '--porcelain') == ''
    assert expected == {name: (source / name).read_bytes() for name in diagnostic.METADATA}


@pytest.mark.parametrize('mutation', ['other', 'passed', 'phase', 'missing-file', 'source'])
def test_metadata_repair_refuses_other_original_results_without_touching_checkout(tmp_path, mutation):
    diagnostic, source, report, original, _, _ = metadata_repair_fixture(tmp_path)
    if mutation == 'other':
        original['probe']['other_changed'] = True
    elif mutation == 'passed':
        original['passed'] = True
    elif mutation == 'phase':
        original['probe']['phase'] = 'helper-copy'
    elif mutation == 'missing-file':
        original['probe']['changed_release_metadata'].pop()
    else:
        original['source_commit'] = 'f' * 40
    report.write_text(json.dumps(original))
    before = {name: (source / name).read_bytes() for name in diagnostic.METADATA}
    result = diagnostic.repair_metadata(source, report)
    assert result['passed'] is False and result['phase'] == 'validate-original-failure'
    assert before == {name: (source / name).read_bytes() for name in diagnostic.METADATA}


@pytest.mark.parametrize('additional_change', ['untracked', 'staged'])
def test_metadata_repair_refuses_live_changes_beyond_four_unstaged_metadata_files(tmp_path, additional_change):
    diagnostic, source, report, _, _, git = metadata_repair_fixture(tmp_path)
    if additional_change == 'untracked':
        (source / 'private-path.txt').write_text('untouched')
    else:
        git('add', 'VERSION')
    before = {name: (source / name).read_bytes() for name in diagnostic.METADATA}
    result = diagnostic.repair_metadata(source, report)
    assert result['passed'] is False and result['phase'] == 'validate-current-checkout'
    assert 'private-path' not in json.dumps(result)
    assert before == {name: (source / name).read_bytes() for name in diagnostic.METADATA}


def test_actual_reporter_holder_and_original_error_survive_return_gc_and_second_load(tmp_path):
    source=tmp_path/'holder-tag';backend=source/'backend';backend.mkdir(parents=True)
    stubs={'__init__.py':'', 'nte_toolchain.py':'', 'node_tools.py':"def host_platform(): return 'win-x64'\n",
        'owned_process.py':"class OwnedProcess:\n def __init__(self,*a,**kw): raise AssertionError('No native process permitted')\n",
        'prebuilt_readers.py':"RUNTIME='10.0.14'\ndef _no_links(*a): pass\ndef _source_names(*a): pass\ndef prebuilt_reader(*a,**kw): pass\ndef reader_environment(*a,**kw): pass\n",
        'runtime_bundle.py':"class RuntimeLayout: pass\ndef relative_resource(value): return value\n"}
    for name,text in stubs.items():(backend/name).write_text(text)
    reporter=ROOT/'scripts/probe-native-unreal.py'
    result=isolated(IMPORT+'''
import gc,weakref,shutil
source=Path(sys.argv[2]);reporter=Path(sys.argv[3]);records=[]
original_load=m.load_reporter
class FakeOwner:
    ended=False
    def finish(self): self.ended=True
class BodyError(OSError): pass
def load(source,reporter):
    loaded=original_load(source,reporter)
    def layout(*args,observation):
        loaded.phase(observation,'runtime-identity');observation.at('runtime-identity','runtime-identity')
        owner=FakeOwner();error=BodyError('PRIVATE-CANARY')
        observation.owners.append(owner);observation.cleanup={'state':'unconfirmed','step':'stop'}
        observation.failed(error,'unknown')
        records.append((weakref.ref(loaded),weakref.ref(observation),weakref.ref(owner),weakref.ref(error),loaded.__name__))
        raise error
    loaded._layout=layout
    return loaded
m.load_reporter=load
m.subprocess.check_output=lambda *a,**kw:m.SOURCE+'\\n'
reports=[]
for _ in range(2):
    reports.append(m.diagnose(source,source,source,reporter=reporter))
    gc.collect()
    for module_ref,holder_ref,owner_ref,error_ref,name in records:
        assert module_ref() is not None and sys.modules[name] is module_ref()
        held=holder_ref();assert held is not None and held.owners==[owner_ref()]
        assert held.errors[0] is error_ref() and held.fixture.is_dir() and not owner_ref().ended
        del held
assert len(records)==2 and records[0][4]!=records[1][4] and records[0][0]() is not records[1][0]()
for report in reports:
    assert report['diagnostic_only'] is True and report['release_eligible'] is False
    assert report['native_acceptance']=='not-established' and report['passed'] is False
    assert set(report['probe'])=={'schema','platform','passed','error','phase','reason'}
    assert (report['probe']['phase'],report['probe']['reason'])==('runtime-identity','filesystem-error')
    assert 'PRIVATE' not in json.dumps(report)
# Only these authored fake owners are explicitly ended before cache cleanup.
for module_ref,holder_ref,owner_ref,error_ref,name in records:
    held=holder_ref();owner_ref().finish();assert owner_ref().ended
    held.owners.clear();shutil.rmtree(held.fixture)
    loaded=module_ref();loaded._RETAINED_FAILURES.clear();assert sys.modules[name] is loaded
    del sys.modules[name]
print(json.dumps({'holder_and_original_error_retained':True,'second_load_keeps_first':True,
    'tag_backend_only':True,'diagnostic_only':True,'native_processes':False}))
''',source,reporter)
    assert result==dict(holder_and_original_error_retained=True,second_load_keeps_first=True,
        tag_backend_only=True,diagnostic_only=True,native_processes=False)


def test_reporter_import_name_collision_refuses_without_overwriting_first_module(tmp_path):
    source,reporter=authored_checkout(tmp_path)
    result=isolated(IMPORT+'''
from types import SimpleNamespace
m.uuid.uuid4=lambda:SimpleNamespace(hex='a'*32)
source=Path(sys.argv[2]);reporter=Path(sys.argv[3])
first=m.load_reporter(source,reporter);name=first.__name__
try:m.load_reporter(source,reporter)
except ValueError:pass
else:raise AssertionError('Unknown first module was replaced')
assert sys.modules[name] is first
# Authored reporter has no resource owner; its fixture is at a known end.
del sys.modules[name]
print(json.dumps({'collision_refused':True,'first_module_preserved':True}))
''',source,reporter)
    assert result==dict(collision_refused=True,first_module_preserved=True)
