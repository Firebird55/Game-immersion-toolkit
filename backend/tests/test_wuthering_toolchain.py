"""Wuwa uses the shared app-local reader with bounded private requests."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import nte_assets, nte_toolchain, runtime_bundle, wuthering_assets as assets
from backend.tests.test_nte_toolchain import fixture


def bundled(tmp_path, monkeypatch):
    layout, tools = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
    monkeypatch.setattr(nte_toolchain, 'discover_layout', lambda: layout)
    monkeypatch.setattr(nte_assets, 'dotnet_sdk', lambda: pytest.fail('Packaged helpers do not discover an SDK'))
    monkeypatch.setattr(assets, '_download', lambda *_: pytest.fail('No runtime tool acquisition'))
    monkeypatch.setattr(assets, 'fingerprint', lambda *_: 'authored-installed-version')
    monkeypatch.setattr(assets, '_archive_metadata', lambda *_: tuple('0x' + f'{n:064x}' for n in range(245)))
    install = tmp_path / 'game'; install.mkdir()
    executable = assets.ensure_extractor(layout.data_root / 'wuwa/tools', None)
    return layout, tools, install, executable


@pytest.mark.parametrize('voice', ['en', 'zh', 'ja', 'ko'])
def test_every_official_voice_uses_shared_apphost_and_stdin(tmp_path, monkeypatch, voice):
    layout, tools, install, executable = bundled(tmp_path, monkeypatch)
    depot = assets.EXTERNAL_ROOT + voice + '_authored_dialogue.wem'
    destination = layout.work_root / 'voice-task'
    requests = []
    def run(args, **kwargs):
        assert args == [str(executable), 'wuwa-extract', str(install), str(tools), str(destination)]
        request = json.loads(kwargs['input']); requests.append(request)
        assert request['filter'] == depot and len(request['archive_metadata']) == 245
        assert not any(value in str(args) for value in request['archive_metadata'])
        assert kwargs['env']['DOTNET_MULTILEVEL_LOOKUP'] == '0' and kwargs['cwd'] == tools
        target = destination / depot; target.parent.mkdir(parents=True); target.write_bytes(b'RIFFauthored voice')
        (destination / 'files.json').write_text(json.dumps([depot]))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(assets.subprocess, 'run', run)
    locale = {'zh': 'zh-Hans'}.get(voice, voice)
    assert assets.extract_voice(install, {'depot': depot, 'locale': locale}, executable, destination) == b'RIFFauthored voice'
    assert len(requests) == 1


def test_inventory_uses_private_temporary_output_and_preserves_missing_packs(tmp_path, monkeypatch):
    layout, _, install, executable = bundled(tmp_path, monkeypatch)
    destinations = []
    def run(args, **_kwargs):
        destination = Path(args[-1]); destinations.append(destination)
        assert args[1] == 'wuwa-list' and destination.is_relative_to(layout.work_root)
        (destination / 'files.json').write_text(json.dumps([assets.EXTERNAL_ROOT + 'en_present.wem']))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(assets.subprocess, 'run', run)
    assert assets.run_extractor(install, executable, None, 'WwiseExternalSource/') == [assets.EXTERNAL_ROOT + 'en_present.wem']
    assert not destinations[0].exists()


@pytest.mark.parametrize('selection', ['ConfigDB', '../../secret', 'ConfigDB/en/accounts',
    assets.EXTERNAL_ROOT + 'en_', assets.EXTERNAL_ROOT + 'ru_clip.wem', assets.EXTERNAL_ROOT + 'en_a/clip.wem'])
def test_unbounded_selections_never_launch_or_lookup_metadata(tmp_path, monkeypatch, selection):
    layout, _, install, executable = bundled(tmp_path, monkeypatch)
    monkeypatch.setattr(assets, '_archive_metadata', lambda *_: pytest.fail('Invalid selection reached metadata lookup'))
    monkeypatch.setattr(assets.subprocess, 'run', lambda *_a, **_k: pytest.fail('Invalid selection launched reader'))
    with pytest.raises(ValueError, match='selection'):
        assets.run_extractor(install, executable, layout.work_root / 'task', selection)


@pytest.mark.parametrize('files', [['../escaped.wem'], [assets.EXTERNAL_ROOT + 'en_../escaped.wem'],
    [assets.EXTERNAL_ROOT + 'en_clip.uasset'], ['Client/Content/unrelated.wem'], {'not': 'an inventory'}])
def test_reader_output_stays_within_requested_surface(tmp_path, monkeypatch, files):
    layout, _, install, executable = bundled(tmp_path, monkeypatch)
    def run(args, **_kwargs):
        target = Path(args[-1]); target.mkdir(parents=True, exist_ok=True)
        (target / 'files.json').write_text(json.dumps(files))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(assets.subprocess, 'run', run)
    with pytest.raises(ValueError, match='unexpected selection'):
        assets.run_extractor(install, executable, None, 'WwiseExternalSource/')


@pytest.mark.parametrize('locale', list(assets.TEXT_LOCALES.values()))
def test_text_filter_supports_all_existing_text_locales(locale):
    value = f'ConfigDB/{locale}/lang_multi_text'
    assert assets._validate_filter(value, False) == 'Client/Content/Aki/' + value


def test_localization_prefix_preserves_authored_patch_shards(tmp_path, monkeypatch):
    layout, _, install, executable = bundled(tmp_path, monkeypatch)
    names = ['Client/Content/Aki/ConfigDB/en/lang_multi_text' + suffix + '.db' for suffix in ('', '_1sthalf')]
    def run(args, **kwargs):
        assert json.loads(kwargs['input'])['filter'] == 'ConfigDB/en/lang_multi_text'
        target = Path(args[-1]); target.mkdir(parents=True, exist_ok=True)
        (target / 'files.json').write_text(json.dumps(names))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(assets.subprocess, 'run', run)
    assert assets.run_extractor(install, executable, layout.work_root / 'tables',
                                'ConfigDB/en/lang_multi_text') == names


def test_bundled_batch_uses_private_inventory_not_immutable_helper_directory(tmp_path, monkeypatch):
    layout, _, install, executable = bundled(tmp_path, monkeypatch)
    names = [assets.EXTERNAL_ROOT + 'en_authored_' + suffix + '.wem' for suffix in ('a', 'b')]
    inventory = layout.data_root / 'wuwa/index-cache/authored-install/complete.json'
    inventory.parent.mkdir(parents=True); inventory.write_text(json.dumps(names))
    filters = []
    def run(args, **kwargs):
        filters.append(json.loads(kwargs['input'])['filter'])
        target = Path(args[-1])
        for name in names:
            path = target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(name.encode())
        (target / 'files.json').write_text(json.dumps(names))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(assets.subprocess, 'run', run)
    actual = assets.extract_voices(install, [{'depot': name, 'locale': 'en'} for name in names],
                                   executable, layout.work_root / 'batch')
    assert actual == [name.encode() for name in names]
    assert filters == [assets.EXTERNAL_ROOT + 'en_authored_']


@pytest.mark.parametrize('game', ['nte', 'wuwa'])
def test_production_voice_service_resolves_cache_placeholder_to_shared_apphost(tmp_path, monkeypatch, game):
    import wave
    from backend import local_voice
    layout, tools, install, executable = bundled(tmp_path, monkeypatch)
    adapter = nte_assets if game == 'nte' else assets
    monkeypatch.setattr(adapter, 'fingerprint', lambda *_: 'authored-installed-version')
    monkeypatch.setattr(nte_assets, '_archive_metadata', lambda *_: '0x' + 'a' * 64)
    metadata = tmp_path / 'cached-metadata'; metadata.touch()
    monkeypatch.setattr(nte_assets, '_metadata_path', lambda *_: metadata)
    depot = 'HT/Content/WwiseAudio/Media/English/123.wem' if game == 'nte' else assets.EXTERNAL_ROOT + 'en_authored.wem'
    data = layout.data_root / game; data.mkdir(parents=True)
    (data / 'textmap.json').write_text(json.dumps({'install': str(install), 'fingerprint': 'authored-installed-version',
        'source_locale': 'en', 'records': [{'text_id': 'authored', 'audio': {'depot': depot, 'locale': 'en'}}]}))
    decoder = tmp_path / 'decoder'; decoder.touch()
    monkeypatch.setattr(local_voice, 'ffmpeg_executable', lambda: 'encoder')
    launched = []
    def run(args, **kwargs):
        if args[0] == str(executable):
            launched.append(args[1]); target = Path(args[-1]); target.mkdir(parents=True, exist_ok=True)
            assert args[3] == str(tools)
            if game == 'nte':
                (target / ('voice.wem' if args[1] == 'voice' else '0.wem')).write_bytes(b'RIFF' + bytes(100))
            else:
                clip = target / depot; clip.parent.mkdir(parents=True); clip.write_bytes(b'RIFF' + bytes(100))
                (target / 'files.json').write_text(json.dumps([depot]))
            return SimpleNamespace(returncode=0)
        if args[0] == str(decoder):
            output = args[args.index('-o') + 1] if '-o' in args else str(args[-1]) + '.wav'
            with wave.open(output, 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000); stream.writeframes(bytes(16000))
        else:
            Path(args[-1]).write_bytes(bytes(200))
    monkeypatch.setattr(local_voice.subprocess, 'run', run)
    service = local_voice.LocalVoiceAssetService(game, data, decoder, layout.data_root / 'audio')
    try:
        assert service.ready
        assert (service.output_dir / service.extract('authored', 1)).is_file()
        assert len(service.extract_batch([('authored', 2, '')])) == 1
        assert launched == (['voice', 'voices'] if game == 'nte' else ['wuwa-extract', 'wuwa-extract'])
    finally:
        service.close()
