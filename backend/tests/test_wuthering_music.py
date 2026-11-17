"""Authored song language, shared-source ownership and top-left capture failures."""
import json
import sqlite3
import struct
import subprocess

import pytest

from backend import wuthering_assets as assets, wuthering_music as music
from backend.endfield_caption_context import EndfieldCaptionContext
from backend.languages import audio_locale
from backend.local_game import LocalDialogue
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_wuthering_bank import bank, direct, u32
from backend.tests.test_wuthering_narrative import flat_blob, flow_database
from backend.wuthering_bank import SceneSource, scene_sources, song_sources
from backend.nte_assets import wwise_hash


def fixture(root, *, original='en', group='new_song', first_id=901, event='play_new_song'):
    subtitles = {
        'en': ['Follow the river through the quiet valley.', 'Go.'],
        'zh-Hans': ['沿着河流穿过寂静的山谷。', '走吧。'],
        'zh-Hant': ['沿著河流穿過寂靜的山谷。', '走吧。'],
        'ja': ['川に沿って静かな谷を進もう。', '行こう。'],
        'ko': ['강을 따라 고요한 계곡을 지나가자.', '가자.'],
    }
    with sqlite3.connect(root / music.TABLE) as db:
        db.execute('CREATE TABLE musicsubtitle (Id INTEGER PRIMARY KEY, SubtitleGroupTag TEXT, BinData BLOB)')
        for offset in range(2):
            identity = first_id + offset
            blob = bytearray(flat_blob({0: identity, 1: group, 2: 0, 3: 0}))
            for slot, value in ((2, offset * 3.), (3, offset * 3. + 2.)):
                struct.pack_into('<f', blob, assets._field(blob, slot), value)
            db.execute('INSERT INTO musicsubtitle VALUES (?,?,?)', (identity, group, blob))
    flow_database(root, [{'Name': 'PostAkEvent', 'Params': {'EventConfig': {
        'Type': 'MusicSubtitle', 'MusicSubtitleGroupTag': group,
        'AkEvent': f'/Game/Aki/WwiseAudio/Events/{event}.{event}'}}}])
    for locale, values in subtitles.items():
        directory = root / assets.TEXT_LOCALES[locale]
        directory.mkdir()
        with sqlite3.connect(directory / 'lang_multi_text.db') as db:
            db.execute('CREATE TABLE MultiText (Id TEXT PRIMARY KEY, Content TEXT, RedirectDbIndex INTEGER)')
            for offset, text in enumerate(values):
                native = audio_locale(locale) == audio_locale(original)
                for suffix, content in (('Original', '{KeepOrigin}' if native else subtitles[original][offset]),
                                        ('Translation', text)):
                    db.execute('INSERT INTO MultiText VALUES (?,?,0)', (f'LyricsText_{first_id + offset}_{suffix}', content))
    return subtitles


def prepare(root, locale='en', **options):
    rows = music.records(root, locale, assets.SUPPORTED_LOCALES,
                         {'play_new_song': (SceneSource(101, None, 100),)},
                         options.pop('shapes', {101: (2, 480000)}))
    for row in rows:
        if row['audio']:
            row['audio']['publisher'] = 'wuwa-' + 'a' * 64
        LocalDialogue(**row)
    return rows


@pytest.mark.parametrize('original,voiced', [('en', {'en'}), ('zh-Hans', {'zh-Hans', 'zh-Hant'})])
def test_original_song_language_is_independent_of_selected_dub_and_preserves_official_translations(original, voiced, tmp_path):
    texts = fixture(tmp_path, original=original)
    for locale in assets.SUPPORTED_LOCALES:
        rows = prepare(tmp_path, locale)
        assert len(rows) == 2
        assert rows[0]['source_text'] == texts[locale][0]
        assert rows[0]['texts'] == {language: values[0] for language, values in texts.items()}
        assert rows[1]['previous_text_id'] == rows[0]['text_id']
        assert rows[0]['text_capture_verified']
        assert {row['voice_status'] for row in rows} == ({'voiced'} if locale in voiced else {'unavailable'})
        if locale in voiced:
            assert rows[0]['audio']['locale'] == audio_locale(locale)
            assert rows[0]['audio']['source_frames'] == 480000
            assert rows[0]['audio_scope'] == 'context'
            assets._validate_voice(rows[0]['audio'])
        else:
            assert all(row['audio'] is None for row in rows)


