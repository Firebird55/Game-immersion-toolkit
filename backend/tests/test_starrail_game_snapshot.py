"""Complete source ownership, explicit gaps and offline original restoration."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import starrail_game_audio as audio, starrail_game_snapshot as snapshot
from backend.game_data_protocol import GameDataError
from backend.tests.test_starrail_game_audio import fixture, acquire_headers, lookup_bytes


def payload():
    return {'format': 2, 'game': 'starrail', 'fingerprint': 'owned-generation', 'source_locale': 'en',
        'content_mode': 'text', 'metadata_revision': 'fixture', 'records': [{
        'text_id': 'starrail:new', 'english': 'Owned fixture.', 'chinese': '原始文本。',
        'source_text': 'Owned fixture.', 'source_locale': 'en', 'audio_locale': 'en',
        'texts': {'en': 'Owned fixture.', 'zh-Hans': '原始文本。'}, 'player_voice': None,
        'audio': None, 'voice_status': 'unavailable', 'audio_omitted_by_request': True,
        'text_capture_verified': True, 'channels': ['dialogue'],
        'source_voice_binding': {'publisher': 'owned-generation', 'locale': 'en', 'source': 'English/voice/Owned.wem'}}]}


def test_render_refuses_missing_members_owned_movies_and_conflicting_source_refs(fixture):
    owner = fixture[2]; span = audio.Span(owner, 80, 20); original = payload()
    with pytest.raises(GameDataError, match='authored recordings'):
        snapshot.render(original, {}, {})
    mixed = copy.deepcopy(original)
    mixed['records'][0]['source_voice_binding']['audio_event'] = 'Ev_conflict'
    with pytest.raises(GameDataError):
        snapshot.render(mixed, {'English/voice/Owned.wem': span}, {})
    movie = copy.deepcopy(original)
    movie['records'][0]['source_voice_binding'] = {'locale': 'en', 'film_caption': {'movies': [{'path': 'Actual.usm'}]}}
    with pytest.raises(GameDataError):
        snapshot.render(movie, {}, {})
    # A caption with no actual movie owner remains visible and unavailable,
    # rather than being labeled silent or blocking on a fabricated movie.
    movie['records'][0]['source_voice_binding']['film_caption']['movies'] = []
    rendered, members = snapshot.render(movie, {}, {})
    assert not members and rendered['records'][0]['voice_status'] == 'unavailable'
    assert rendered['records'][0]['audio_omitted_by_request'] is False


def test_movie_plan_requires_owned_movie_and_actual_localized_caption(monkeypatch):
    from backend import starrail_game_data as game, starrail_assets, starrail_films
    scripts = [('scene_Caption.json', {'CaptionList': [{'CaptionTextID': {'Hash': 1}}]})]
    catalog = SimpleNamespace(caption_scripts=lambda: scripts)
    movies = {'scene': [{'path': 'owned.usm'}]}; text = {'1': ''}
    monkeypatch.setattr(starrail_films, '_movie_sources', lambda *a: (movies, set()))
    monkeypatch.setattr(starrail_assets, 'selected_tables', lambda *a: {'en': text})
    assert not game.StarRailProvider._required_movie_audio(catalog, 'en')
    text['1'] = 'An authored subtitle.'
    assert game.StarRailProvider._required_movie_audio(catalog, 'en')
    movies.clear()
    assert not game.StarRailProvider._required_movie_audio(catalog, 'en')


def test_player_sequence_render_preserves_branch_playlist_text_and_restore_bounds(fixture):
    span = audio.Span(fixture[2], 80, 20); original = payload(); row = original['records'][0]
    row['texts'] = {'en': 'One: First.\nTwo: Second.', 'zh-Hans': '甲「一」\n乙「二」'}
    raw_texts = copy.deepcopy(row['texts'])
    row['texts'] = {locale: text.replace('\n', ' ') for locale, text in row['texts'].items()}
    row['english'] = row['source_text'] = row['texts']['en']
    row['source_voice_binding'] = {'publisher': 'owned-generation', 'locale': 'en', 'audio_event': 'Ev_any'}
    options = {gender+'-part-'+str(n): (120+n, span) for gender in ('male', 'female') for n in (1, 2)}
    # Display-normalized text has lost the authored line breaks. Sequence
    # segmentation must use the matching original TextMap values, not guess.
    with pytest.raises(GameDataError):
        snapshot.render(original, {}, {'Ev_any': options})
    result, members = snapshot.render(original, {}, {'Ev_any': options}, sequence_texts={'starrail:new': raw_texts})
    assert [r['text_id'] for r in result['records']] == [
        'starrail:new_m-part-1', 'starrail:new_m-part-2', 'starrail:new_f-part-1', 'starrail:new_f-part-2']
    assert [r['source_text'] for r in result['records']] == ['First.', 'Second.', 'First.', 'Second.']
    assert [r['player_voice'] for r in result['records']] == ['male', 'male', 'female', 'female']
    assert snapshot.unpack(snapshot.pack(members), result) == members
    changed = snapshot.pack(members); changed['members'][0][1] = True
    with pytest.raises(GameDataError):
        snapshot.unpack(changed, result)
    changed = snapshot.pack(members); changed['members'].pop()
    with pytest.raises(GameDataError):
        snapshot.unpack(changed, result)


def test_actual_provider_snapshot_and_restore_recheck_owned_files_without_network(fixture, monkeypatch, tmp_path):
    from backend import starrail_game_data as game, starrail_assets, starrail_hotfix, sophon_assets, starrail_events, native_codecs
    ctx = fixture[0]; owner, store, transport = acquire_headers(fixture)
    store.acquire(audio.Span(owner, 80, 20), transport)
    provider = game.create_provider(platform='windows')
    monkeypatch.setattr(provider, '_directory', lambda *a: store.directory.parent)
    monkeypatch.setattr(provider, '_audio_runtime_available', lambda: True)
    tools = tmp_path / 'inert-codec'; tools.write_bytes(b'inert closed fixture; never executed')
    monkeypatch.setattr(native_codecs, 'packaged_codec_executable', lambda tool, **k: tools)
    monkeypatch.setattr(starrail_assets, 'index_text_catalog', lambda *a: payload())
    monkeypatch.setattr(starrail_hotfix, 'index', lambda *a, **k: b'cached AudioV')
    monkeypatch.setattr(audio, 'owners', lambda *a: (owner,))
    raw = lookup_bytes()
    asset = sophon_assets.File(starrail_events.LOOKUP, len(raw), hashlib.md5(raw).hexdigest(), (), 'https://autopatchos.starrails.com/test')
    monkeypatch.setattr(sophon_assets, 'manifest', lambda *a, **k: {starrail_events.LOOKUP: asset})
    class Lookup:
        def __init__(self, *a): pass
        def read(self): return raw
    monkeypatch.setattr(audio, 'OriginalLookup', Lookup)
    ctx.directory.mkdir(parents=True, exist_ok=True)
    catalog = SimpleNamespace(build={'channel': 'starrail-global', 'manifests': {'game': []}},
        tables=SimpleNamespace(directory=tmp_path / 'sophon'))
    source = provider._snapshot_audio(ctx, {'build': catalog.build, 'helper': 'a'*64, 'files': {}, 'audio': {}},
        'owned-generation', catalog, SimpleNamespace(identity='b'*64), {}, store)
    ctx.service._validate_source(source, ctx)
    row = json.loads(source.snapshot_path.read_bytes())['records'][0]
    assert source.voice_source.has(row) and row['voice_status'] == 'voiced'
    monkeypatch.setattr(provider, '_reader', lambda *a: pytest.fail('Offline restore cannot launch metadata helper'))
    monkeypatch.setattr(provider, '_transport', lambda *a: pytest.fail('Offline restore cannot fetch publisher assets'))
    restored = provider.restore(source.restore_handle, ctx)
    assert restored.voice_source.has(row)
    store._path(audio.Span(owner, 80, 20)).write_bytes(bytes(20))
    with pytest.raises(GameDataError, match='not verified locally'):
        provider.restore(source.restore_handle, ctx)
