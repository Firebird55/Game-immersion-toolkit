"""Prevent developer DLLs from leaking into the distributable native runtime."""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

import pytest

spec = spec_from_file_location('desktop_builder', Path(__file__).resolve().parents[2] / 'scripts/build-desktop-runtime.py')
builder = module_from_spec(spec)
spec.loader.exec_module(builder)


def test_build_identity_includes_commonjs_recipe_and_ignores_build_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    for name in ('requirements.txt', 'requirements.lock.txt', 'package.json', 'package-lock.json'):
        (tmp_path / name).write_text('{}')
    recipe = tmp_path / 'packaging/zzz-reader/transpile.cjs'
    recipe.parent.mkdir(parents=True)
    recipe.write_text('// authored fixed compiler recipe')
    ignored = tmp_path / 'packaging/obj/generated.cjs'
    ignored.parent.mkdir()
    ignored.write_text('// build output')
    before = builder.source_inputs()
    assert 'packaging/zzz-reader/transpile.cjs' in before
    assert 'packaging/obj/generated.cjs' not in before
    recipe.write_text('// changed fixed compiler recipe')
    assert builder.source_inputs() != before


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
