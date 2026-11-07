import os

import pytest

from backend.hoyo_dialogue import fingerprint


def test_text_hotfixes_invalidate_voice_unchanged_snapshots_but_logs_do_not(tmp_path):
    for game, folder, relative in [
        ('starrail', 'StarRail_Data', 'Persistent/DesignData/Windows/talk.bytes'),
        ('genshin', 'GenshinImpact_Data', 'StreamingAssets/data_versions_streaming'),
    ]:
        install = tmp_path / game
        root = install / folder
        target = root / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(b'old synthetic text manifest')
        first = fingerprint(install, game)
        target.write_bytes(b'new synthetic text manifest after a text-only patch')
        second = fingerprint(install, game)
        assert second != first
        private = root / 'Persistent/Apm/events.log'
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_text('Synthetic unrelated telemetry.')
        assert fingerprint(install, game) == second
        target.unlink()
        assert fingerprint(install, game) != second


@pytest.mark.parametrize(('game', 'folder', 'relative'), [
    ('genshin', 'GenshinImpact_Data', 'StreamingAssets/AssetBundles/data_revision'),
    ('genshin', 'YuanShen_Data', 'Persistent/data_versions_persist'),
    ('genshin', 'GenshinImpact_Data', 'Persistent/res_versions_persist'),
    ('starrail', 'StarRail_Data', 'Persistent/DesignData/Windows/M_DesignV.bytes'),
    ('starrail', 'StarRail_Data', 'StreamingAssets/Asb/Windows/M_BlockV.bytes'),
])
def test_local_hotfix_marker_replaced_at_identical_size_and_mtime(tmp_path, game, folder, relative):
    root = tmp_path / folder
    pck = root / 'StreamingAssets/AudioAssets/English/example.pck'
    pck.parent.mkdir(parents=True)
    pck.write_bytes(b'unchanged synthetic pack')
    marker = root / relative
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(b'revision-A')
    old = marker.stat()
    before = fingerprint(tmp_path, game)
    marker.write_bytes(b'revision-B')
    os.utime(marker, ns=(old.st_atime_ns, old.st_mtime_ns))
    assert marker.stat().st_size == old.st_size and marker.stat().st_mtime_ns == old.st_mtime_ns
    assert fingerprint(tmp_path, game) != before