@pytest.mark.parametrize('changed', ['different-original', 'missing-original', 'inconsistent-later-row'])
def test_incomplete_or_disagreeing_original_text_never_guesses_song_language(changed, tmp_path):
    fixture(tmp_path)
    for locale in ('zh-Hans', 'zh-Hant', 'ja', 'ko'):
        with sqlite3.connect(tmp_path / locale / 'lang_multi_text.db') as db:
            if changed == 'missing-original':
                db.execute("DELETE FROM MultiText WHERE Id LIKE '%_Original'")
            else:
                db.execute('UPDATE MultiText SET Content=? WHERE Id=?',
                           ('Other authored words.', 'LyricsText_902_Original' if changed == 'inconsistent-later-row' else 'LyricsText_901_Original'))
    assert all(row['audio'] is None and row['voice_status'] == 'unavailable' for row in prepare(tmp_path))


def test_missing_audio_translations_require_explicit_opt_in_and_never_become_unvoiced(tmp_path):
    fixture(tmp_path)
    rows = prepare(tmp_path, 'ja')
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'wuwa', 'source_locale': 'ja', 'records': rows}))
    index = MultilingualTextIndex('wuwa', tmp_path)
    assert index.ready
    text = rows[0]['source_text']
    assert not index.match_lines([text])
    index.capture_unvoiced = True
    assert not index.match_unvoiced_lines([text])
    index.capture_missing_audio = True
    hits = index.match_missing_audio_lines([text])
    assert len(hits) == 1 and hits[0].voice_status == 'unavailable'
    assert not index.match_missing_audio_lines([text[:-4]])


def test_short_top_left_lyric_requires_stable_authored_predecessor_and_context_reset(tmp_path):
    fixture(tmp_path)
    rows = prepare(tmp_path)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'wuwa', 'source_locale': 'en',
        'publisher_song_cues': 2, 'records': rows}))
    index = MultilingualTextIndex('wuwa', tmp_path)
    assert index.ready
    long, short = [row['source_text'] for row in rows]
    assert index.match_full_frame_voice_lines([long])
    assert not index.match_full_frame_voice_lines([short])
    context = EndfieldCaptionContext()
    def observe(text, now, scope=1):
        return context.observe(index, [text], index.match_full_frame_voice_lines([text]), channel='cinematic',
                               kind='music_subtitle', scope=scope, now=now, stable_frames=2)
    assert observe(short, 0) is None
    assert observe(long, 1) is None
    assert observe(long, 1.1) is None
    hit = observe(short, 1.2)
    assert hit and hit.text_id == rows[1]['text_id'] and hit.audio_scope == 'context'
    assert observe(short, 1.3, scope=2) is None
    context.reset()
    assert observe(short, 2) is None


@pytest.mark.parametrize('change', [{'music_context': False}, {'source_clock': 'wall_time'},
                                  {'scene_context': False}, {'start_ms': 0}, {'source_frames': 14400001}])
def test_common_source_cannot_escape_its_whole_song_contract(change, tmp_path):
    fixture(tmp_path)
    audio = prepare(tmp_path)[0]['audio']
    audio.update(change)
    with pytest.raises(ValueError):
        assets._validate_voice(audio)


def common_bank(*, delay=100, extra_play=False):
    nodes = direct()
    kind, key, data = nodes[0]
    nodes[0] = kind, key, data[:17] + b'\x08' + data[18:]
    nodes[-1] = (3, 50, b'\x03\x04' + u32(10) + b'\0\x01\x3a' + u32(delay)
                 + b'\0\x04' + u32(wwise_hash('owned_scene')) + u32(30))
    if extra_play:
        nodes.append((3, 51, nodes[-1][2]))
    return bank(nodes, actions=(50, 51) if extra_play else (50,))


