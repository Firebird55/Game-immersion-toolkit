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
