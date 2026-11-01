"""Setup checks metadata without initializing unrelated native readers."""
from pathlib import Path
import subprocess
import sys


def test_endfield_readiness_does_not_import_native_archive_dependencies(tmp_path):
    script = '''
import importlib.abc
import sys
from pathlib import Path
class RejectNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'backend.endfield_vfs', 'numpy', 'Crypto'}:
            raise AssertionError('Readiness loaded an archive-processing dependency')
sys.meta_path.insert(0, RejectNative())
from backend.endfield_metadata import ready
assert ready(Path(sys.argv[1])) is False
'''
    subprocess.run([sys.executable, '-c', script, str(tmp_path)], check=True,
                   cwd=Path(__file__).resolve().parents[2], timeout=15,
                   capture_output=True, text=True)