def test_source_position_clock_allows_authored_start_delay_without_weakening_scene_clock():
    data = common_bank()
    assert song_sources(data, 'owned_scene', {101}) == (SceneSource(101, None, 100),)
    assert not scene_sources(data, 'owned_scene', {101})
    assert not song_sources(bank(direct()), 'owned_scene', {101})
    assert not song_sources(common_bank(extra_play=True), 'owned_scene', {101})
    nodes = direct()
    nodes[0] = (2, 10, nodes[0][2][:17] + b'\x08' + nodes[0][2][18:])
    nodes.append((3, 51, b'\x03\x01' + u32(10) + b'\0'))
    assert not song_sources(bank(nodes, actions=(50, 51)), 'owned_scene', {101})
    assert not song_sources(common_bank(delay=300001), 'owned_scene', {101})


def test_missing_source_or_incomplete_clock_retains_text_without_a_silence_claim(tmp_path):
    fixture(tmp_path)
    for shapes in ({}, {101: (2, 48000)}, {101: (2, 14400001)}):
        rows = prepare(tmp_path, shapes=shapes)
        assert len(rows) == 2 and all(row['audio'] is None and row['voice_status'] == 'unavailable' for row in rows)


def test_normal_capture_keeps_top_left_context_and_restarts_stability_after_menu(tmp_path):
    import asyncio
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from backend.capture import _ScanOutcome
    from backend.tests.test_local_chatter import row as ocr_row
    from backend.tests.test_subtitle_capture import fixture_service
    fixture(tmp_path)
    rows = prepare(tmp_path)
    rows.append({**rows[0], 'text_id': 'wuwa:music:903', 'previous_text_id': rows[1]['text_id']})
    directory = tmp_path / 'prepared'; directory.mkdir()
    (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'wuwa', 'source_locale': 'en',
        'publisher_song_cues': 3, 'records': rows}))
    index = MultilingualTextIndex('wuwa', directory)
    service, _, scheduled, published = fixture_service(tmp_path, game='wuwa')
    service.game_indexes = {'wuwa': index}
    service.game_voice_assets = {'wuwa': service.voice_assets}
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Authored game fixture')
    response = {'lines': [ocr_row(rows[0]['source_text'], .03, .12, size=(800, 200))]}
    engine = SimpleNamespace(recognize_pil=lambda _: response)
    def scan():
        return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                      datetime.now(timezone.utc), 'wuwa')
    async def run():
        service._event_loop = asyncio.get_running_loop()
        assert not scan().emitted_lines
        response['dialogue_menu'] = True
        assert not scan().emitted_lines
        response.pop('dialogue_menu')
        assert not scan().emitted_lines
        assert [line.text_id for line in scan().emitted_lines] == [rows[0]['text_id']]
        response['lines'] = [ocr_row(rows[1]['source_text'], .03, .12, size=(800, 200))]
        assert not scan().emitted_lines
        assert [line.text_id for line in scan().emitted_lines] == [rows[1]['text_id']]
        response['lines'] = [ocr_row(rows[2]['source_text'], .03, .12, size=(800, 200))]
        assert not scan().emitted_lines
        assert [line.text_id for line in scan().emitted_lines] == [rows[2]['text_id']]
        await asyncio.sleep(.02)
        assert len(scheduled) == len(published) == 3
        assert all(line.audio_scope == 'context' and line.game == 'wuwa' for line in published)
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()


def test_shared_resource_overlay_tombstone_cannot_fall_back_to_retired_audio(tmp_path, monkeypatch):
    from backend import wuthering_release as release
    def packages(snapshot, channel, layer):
        assert channel == 'resource'
        return [layer]
    def locations(tools, packages, params, *, wanted):
        layer = packages[0]
        if layer == 'PatchFiles':
            return {'retired.wem': (('new', 1, 'new-hash'), -2147483648)}
        if layer == 'BaseFiles':
            return {name: (('old', 1, 'old-hash'), 5) for name in wanted if name in {'retired.wem', 'current.wem'}}
        return {}
    monkeypatch.setattr(release, '_packages', packages)
    monkeypatch.setattr(release, '_locations', locations)
    assert release._shared_locations(tmp_path, {}, (), {'retired.wem', 'current.wem'}) == {
        'current.wem': (('old', 1, 'old-hash'), 5)}


