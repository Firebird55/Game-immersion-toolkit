"""The exact isolated recovery/update copy lists must import without the repo."""
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('script,pattern', [
    ('companion-process-identity-e2e.ps1', r"foreach \(\$name in @\(([^)]*'desktop_gateway\.py'[^)]*)\)\)"),
    ('update-companion-e2e.mjs', r"for\(const name of \[([^\]]*'desktop_gateway\.py'[^\]]*)\]\)"),
], ids=['process-identity-recovery', 'prepared-update'])
def test_isolated_gateway_copy_list_contains_its_real_import_closure(tmp_path, script, pattern):
    match = re.search(pattern, (ROOT / 'scripts' / script).read_text(encoding='utf-8'))
    assert match is not None, 'The fixture gateway copy list was not found'
    files = re.findall(r"'([^']+)'", match[1])
    backend = tmp_path / 'backend'
    backend.mkdir()
    (backend / '__init__.py').touch()  # The JavaScript update fixture creates this explicitly.
    for name in files:
        assert Path(name).name == name
        shutil.copyfile(ROOT / 'backend' / name, backend / name)
    # -I excludes cwd/PYTHONPATH; only the fixture root and prepared interpreter
    # dependencies are available. --help imports the real gateway without
    # binding a port, reading game/account state, or launching any services.
    result = subprocess.run([sys.executable, '-I', '-B', '-c',
        'import runpy,sys; sys.path.insert(0,sys.argv[1]); '
        'sys.argv=["backend.desktop_gateway","--help"]; '
        'runpy.run_module("backend.desktop_gateway",run_name="__main__")', str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert '--shutdown-stdin' not in result.stdout  # Hidden lifecycle controls stay hidden.
    assert '--api-port' in result.stdout
