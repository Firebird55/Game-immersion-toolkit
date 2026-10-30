"""Setup may prepare codecs after playback services have already been created."""
import json

import pytest

from backend import local_voice, pragmata_audio, voice_assets, voice_decoder


@pytest.mark.parametrize('kind', ['zzz', 'pragmata', 'local'])
def test_running_service_observes_codec_preparation_and_removal(tmp_path, monkeypatch, kind):
    available = {'binary': None}
    monkeypatch.setattr(voice_decoder, 'vgmstream_executable', lambda: available['binary'])
    for module in (voice_assets, pragmata_audio, local_voice):
        monkeypatch.setattr(module, 'ffmpeg_executable', lambda: 'owned-encoder')
    if kind == 'zzz':
        manifest = tmp_path / 'manifest.json'
        manifest.write_text(json.dumps({'version': 1, 'entries': {'line': {}}}))
        service = voice_assets.VoiceAssetService(manifest, None, tmp_path / 'audio')
        reload = lambda: service.reload(manifest)
    else:
        (tmp_path / 'textmap.json').write_text(json.dumps({
            'install': str(tmp_path), 'fingerprint': 'fixture', 'records': [
                {'text_id': 'line', 'audio': {'media_id': 123, 'bank': 'authored'}}]}))
        service = (pragmata_audio.PragmataVoiceAssetService(tmp_path, None, tmp_path / 'audio')
                   if kind == 'pragmata' else
                   local_voice.LocalVoiceAssetService('genshin', tmp_path, None, tmp_path / 'audio'))
        reload = service.reload
    try:
        assert not service.ready
        with pytest.raises(RuntimeError, match='Prepare voice tools'):
            service.require_decoder()
        # A native executable need not have the Windows suffix, nor live in data.
        binary = tmp_path / 'immutable codecs' / 'vgmstream-cli'
        binary.parent.mkdir()
        binary.write_bytes(b'authored resolver fixture')
        available['binary'] = binary
        reload()
        assert service.ready
        assert service.require_decoder() == binary
        binary.unlink()
        reload()
        assert not service.ready
        with pytest.raises(RuntimeError, match='Prepare voice tools'):
            service.require_decoder()
    finally:
        service.close()