def test_original_source_cache_is_revision_scoped_and_survives_interrupted_new_download(tmp_path, monkeypatch):
    from backend import wuthering_release as release
    from types import SimpleNamespace
    import hashlib
    old, new = ('wuwa-' + letter * 64 for letter in ('a', 'b'))
    depot = 'Client/Content/Aki/WwiseAudio_Generated/Media/101.wem'
    original = b'RIFF' + struct.pack('<I', 8) + b'WAVEold!'
    updated = b'RIFF' + struct.pack('<I', 8) + b'WAVEnew!'
    calls = []
    def package(tools, stamp, info):
        def extract(position):
            calls.append(stamp)
            if stamp == new:
                raise OSError('Interrupted original publisher transfer')
            return original
        return SimpleNamespace(extract=extract)
    monkeypatch.setattr(release, '_voice_package', package)
    assert release._source_bytes(tmp_path, old, depot, (('old-source',), 1)) == original
    old_file = release._descriptor_path(tmp_path, old).parent / 'clips' / hashlib.sha256(depot.encode()).hexdigest()
    retained = old_file.read_bytes()
    with pytest.raises(OSError, match='Interrupted'):
        release._source_bytes(tmp_path, new, depot, (('new-source',), 1))
    assert old_file.read_bytes() == retained
    assert release._source_bytes(tmp_path, old, depot) == original
    assert release._source_bytes(tmp_path, new, depot) is None
    assert release._source_bytes(tmp_path, old, depot.replace('101', '102')) is None
    monkeypatch.setattr(release, '_voice_package', lambda *_: SimpleNamespace(extract=lambda _: updated))
    assert release._source_bytes(tmp_path, new, depot, (('new-source',), 1)) == updated
    assert release._source_bytes(tmp_path, old, depot) == original
    old_file.write_bytes(retained[:-1] + b'?')
    assert release._source_bytes(tmp_path, old, depot) is None


@pytest.mark.parametrize('failure', [OSError('Native source could not be opened'),
    subprocess.CalledProcessError(1, ['authored-probe']), subprocess.TimeoutExpired('authored-probe', 45)])
def test_native_probe_failure_cannot_silently_remove_existing_voice_contexts(failure, tmp_path, monkeypatch):
    from backend import wuthering_cinematics as films
    from backend.preparation_errors import PreparationFailure
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(films.subprocess, 'run', fail)
    with pytest.raises(PreparationFailure, match='incomplete candidate') as error:
        films.source_info(b'authored fixture', 'authored-decoder', tmp_path)
    assert error.value.code == 'audio_probe_failed'


def test_new_group_names_and_new_caption_ids_need_no_reader_update(tmp_path):
    fixture(tmp_path, group='新章节-song.2', first_id=52123)
    rows = prepare(tmp_path)
    assert {row['text_id'] for row in rows} == {'wuwa:music:52123', 'wuwa:music:52124'}
    assert all(row['voice_status'] == 'voiced' for row in rows)
    assert all(row['audio']['scene'] == '新章节-song.2' for row in rows)


def test_valid_unsupported_source_shape_stays_distinct_from_a_failed_native_probe(tmp_path, monkeypatch):
    from backend import wuthering_cinematics as films
    from types import SimpleNamespace
    metadata = {'sampleRate': 48000, 'channels': 6, 'numberOfSamples': 96000, 'playSamples': 96000,
                'mixingInfo': {'inputChannels': 6, 'outputChannels': 6}, 'streamInfo': {'total': 1, 'index': 0}}
    monkeypatch.setattr(films.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=json.dumps(metadata).encode()))
    assert films.source_info(b'authored fixture', 'authored-decoder', tmp_path) is None


