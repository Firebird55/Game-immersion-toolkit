"""Shared readiness follows included operations, not a global bundle switch."""
from pathlib import Path

import pytest

from backend import game_tools, media_tools, endfield_metadata, re_pak_metadata
from backend.game_paths import GAMES
from backend.preparation_errors import PreparationFailure
from backend.tests.test_runtime_composition import fixture_layout


def included_runtime(tmp_path, monkeypatch):
    layout = fixture_layout(tmp_path, monkeypatch)
    monkeypatch.setattr(media_tools, 'ffmpeg_executable', lambda: str(layout.resource_root / 'codecs/audio/ffmpeg'))
    monkeypatch.setattr(media_tools, 'vgmstream_executable', lambda *_: layout.resource_root / 'codecs/audio/vgmstream-cli')
    monkeypatch.setattr(endfield_metadata, 'ready', lambda *_: True)
    monkeypatch.setattr(re_pak_metadata, 'ready', lambda *_: True)
    def no_download(*_a, **_k):
        pytest.fail('A bundled runtime attempted executable acquisition')
    monkeypatch.setattr(game_tools, 'install_archive', no_download)
    monkeypatch.setattr(game_tools, 'download', no_download)
    return layout


@pytest.mark.parametrize('game', sorted(set(GAMES) - {'zzz', 'nte', 'wuwa', 'cyberpunk'}))
def test_common_packaged_audio_and_owned_readers_do_not_need_developer_tools(tmp_path, monkeypatch, game):
    layout = included_runtime(tmp_path, monkeypatch)
    prepared = []
    from backend import endfield_assets
    monkeypatch.setattr(endfield_assets, 'ensure_extractor', lambda path: prepared.append(path))
    monkeypatch.setattr(re_pak_metadata, 'prepare', lambda path: prepared.append(path))
    assert game_tools.missing_tools(layout.application_root, game) == []
    progress = []
    game_tools.prepare_tools(layout.application_root, game, progress.append)
    assert prepared == ([layout.data_root / game / 'tools'] if game in {'endfield', 'pragmata'} else [])
    assert not layout.application_root.exists()


@pytest.mark.parametrize('game', ['nte', 'wuwa'])
def test_valid_unreal_chain_uses_same_ready_flow_and_never_source_sdk(tmp_path, monkeypatch, game):
    from backend import nte_assets, nte_toolchain
    layout = included_runtime(tmp_path, monkeypatch)
    resolved = []
    monkeypatch.setattr(nte_toolchain, 'resolve', lambda: resolved.append(True))
    monkeypatch.setattr(nte_assets, 'dotnet_sdk', lambda: pytest.fail('No source SDK discovery'))
    assert game_tools.missing_tools(layout.application_root, game) == []
    game_tools.prepare_tools(layout.application_root, game)
    assert len(resolved) == 2


def test_verified_cyberpunk_runtime_uses_same_packaged_preparation(tmp_path, monkeypatch):
    from backend import cyberpunk_toolchain
    layout = included_runtime(tmp_path, monkeypatch)
    checked = []
    monkeypatch.setattr(cyberpunk_toolchain, 'resolve', lambda: checked.append(True))
    assert game_tools.missing_tools(layout.application_root, 'cyberpunk') == []
    game_tools.prepare_tools(layout.application_root, 'cyberpunk')
    assert checked == [True, True]


def test_missing_reader_does_not_disable_other_games_or_start_executable_downloads(tmp_path, monkeypatch):
    from backend import prebuilt_node_reader, nte_toolchain, cyberpunk_toolchain
    layout = included_runtime(tmp_path, monkeypatch)
    def absent():
        raise PreparationFailure('bundle_toolchain_unavailable', 'Missing reader resources')
    monkeypatch.setattr(nte_toolchain, 'resolve', absent)
    monkeypatch.setattr(cyberpunk_toolchain, 'resolve', absent)
    monkeypatch.setattr(prebuilt_node_reader, 'require_zzz_reader', absent)
    for game in ('nte', 'zzz', 'wuwa', 'cyberpunk'):
        missing = game_tools.missing_tools(layout.application_root, game)
        assert len(missing) == 1
        with pytest.raises(PreparationFailure) as caught:
            game_tools.prepare_tools(layout.application_root, game)
        assert missing[0] in str(caught.value)
        assert 'SDK' not in str(caught.value) and 'source runtime' not in str(caught.value)
    assert game_tools.missing_tools(layout.application_root, 'genshin') == []
    game_tools.prepare_tools(layout.application_root, 'genshin')


