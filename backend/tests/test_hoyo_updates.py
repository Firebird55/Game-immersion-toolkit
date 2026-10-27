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