def test_repeated_chorus_keeps_the_authored_current_occurrence_after_index_coalescing(tmp_path):
    fixture(tmp_path)
    with sqlite3.connect(tmp_path / music.TABLE) as db:
        blob = bytearray(flat_blob({0: 903, 1: 'new_song', 2: 0, 3: 0}))
        struct.pack_into('<f', blob, assets._field(blob, 2), 6.)
        struct.pack_into('<f', blob, assets._field(blob, 3), 8.)
        db.execute('INSERT INTO musicsubtitle VALUES (?,?,?)', (903, 'new_song', blob))
    for locale in assets.SUPPORTED_LOCALES:
        with sqlite3.connect(tmp_path / locale / 'lang_multi_text.db') as db:
            for suffix in ('Original', 'Translation'):
                text, = db.execute('SELECT Content FROM MultiText WHERE Id=?', (f'LyricsText_901_{suffix}',)).fetchone()
                db.execute('INSERT INTO MultiText VALUES (?,?,0)', (f'LyricsText_903_{suffix}', text))
    rows = prepare(tmp_path)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'wuwa', 'source_locale': 'en',
        'publisher_song_cues': 3, 'records': rows}))
    index = MultilingualTextIndex('wuwa', tmp_path)
    context = EndfieldCaptionContext()
    latest = None
    for number, row in enumerate(rows):
        direct = index.match_full_frame_voice_lines([row['source_text']])
        if number == 2:
            assert [hit.text_id for hit in direct] == [rows[0]['text_id']]
        for frame in (0, 1):
            hit = context.observe(index, [row['source_text']], direct, channel='cinematic', kind='music_subtitle',
                                  scope=1, now=number + frame * .1, stable_frames=2, prefer_authored_occurrence=True)
            if hit:
                latest = hit
    assert latest and latest.text_id == rows[2]['text_id']


def test_missing_song_audio_uses_predecessor_only_after_opt_in_without_audio_or_default_ocr(tmp_path):
    import asyncio
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from backend.capture import _ScanOutcome
    from backend.tests.test_local_chatter import row as ocr_row
    from backend.tests.test_subtitle_capture import fixture_service
    fixture(tmp_path)
    rows = prepare(tmp_path, 'ja')
    rows[1]['requires_previous'] = True
    directory = tmp_path / 'prepared'; directory.mkdir()
    (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'wuwa', 'source_locale': 'ja',
        'publisher_song_cues': 2, 'publisher_song_voices': 0, 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('wuwa', directory)
    service, _, scheduled, published = fixture_service(tmp_path, game='wuwa')
    window = SimpleNamespace(handle=1, bounds=(0, 0, 1920, 1080), title='Authored fixture')
    scans = []
    response = {'lines': [ocr_row(rows[0]['source_text'], .03, .12, size=(800, 200))]}
    engine = SimpleNamespace(recognize_pil=lambda image: scans.append(image.size) or response)
    def scan():
        index.capture_missing_audio = service.settings.get().capture_missing_audio
        return service._with_unvoiced(_ScanOutcome([]), index, window, engine, 0,
                                      datetime.now(timezone.utc), 'wuwa')
    async def run():
        service._event_loop = asyncio.get_running_loop()
        assert not scan().emitted_lines and not scans and index.audio_count == 0
        service.settings.save(service.settings.get().model_copy(update={'capture_missing_audio': True}))
        response['lines'] = [ocr_row(rows[1]['source_text'], .03, .12, size=(800, 200))]
        assert not scan().emitted_lines
        response['lines'] = [ocr_row(rows[0]['source_text'], .03, .12, size=(800, 200))]
        assert not scan().emitted_lines
        assert [line.text_id for line in scan().emitted_lines] == [rows[0]['text_id']]
        response['lines'] = [ocr_row(rows[1]['source_text'], .03, .12, size=(800, 200))]
        assert not scan().emitted_lines
        assert [line.text_id for line in scan().emitted_lines] == [rows[1]['text_id']]
        await asyncio.sleep(.02)
        assert len(published) == 2 and not scheduled
        assert all(line.voice_status == 'unavailable' for line in published)
    try:
        asyncio.run(run())
    finally:
        service._executor.shutdown()
