"""Actual isolated Source workers plus extraction/PCM; all content is authored."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from backend import accounts, media_tools
from backend.source_pcm_probe import probe

ROOT = Path(__file__).resolve().parents[2]


def test_real_portal_workers_bind_selected_vpk_pcm_and_reject_damaged_or_missing_sources(tmp_path, monkeypatch):
    def forbidden(*_args, **_options):
        pytest.fail('The authored original PCM path needs no external codec or account')
    monkeypatch.setattr(media_tools, 'ffmpeg_executable', forbidden)
    monkeypatch.setattr(accounts, 'AccountStore', forbidden)
    modules = {'game-index': 'game_index_worker', 'language': 'language_worker'}
    calls = []
    def run_worker(kind, arguments, *, expected_status=0):
        completed = subprocess.run([sys.executable, '-m', 'backend.' + modules[kind], *arguments], cwd=ROOT,
            env={**os.environ, 'PATH': '', 'LOCALAPPDATA': str(tmp_path / 'private-settings'),
                'PROXY_TRANSCRIPT_PROJECT_ROOT': str(ROOT)}, capture_output=True, timeout=90)
        assert completed.returncode == expected_status, f'{kind} unexpected exit {completed.returncode}'
        calls.append(kind)
        return completed
    layout = SimpleNamespace(work_root=tmp_path / 'private-work')
    result = probe(layout, run_worker)
    assert calls == ['game-index', 'language', 'language', 'language']
    assert result['game_index_worker'] == result['language_worker'] == 'passed'
    assert result['reader_extraction'] == 'in-process-existing-adapter-passed'
    assert result['cases'][0]['wav_sha256'] != result['cases'][1]['wav_sha256']
    assert result['missing_selected_voice_pack'] == 'unavailable-no-fallback'
    assert result['changed_binding'] == result['vpk_crc_mismatch'] == 'rejected'
    assert result['truncated_pcm'] == 'rejected-previous-output-preserved'
    assert result['authored_installations'] == 'unchanged' and result['external_codec_used'] is False
    assert result['voiced_mobile_export'] == result['installed_game_probe'] == 'not-run'
    assert result['native_windows_11_acceptance'] == 'unavailable' and result['r19_complete'] is False
