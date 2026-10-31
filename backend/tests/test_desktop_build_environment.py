"""Prevent developer DLLs from leaking into the distributable native runtime."""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

import pytest

spec = spec_from_file_location('desktop_builder', Path(__file__).resolve().parents[2] / 'scripts/build-desktop-runtime.py')
builder = module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.mark.parametrize('platform', ['win32', 'linux', 'darwin'])
def test_native_library_search_excludes_unrelated_developer_tools(monkeypatch, platform):
    monkeypatch.setattr(builder.sys, 'platform', platform)
    monkeypatch.setenv('SystemRoot', 'C:/Windows')
    monkeypatch.setenv('PATH', 'unrelated-poppler-and-qt')
    for key in ('PYTHONPATH', 'PYTHONHOME', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH',
                'DYLD_FALLBACK_LIBRARY_PATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        monkeypatch.setenv(key, 'unrelated-native-libraries')
    env = builder.build_environment(Path('inputs.json'), Path('evidence'))
    assert 'unrelated-poppler-and-qt' not in env['PATH']
    assert 'unrelated-native-libraries' not in env.values()
    assert str(Path(builder.sys.executable).parent) in env['PATH'].split(os.pathsep)
    assert env['PROXY_RUNTIME_BUILD_INPUTS'] == 'inputs.json'
    assert env['PYTHONNOUSERSITE'] == '1'
