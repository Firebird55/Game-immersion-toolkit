"""Normal preparation must never pair publisher text with another audio release."""
from types import SimpleNamespace

import pytest

from backend import dialogue_catalog, game_assets, hoyo_dialogue, hoyo_publisher_voice as voices
from backend import publisher_regions, starrail_assets as assets, starrail_publisher as publisher
from backend import starrail_original_provider as original, starrail_movie_metadata as formats


@pytest.mark.parametrize('region', ['global', 'cn'])
def test_normal_publisher_uses_original_text_and_identical_fingerprint_route(tmp_path, monkeypatch, region):
    from backend.tests.test_starrail_original_provider import fixture
    fixture(monkeypatch, region=region)
    monkeypatch.setattr(formats, 'check_latest', lambda directory: ('a' * 40, False))
    monkeypatch.setattr(publisher, '_text_commit', lambda *_: pytest.fail('Community text lookup'))
    monkeypatch.setattr(publisher, 'ReleasedCatalog', lambda *_args, **_kwargs: pytest.fail('Community text catalog'))
    stamp, catalog = publisher.prepare(tmp_path, region)
    assert catalog.revision.startswith('original-')
    assert publisher.current(stamp, region, tmp_path / 'tools')
    publisher._poll.cache_clear()
    assert publisher.fingerprint(region, tmp_path / 'tools') == stamp


@pytest.mark.parametrize('locale', ['en', 'ja', 'ko', 'zh-Hans'])
def test_saved_older_install_and_absent_dub_use_one_publisher_generation(tmp_path, monkeypatch, locale):
    from backend import starrail_events, starrail_films, voice_pack_probe
    install = tmp_path / 'saved-older-install'
    install.mkdir()
    saved = install / 'old-package.pck'
    saved.write_bytes(b'older package must remain untouched')
    assert voice_pack_probe.probe('starrail', install, locale) == 'publisher'
    catalog = SimpleNamespace(revision='original-generation-two', revision_title='official two')
    monkeypatch.setattr(publisher_regions, 'selected_region', lambda *_: 'cn')
    def prepare(data, region):
        assert data == tmp_path and region == 'cn'
        return 'publisher-two', catalog
    monkeypatch.setattr(publisher, 'prepare', prepare)
    monkeypatch.setattr(publisher, 'current', lambda stamp, region, tools: stamp == 'publisher-two' and region == 'cn')
    monkeypatch.setattr(dialogue_catalog.DialogueCatalog, '_bytes', lambda *_: pytest.fail('Community text catalog'))
    monkeypatch.setattr(hoyo_dialogue, 'inventory', lambda *_: pytest.fail('Old installed PCK inventory'))
    monkeypatch.setattr(hoyo_dialogue, 'fingerprint', lambda *_: pytest.fail('Old installed fingerprint'))
    tables = {locale: {'1': 'Current official words'}}
    monkeypatch.setattr(assets, 'selected_tables', lambda *_: tables)
    source = 'Owned-current-voice'
    links = [{'id': '1', 'hash': 1, 'source': source, 'player_voice': None}]
    monkeypatch.setattr(assets, 'authored_links', lambda *_: links)
    monkeypatch.setattr(assets, '_readable_records', lambda *_: [])
    def inventory(data, stamp, selected, game):
        assert (stamp, selected, game) == ('publisher-two', locale, 'starrail')
        return {hoyo_dialogue.voice_hash(source): {'publisher': stamp, 'package': 'current-original.pck'}}
    monkeypatch.setattr(voices, 'inventory', inventory)
    monkeypatch.setattr(starrail_events, 'bindings', lambda *_: {})
    monkeypatch.setattr(starrail_films, 'caption_rows', lambda *_: [])
    snapshot = assets.index_language(install, tmp_path, locale, [])
    assert snapshot['install'] is None and snapshot['source_mode'] == 'publisher'
    assert snapshot['records'][0]['source_text'] == 'Current official words'
    assert snapshot['records'][0]['audio']['publisher'] == snapshot['fingerprint'] == 'publisher-two'
    assert saved.read_bytes() == b'older package must remain untouched'
    monkeypatch.setattr(assets, 'publisher_fingerprint', lambda _: 'publisher-two')
    # The watcher's comparison agrees with the newly saved snapshot even when
    # the user still has a saved installation preference.
    assert game_assets.preparation_fingerprint(assets, install, tmp_path / 'tools') == snapshot['fingerprint']
    local = SimpleNamespace(fingerprint=lambda value: 'local-old', publisher_fingerprint=lambda _: 'publisher-other')
    assert game_assets.preparation_fingerprint(local, install, tmp_path / 'tools') == 'local-old'


def test_playback_obeys_each_record_source_and_preserves_historical_local_playback(tmp_path, monkeypatch):
    install = tmp_path / 'historical-install'
    monkeypatch.setattr(voices, 'extract', lambda audio, executable, game: b'publisher-' + audio['publisher'].encode())
    monkeypatch.setattr(hoyo_dialogue, 'extract_voice', lambda path, game, audio: b'historical-local' if path == install else None)
    assert assets.extract_voice(install, {'publisher': 'old-exact-release'}, '', '') == b'publisher-old-exact-release'
    assert assets.extract_voice(install, {'package': 'old.pck'}, '', '') == b'historical-local'


def test_cached_publisher_snapshot_availability_does_not_poll_the_network(tmp_path, monkeypatch):
    build = {'channel': 'starrail-global', 'version': '1.2.3'}
    stamp, raw = voices.descriptor(build)
    path = tmp_path / 'sophon/releases' / stamp
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    monkeypatch.setattr(publisher, 'fingerprint', lambda *_: pytest.fail('Offline snapshot polled current release'))
    assert assets.publisher_snapshot_available(tmp_path, stamp)


def test_failed_normal_original_update_preserves_the_previously_published_language(tmp_path, monkeypatch):
    from backend import language_worker
    from backend.tests.test_starrail_original_provider import fixture
    fixture(monkeypatch, failed='table')
    monkeypatch.setattr(formats, 'check_latest', lambda _: ('a' * 40, False))
    output = tmp_path / 'complete-language.json'
    previous = b'previous complete language and exact historical audio bindings'
    output.write_bytes(previous)
    with pytest.raises(ValueError, match='Malformed original table'):
        language_worker.build('starrail', tmp_path / 'saved-install', tmp_path, 'en', [], output)
    assert output.read_bytes() == previous
    assert not (tmp_path / 'tools/sophon/releases').exists()
