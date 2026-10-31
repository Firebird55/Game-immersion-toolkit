"""Execute the actual fixed publisher against owned filesystem boundaries."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PublisherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='r19-census-publisher-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base/'source'
        (self.root/'scripts').mkdir(parents=True)
        self.core = self.root/'scripts/probe-msvc-redist.py'
        shutil.copyfile(ROOT/'scripts/probe-msvc-redist.py', self.core)
        source = (ROOT/'scripts/run-msvc-redist-census.mjs').read_text(encoding='utf-8')
        self.program = source.split('const publish = String.raw`\n', 1)[1].split('\n`;', 1)[0]
        self.report = {'schema': 'owned-publisher-fixture', 'status': 'observed-not-approved'}
        raw = (json.dumps(self.report, separators=(',', ':'))+'\n').encode()
        self.binding = {'schema': 'owned-binding-fixture',
            'census': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
        self.output = self.root/'output/checks'

    def invoke(self, payload=None):
        result = subprocess.run([sys.executable, '-I', '-B', '-c', self.program, str(self.root)],
            input=payload if payload is not None else json.dumps([self.report, self.binding]).encode(),
            capture_output=True, timeout=15)
        self.assertNotIn(b'PRIVATE', result.stdout+result.stderr)
        self.assertNotIn(str(self.base).encode(), result.stdout+result.stderr)
        return result

    def refused(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')
        self.assertNotIn(b'PAIR_WRITTEN', result.stderr)

    def test_fresh_pair_is_exclusive_and_the_published_census_matches_the_bound_bytes(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.replace(b'\r\n', b'\n'), b'PAIR_WRITTEN\n')
        census = (self.output/'MSVC-REDIST-CENSUS.json').read_bytes()
        self.assertEqual(hashlib.sha256(census).hexdigest(), self.binding['census']['sha256'])
        self.assertEqual(json.loads((self.output/'MSVC-REDIST-CI-BINDING.json').read_bytes()), self.binding)

    def test_either_existing_leaf_refuses_before_creating_the_other_and_preserves_unknown_files(self):
        self.output.mkdir(parents=True)
        for existing, absent in [('MSVC-REDIST-CENSUS.json', 'MSVC-REDIST-CI-BINDING.json'),
                                 ('MSVC-REDIST-CI-BINDING.json', 'MSVC-REDIST-CENSUS.json')]:
            with self.subTest(existing=existing):
                target = self.output/existing
                target.write_bytes(b'PRIVATE previous-owner file')
                self.refused(self.invoke())
                self.assertEqual(target.read_bytes(), b'PRIVATE previous-owner file')
                self.assertFalse((self.output/absent).exists())
                target.unlink()

    def test_linked_public_parent_never_writes_outside_the_owned_source_tree(self):
        outside = self.base/'PRIVATE outside'
        outside.mkdir()
        for parent in (self.root/'output', self.output):
            with self.subTest(parent=parent.name):
                parent.parent.mkdir(parents=True, exist_ok=True)
                parent.symlink_to(outside, target_is_directory=True)
                self.refused(self.invoke())
                self.assertEqual(list(outside.iterdir()), [])
                parent.unlink()

    def test_either_linked_leaf_is_refused_and_no_partial_pair_is_written(self):
        self.output.mkdir(parents=True)
        outside = self.base/'PRIVATE outside.json'
        outside.write_bytes(b'PRIVATE unchanged target')
        for existing, absent in [('MSVC-REDIST-CENSUS.json', 'MSVC-REDIST-CI-BINDING.json'),
                                 ('MSVC-REDIST-CI-BINDING.json', 'MSVC-REDIST-CENSUS.json')]:
            with self.subTest(existing=existing):
                target = self.output/existing
                target.symlink_to(outside)
                self.refused(self.invoke())
                self.assertEqual(outside.read_bytes(), b'PRIVATE unchanged target')
                self.assertFalse((self.output/absent).exists())
                target.unlink()

    def test_same_size_binding_change_after_write_cannot_receive_a_pair_written_receipt(self):
        # Behavior double only in this owned copy: reproduce the reviewer's
        # write/read race while executing the unchanged actual CI publisher.
        with self.core.open('a', encoding='utf-8') as stream:
            stream.write('''
_original_write_report = write_report
def write_report(path, value, **kwargs):
    _original_write_report(path, value, **kwargs)
    if path.name == 'MSVC-REDIST-CI-BINDING.json':
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'owned-binding-fixture', b'owned-binding-altered'))
''')
        self.refused(self.invoke())

    def test_mapping_change_after_first_leaf_refuses_before_writing_the_second_leaf(self):
        # Inject only authored mapping responses into the owned core copy. A
        # fresh budget per leaf would forget the earlier preflight identity.
        with self.core.open('a', encoding='utf-8') as stream:
            stream.write('''
_mapping = [r'\\Device\\HarddiskVolume1']
def windows_drive_mapping(drive, budget):
    return _mapping[0]
_original_path_identity = path_identity
def path_identity(path, budget):
    checked_drive('C:', budget)
    return _original_path_identity(path, budget)
_original_write_report = write_report
def write_report(path, value, **kwargs):
    _original_write_report(path, value, **kwargs)
    if path.name == 'MSVC-REDIST-CENSUS.json':
        _mapping[0] = r'\\Device\\HarddiskVolume2'
''')
        self.refused(self.invoke())
        self.assertTrue((self.output/'MSVC-REDIST-CENSUS.json').is_file())
        self.assertFalse((self.output/'MSVC-REDIST-CI-BINDING.json').exists())

    def test_overbound_or_malformed_payload_cannot_publish_a_partial_pair(self):
        for payload in (b'x'*131073, b'{', b'[]', b'[{},null]'):
            with self.subTest(bytes=len(payload)):
                self.refused(self.invoke(payload))
                self.assertEqual(list(self.output.iterdir()), [])

    def diagnostic_helpers(self):
        source = (ROOT/'scripts/run-msvc-redist-census.mjs').read_text(encoding='utf-8')
        program = source.split('const observerDiagnostics = String.raw`\n', 1)[1].split('\n`;', 1)[0]
        observer = source.split('const program = String.raw`\n', 1)[1].split('\n`;', 1)[0]
        observer = observer.replace('${observerDiagnostics}', program)
        compile(observer, '<authored-observer-program>', 'exec')
        namespace = {}
        exec(compile(program, '<authored-observer-diagnostic>', 'exec'), namespace)
        namespace['observer_program'] = observer
        return namespace

    def test_observer_failure_diagnostic_uses_fixed_parent_labels_without_exception_or_subtest_text(self):
        helpers = self.diagnostic_helpers(); names = helpers['METHODS']['CensusTests']
        marker = 'PRIVATE synthetic exception, account parameter and source path'
        class PrivateParameter:
            def __repr__(self): raise AssertionError('Subtest values must not be formatted.')
        def inline(case): case.fail(marker)
        def subtest(case):
            with case.subTest(account=PrivateParameter()): case.fail(marker)
        def skip(case): case.skipTest(marker)
        def forbidden_id(_case): raise AssertionError('Unittest ids must not be read.')
        owned = type('CensusTests', (unittest.TestCase,), {names[12]:inline, names[4]:subtest,
            names[0]:skip, 'id':forbidden_id, '__str__':forbidden_id})
        result = helpers['SafeResult']()
        unittest.TestSuite([owned(names[12]),owned(names[4]),owned(names[0])]).run(result)
        value = helpers['safe_diagnostic']('authored-contracts','unexpected',result)
        self.assertEqual((value['contracts'],value['failures'],value['errors'],value['skipped']), (3,2,0,1))
        self.assertEqual(value['tests'], ['core-01','core-05','core-13']); self.assertFalse(result.wasSuccessful())
        self.assertEqual((result.failures,result.errors,result.skipped), ([],[],[]))
        self.assertFalse(marker in json.dumps(value), 'Fixed diagnostic included fixture text.')
        # Execute the actual handler with an absent owned root. It either
        # refuses observer identity or import before loading any census/test
        # module; this cannot recursively run this suite or query installed VS.
        refused = subprocess.run([sys.executable,'-I','-B','-c',helpers['observer_program'],
            str(self.base/'PRIVATE absent observer root'),'a'*40,'owned-diagnostic'],
            capture_output=True,timeout=15)
        self.assertEqual(refused.returncode,2); self.assertEqual(refused.stderr,b'')
        self.assertLessEqual(len(refused.stdout),4096)
        value = json.loads(refused.stdout)
        self.assertEqual((value['phase'],value['code'],value['contracts'],value['tests']),
            ('observer-identity','unexpected',None,[]))
        self.assertFalse(b'PRIVATE' in refused.stdout, 'Handled child failure included fixture arguments.')

    def test_observer_failure_diagnostic_caps_labels_counts_and_unknown_methods(self):
        helpers = self.diagnostic_helpers(); names = helpers['METHODS']['CensusTests']
        result = helpers['SafeResult']()
        for name in names:
            result.record('errors', type('CensusTests', (), {'_testMethodName':name})())
        value = helpers['safe_diagnostic']('authored-contracts','unexpected',result)
        self.assertEqual(len(value['tests']),8); self.assertEqual(value['errors'],28)
        result = helpers['SafeResult']()
        result.record('errors', type('PRIVATE unknown class', (), {'_testMethodName':'PRIVATE unknown parameter'})())
        self.assertEqual(helpers['safe_diagnostic']('authored-contracts','unexpected',result)['tests'], ['unavailable'])
        result.counts['errors'] = 1001
        value = helpers['safe_diagnostic']('authored-contracts','unexpected',result)
        self.assertEqual([value[key] for key in ('contracts','failures','errors','skipped')], [None]*4)
        self.assertEqual(value['tests'],[])
        self.assertFalse('PRIVATE' in json.dumps(value), 'Unknown method details must not be published.')


if __name__ == '__main__':
    unittest.main()
