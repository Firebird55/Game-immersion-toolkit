"""Consumer regressions absent from the resolver-only/source process tests.

These use synthetic roots and subprocess tripwires, never installed games or
accounts. They prove integration/refusal, not native frozen tool execution.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend import runtime_bundle, runtime_paths
from backend.preparation_errors import PreparationFailure


def fixture_layout(tmp_path, monkeypatch):
    source = runtime_bundle.discover_layout()
    layout = replace(source, mode='bundle', application_root=tmp_path / 'app',
        resource_root=tmp_path / 'app/_internal', data_root=tmp_path / 'state/data-v1',
        settings_root=tmp_path / 'state', cache_root=tmp_path / 'state/cache-v1',
        work_root=tmp_path / 'state/cache-v1/work', tool_root=tmp_path / 'state/tools-v1',
        state_root=tmp_path / 'state/host-v1', default_export_root=tmp_path / 'state/exports',
        legacy_root=None, resources={}, children=(), profile='diagnostic')
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
    monkeypatch.setattr(runtime_paths, 'discover_layout', lambda: layout)
    return layout


def test_export_and_selected_snapshot_share_explicit_data_without_app_writes(tmp_path, monkeypatch):
    from backend.language_preparation import selected_snapshot
    from backend.mobile_export_controls import MobileExportManager
    layout = fixture_layout(tmp_path, monkeypatch)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'host-settings'))
    other = tmp_path / 'unrelated'; other.mkdir()
    monkeypatch.chdir(other)
    snapshot, accounts, account = selected_snapshot(layout.application_root, 'halflife')
    assert snapshot == layout.data_root / 'halflife/textmap.json'
    assert accounts is None and account == 'legacy'
    manager = MobileExportManager(layout.application_root)
    assert manager.destination() == layout.default_export_root
    external = tmp_path / 'selected-volume/exports'
    manager._save_destination(external)
    assert manager.destination() == external
    assert not layout.application_root.exists()
    assert not layout.data_root.exists()


def test_source_consumer_roots_preserve_caller_installation(tmp_path):
    from backend.language_preparation import selected_snapshot
    from backend.mobile_export_controls import MobileExportManager
    root = tmp_path / 'old-install'
    assert runtime_paths.data_root(root) == root / 'data'
    assert runtime_paths.voice_work_root(root) == root / 'work/voice-assets'
    assert selected_snapshot(root, 'halflife')[0] == root / 'data/halflife/textmap.json'
    # Explicit existing destination preferences continue to win; defaults retain
    # the source layout. No file movement is part of root resolution.
    assert runtime_paths.default_export_root(root) == root / 'output/mobile-libraries'


def test_source_rejects_new_root_overrides_before_splitting_export_state(tmp_path, monkeypatch):
    root = tmp_path / 'old-install'
    for suffix, folder in [('DATA_ROOT', 'data-v1'), ('WORK_ROOT', 'voice-work'), ('DEFAULT_EXPORT_ROOT', 'exports')]:
        monkeypatch.setenv('PROXY_TRANSCRIPT_' + suffix, str(tmp_path / folder))
    with pytest.raises(runtime_bundle.RuntimeBundleError):
        runtime_paths.data_root(root)
    assert not root.exists() and not (tmp_path / 'data-v1').exists()


@pytest.mark.parametrize('component', ['nte-prepare', 'nte-run', 'ree'])
def test_frozen_reader_refuses_before_download_sdk_or_compiler(tmp_path, monkeypatch, component):
    from backend import bundle_tools, prebuilt_readers, nte_assets, ree_extractor, game_tools
    monkeypatch.setattr(bundle_tools, 'discover_layout', lambda: SimpleNamespace(mode='bundle'))
    monkeypatch.setattr(prebuilt_readers, 'discover_layout', lambda: SimpleNamespace(mode='bundle'))
    def forbidden(*_args, **_kwargs):
        pytest.fail('A diagnostic bundle attempted a developer tool or download')
    monkeypatch.setattr(nte_assets, 'dotnet_sdk', forbidden)
    monkeypatch.setattr(game_tools, 'install_archive', forbidden)
    monkeypatch.setattr(game_tools, 'download', forbidden)
    monkeypatch.setattr(nte_assets.subprocess, 'run', forbidden)
    functions = {
        'nte-prepare': lambda: nte_assets.ensure_extractor(tmp_path / 'tools'),
        'nte-run': lambda: nte_assets.run_reader(tmp_path / 'game', tmp_path / 'reader', tmp_path / 'out', 'inventory'),
        'ree': lambda: ree_extractor.ensure_extractor(tmp_path / 'tools'),
    }
    with pytest.raises(PreparationFailure) as error:
        functions[component]()
    assert error.value.code == 'bundle_toolchain_unavailable'
    assert not list(tmp_path.iterdir())


def test_diagnostic_readiness_keeps_text_only_game_distinct_from_global_audio(tmp_path, monkeypatch):
    from backend import game_tools, media_tools
    from backend.game_paths import GAMES
    fixture_layout(tmp_path, monkeypatch)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda *_: pytest.fail('Frozen FFmpeg fell back to PATH'))
    media_tools.ffmpeg_executable.cache_clear()
    try:
        assert media_tools.ffmpeg_executable() is None
        assert game_tools.missing_tools(tmp_path, 'halflife') == []
        assert len(GAMES) == 25
        for game in GAMES:
            if game not in {'halflife', 'beyond', 'heavyrain'}:
                assert game_tools.missing_tools(tmp_path, game) == ['R19 decoder/helper closure unavailable']
    finally:
        media_tools.ffmpeg_executable.cache_clear()


def test_frozen_setup_reports_pending_runtime_gate_without_recommending_developer_tools(tmp_path, monkeypatch):
    # Resolver/refusal tests do not exercise the actual setup requirements. A
    # frozen executable must not send users back to source npm/SDK repair steps.
    import json
    from pathlib import Path
    from backend import installation
    layout = fixture_layout(tmp_path, monkeypatch)
    package = tmp_path / 'package.json'; package.write_text(json.dumps({'version': '0.22.0'}))
    monkeypatch.setattr(installation, 'discover_layout', lambda: layout)
    monkeypatch.setattr(installation, 'resource_path', lambda _: package)
    monkeypatch.setattr(installation, 'load_paths', lambda: {})
    monkeypatch.setattr(installation, 'configured_install', lambda _: None)
    monkeypatch.setattr(installation, 'missing_tools', lambda *_: ['R19 decoder/helper closure unavailable'])
    monkeypatch.setattr(installation, 'ffmpeg_executable', lambda: None)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'empty-host')
    monkeypatch.setattr(installation.shutil, 'which', lambda *_: pytest.fail('Frozen setup probed a developer PATH tool'))
    service = installation.InstallationService(layout.application_root, settings=SimpleNamespace(),
        game_state=lambda _: {}, refresh=lambda _: None, account_configured=lambda: False,
        install_lookup=lambda _: None)
    result = service.status()
    assert 'node' not in {item['id'] for item in result['requirements']}
    gate = next(item for item in result['requirements'] if item['id'] == 'runtime-acceptance')
    assert gate['ready'] is False
    assert all('Install.cmd' not in item['help'] for item in result['requirements'])
    assert 'SDK' not in next(item for item in result['games'] if item['id'] == 'endfield')['voice_hint']
    assert not layout.application_root.exists() and not layout.settings_root.exists()