def test_private_format_metadata_is_separate_from_missing_native_runtime(tmp_path, monkeypatch):
    layout = included_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(re_pak_metadata, 'ready', lambda *_: False)
    assert game_tools.missing_tools(layout.application_root, 'pragmata') == ['Archive format metadata']
    prepared = []
    monkeypatch.setattr(re_pak_metadata, 'prepare', prepared.append)
    game_tools.prepare_tools(layout.application_root, 'pragmata')
    assert prepared == [layout.data_root / 'pragmata/tools']
    monkeypatch.setattr(media_tools, 'vgmstream_executable', lambda *_: None)
    with pytest.raises(PreparationFailure, match='Voice decoder'):
        game_tools.prepare_tools(layout.application_root, 'pragmata')
    assert len(prepared) == 1


@pytest.mark.parametrize('operation', ['wuwa-prepare', 'wuwa-run', 'cyberpunk-prepare', 'cyberpunk-run'])
def test_unbundled_external_extractors_refuse_before_any_acquisition_or_run(tmp_path, monkeypatch, operation):
    from backend import bundle_tools, cyberpunk_assets, cyberpunk_toolchain, wuthering_assets
    layout = included_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(bundle_tools, 'discover_layout', lambda: layout)
    monkeypatch.setattr(cyberpunk_toolchain, 'discover_layout', lambda: layout)
    def forbidden(*_a, **_k):
        pytest.fail('Unbundled extractor attempted download, process launch or private metadata lookup')
    monkeypatch.setattr(wuthering_assets, '_download', forbidden)
    monkeypatch.setattr(wuthering_assets, '_archive_metadata', forbidden)
    monkeypatch.setattr(cyberpunk_toolchain.urllib.request, 'urlopen', forbidden)
    monkeypatch.setattr(cyberpunk_toolchain, 'OwnedProcess', forbidden)
    calls = {'wuwa-prepare': lambda: wuthering_assets.ensure_extractor(tmp_path / 'tools', None),
        'wuwa-run': lambda: wuthering_assets.run_extractor(tmp_path / 'game', tmp_path / 'tool', None, 'text'),
        'cyberpunk-prepare': lambda: cyberpunk_assets.ensure_wolvenkit(tmp_path / 'tools'),
        'cyberpunk-run': lambda: cyberpunk_assets.run_wolvenkit(tmp_path / 'tool', 'help')}
    with pytest.raises(PreparationFailure) as caught:
        calls[operation]()
    assert caught.value.code == 'bundle_toolchain_unavailable'
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('operation', ['index_install', 'index_language'])
def test_wuthering_index_uses_common_decoder_resolution(tmp_path, monkeypatch, operation):
    from backend import wuthering_assets
    selected = tmp_path / 'toolkit/data/wuwa'
    decoder = tmp_path / 'immutable-audio/vgmstream-cli'
    requests = []
    monkeypatch.setattr(media_tools, 'vgmstream_executable', lambda root: requests.append(root) or decoder)
    monkeypatch.setattr(wuthering_assets, 'fingerprint', lambda *_: 'synthetic')
    class StopAfterResolution(Exception):
        pass
    def ensure(directory, actual_decoder):
        assert directory == selected / 'tools' and actual_decoder == decoder
        raise StopAfterResolution
    monkeypatch.setattr(wuthering_assets, 'ensure_extractor', ensure)
    with pytest.raises(StopAfterResolution):
        if operation == 'index_install':
            wuthering_assets.index_install(tmp_path / 'game', selected)
        else:
            wuthering_assets.index_language(tmp_path / 'game', selected, 'en', ['en'])
    assert requests == [tmp_path / 'toolkit']
