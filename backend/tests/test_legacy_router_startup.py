"""New launchers must retain the router belonging to an installed source slot."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('kind', ['legacy', 'gateway', 'missing'])
def test_router_uses_installed_source_slot(tmp_path, kind):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if not shell:
        pytest.skip('PowerShell is unavailable')
    source = tmp_path / 'installed'
    for directory in ['backend', 'scripts', 'data']:
        (source / directory).mkdir(parents=True)
    if kind != 'missing':
        (source / 'scripts/companion-router.mjs').touch()
    if kind == 'gateway':
        (source / 'backend/desktop_gateway.py').touch()
    python = source / 'python.exe'
    python.touch()
    (source / 'data/companion-runtime.json').write_text(json.dumps({'active': {'python': str(python)}}))
    runtime = Path(__file__).resolve().parents[2] / 'scripts/companion-runtime.ps1'
    script = tmp_path / 'probe.ps1'
    script.write_text("""param($Runtime,$Source)
$ErrorActionPreference='Stop'
. $Runtime
function Copy-CompanionAssets { return 'authored-assets' }
function Start-CompanionProcess($Executable,$Arguments,$Directory,$Log) {
    [pscustomobject]@{executable=$Executable;arguments=$Arguments;directory=$Directory} | ConvertTo-Json -Compress
}
Start-CompanionRouter $Source $Source -ApiPort 18766 -FrontendPort 13000
""")
    result = subprocess.run([shell, '-NoProfile', '-File', str(script), str(runtime), str(source)],
                            capture_output=True, text=True, timeout=30)
    if kind == 'missing':
        assert result.returncode != 0
        assert 'no compatible transcript router' in result.stderr
        return
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed['directory'] == str(source)
    assert observed['arguments'][-4:] == ['--api-port', '18766', '--frontend-port', '13000']
    if kind == 'gateway':
        assert observed['executable'] == str(python)
        assert observed['arguments'][:3] == ['-u', '-m', 'backend.desktop_gateway']
    else:
        assert Path(observed['arguments'][0]) == source / 'scripts/companion-router.mjs'
        assert Path(observed['executable']).stem == 'node'
