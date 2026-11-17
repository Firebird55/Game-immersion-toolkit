"""Synthetic CRI audio and metadata: no game media, real format keys or network."""
import hashlib
import json
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_movie_audio as audio, starrail_movie_metadata as metadata
from backend.local_voice import _source_suffix
# Reuse the existing typed UTF fixture instead of introducing another writer.
from backend.tests.test_persona5_assets import table


def chunk(kind, track, data, content=0):
    header = bytearray(32)
    header[:4] = kind
    struct.pack_into('>I', header, 4, 24 + len(data))
    header[9], header[12], header[15] = 24, track, content
    return bytes(header) + data


def adx(marker=3):
    header = bytearray(32)
    header[:4] = b'\x80\x00\x00\x1c'
    struct.pack_into('>BBBBIIH', header, 4, 3, 18, 4, 2, 48000, 2048, 500)
    header[18] = 4
    header[26:32] = b'(c)CRI'
    return bytes(header) + (b'\0\x02' + bytes([marker]) * 16) * 128 + b'\x80\x01' + bytes(16)


def movie(*, masked=True, duplicate=False):
    en, ja = adx(3), adx(5)
    rows = [{'stmid': int.from_bytes(b'@SFA', 'big'), 'chno': ch, 'filename': f'mix_{dub}#{ch:02}.sfa'}
            for dub, ch in [('EN', 7), ('JP', 2)]]
    if duplicate:
        rows.append({'stmid': int.from_bytes(b'@SFA', 'big'), 'chno': 5, 'filename': 'other_EN#05.sfa'})
    result = chunk(b'CRID', 3, table([('stmid', 4), ('chno', 2), ('filename', 10)], rows), 1)
    # Independent fixed reference vector for the deliberately synthetic key 7.
    mask = [248, 85, 255, 82, 6, 85, 158, 67, 255, 85, 0, 82, 248, 85, 52, 67,
            255, 85, 0, 82, 56, 85, 109, 67, 7, 85, 228, 82, 223, 85, 126, 67]
    for number, track in [(7, en), (2, ja)]:
        for start, end in [(0, 501), (501, len(track))]:
            packet = track[start:end]
            if masked:
                packet = packet[:320] + bytes(value ^ mask[i % 32] for i, value in enumerate(packet[320:]))
            result += chunk(b'@SFA', number, packet)
    return result, en, ja


def asset(body, name='Scene.usm'):
    reads = []
    def read(directory, start, size):
        reads.append((start, size))
        return body[start:start + size]
    return SimpleNamespace(name=name, size=len(body), digest=hashlib.md5(body).hexdigest(), read=read, reads=reads)


def catalog(a, *, revision='1' * 40, key=7, previous=None, variants=None):
    history = {'path/' + a.name: {'versions': [*(previous or []), {'version': '1.1.0', 'md5': a.digest, 'size': a.size}]}}
    return metadata.Catalog(revision, 'a' * 64, history, {a.name[:-4]: f'{key:016x}'}, variants or {})


@pytest.mark.parametrize('masked', [False, True])
def test_reads_named_dub_with_packet_reset_and_complete_samples(tmp_path, masked):
    body, en, ja = movie(masked=masked)
    path = tmp_path / 'movie.usm'
    path.write_bytes(body)
    key = 7 if masked else 0
    selected = audio.read_track(path, 'en', key)
    assert selected.data == en and selected.samples == 2048 and selected.channels == 2 and selected.rate == 48000
    assert audio.read_track(path, 'ja', key).data == ja
    assert _source_suffix(selected.data, {'movie': 'Scene.usm'}, 'starrail') == '.adx'
    with pytest.raises(ValueError):
        audio.read_track(path, 'ko', key)
    path.write_bytes(movie(masked=masked, duplicate=True)[0])
    with pytest.raises(ValueError):
        audio.read_track(path, 'en', key)


def test_refuses_truncated_or_premature_eof_instead_of_accepting_decoder_success(tmp_path):
    body, en, _ = movie()
    path = tmp_path / 'movie.usm'
    path.write_bytes(body[:-5])
    with pytest.raises(ValueError):
        audio.read_track(path, 'en', 7)
    broken = bytearray(en)
    broken[32 + 18 * 6] = 128
    with pytest.raises(ValueError):
        audio._adx(broken)
    with pytest.raises(ValueError):
        audio._adx(en[:-40])


def test_changed_movie_needs_exact_metadata_and_historical_key_selection():
    body, _, _ = movie()
    before = asset(body)
    old = catalog(before)
    changed = asset(body + b'new generation')
    with pytest.raises(ValueError):
        old.key_for(changed)
    previous = [{'version': '1.0.0', 'md5': before.digest, 'size': before.size}]
    new = catalog(changed, key=9, previous=previous)
    assert new.key_for(changed) == 9 and old.key_for(before) == 7
    with pytest.raises(ValueError):
        new.key_for(before)
    new = catalog(changed, key=9, previous=previous, variants={'Scene': {'1.0.0': f'{7:016x}', '1.1.0': f'{9:016x}'}})
    assert new.key_for(before) == 7 and new.key_for(changed) == 9


def test_verified_original_audio_replays_offline_and_failed_update_keeps_it(tmp_path):
    body, en, ja = movie()
    before = asset(body)
    source = catalog(before)
    assert audio.recording(tmp_path, before, 'en', source).data == en
    before.reads.clear()
    assert audio.recording(tmp_path, before, 'en', source, hashlib.sha256(en).hexdigest()).data == en
    assert not before.reads
    assert audio.recording(tmp_path, before, 'ja', source).data == ja
    changed = asset(body)
    changed.digest = 'b' * 32
    with pytest.raises(ValueError):
        audio.recording(tmp_path, changed, 'en', catalog(changed))
    before.read = lambda *_: pytest.fail('Old recording must remain playable offline')
    assert audio.recording(tmp_path, before, 'en', source).data == en


def test_pinned_metadata_cache_validates_complete_digest_and_never_executes_data(tmp_path, monkeypatch):
    body, _, _ = movie()
    a = asset(body)
    c = catalog(a)
    documents = dict(zip(metadata.FILES, map(json.dumps, [c.history, c.keys, c.variants])))
    monkeypatch.setattr(metadata, 'latest_revision', lambda: c.revision)
    from backend.tests.test_starrail_movie_source import source_fixture
    source_fixture(monkeypatch, documents, c.revision)
    first = metadata.load(tmp_path)
    assert first.key_for(a) == 7
    monkeypatch.setattr(metadata, 'download', lambda *_a, **_k: pytest.fail('Pinned offline metadata read'))
    assert metadata.load(tmp_path, first.revision, first.digest).key_for(a) == 7
    with pytest.raises(ValueError):
        metadata.load(tmp_path, first.revision, 'b' * 64)


def test_normal_caption_preparation_uses_spoken_windows_and_rejects_changed_track(tmp_path, monkeypatch):
    from backend import starrail_films as films
    scene, video, locale, digest, text_hash = 'FixtureMovie', 24, 'en', 'c' * 64, 77
    monkeypatch.setattr(films, 'MOVIE_AUDIO_CUTS', {(scene, video, locale, digest): {text_hash: (200, 6550)}})
    tables = {'en': {str(text_hash): 'Fixture sentence', '9': 'Unreviewed sentence'}}
    source = {'ExcelOutput/CutSceneConfig.json': [], 'ExcelOutput/VoiceConfig.json': [],
              'ExcelOutput/VideoConfig.json': [{'VideoID': video, 'VideoPath': 'Scene.usm',
                  'CaptionPath': f'Config/CutSceneCaption/{scene}_Caption.json'}]}
    a = asset(b'fixture source')
    scripts = [(scene + '_Caption.json', {'CaptionList': [
        {'CaptionTextID': {'Hash': text_hash}, 'StartTime': .333, 'EndTime': 6.633},
        {'CaptionTextID': {'Hash': 9}, 'StartTime': 7, 'EndTime': 8}]})]
    c = SimpleNamespace(file=source.__getitem__, movie_files={'scene.usm': a},
                        caption_scripts=lambda: scripts, movie_audio_source=(tmp_path, 'publisher', '1' * 40))
    selected = {'publisher': 'publisher', 'locale': 'en', 'movie': 'Scene.usm', 'recording_sha256': digest}
    monkeypatch.setattr(metadata, 'load', lambda *_: object())
    monkeypatch.setattr(audio, 'binding', lambda *_: (dict(selected), 53433))
    first, unavailable = films.caption_rows(tmp_path, c, tables, 'en', {})
    assert first['voice_status'] == 'voiced' and unavailable['audio'] is None
    assert (first['audio']['start_ms'], first['audio']['end_ms']) == (200, 6550)
    assert first['film_caption']['start_ms'] == 333
    selected['recording_sha256'] = 'b' * 64
    changed, _ = films.caption_rows(tmp_path, c, tables, 'en', {})
    assert changed['audio'] is None and c.movie_audio_incomplete
    assert first['audio']['recording_sha256'] == digest


def test_protagonist_movies_require_each_branch_recording_and_keep_missing_counterpart(tmp_path, monkeypatch):
    from backend import starrail_films as films
    male_hash, female_hash = 'c' * 64, 'd' * 64
    scene, video, caption = 'PlayerMovie', 24, 77
    monkeypatch.setattr(films, 'MOVIE_AUDIO_CUTS', {
        (scene, video, 'en', male_hash): {caption: (100, 900)},
        (scene, video, 'en', female_hash): {caption: (200, 1100)},
    })
    source = {'ExcelOutput/CutSceneConfig.json': [], 'ExcelOutput/VoiceConfig.json': [],
              'ExcelOutput/VideoConfig.json': [{'VideoID': video, 'VideoPath': 'Player.usm',
                  'IsPlayerInvolved': True, 'CaptionPath': f'Config/CutSceneCaption/{scene}_Caption.json'}]}
    male = SimpleNamespace(name='Player_m.usm', size=99, digest='a' * 32)
    female = SimpleNamespace(name='Player_f.usm', size=101, digest='b' * 32)
    scripts = [(scene + '_Caption.json', {'CaptionList': [
        {'CaptionTextID': {'Hash': caption}, 'StartTime': .333, 'EndTime': .633}]})]
    c = SimpleNamespace(file=source.__getitem__, movie_files={'player_m.usm': male, 'player_f.usm': female},
                        caption_scripts=lambda: scripts, movie_audio_source=(tmp_path, 'publisher', '1' * 40))
    hashes = {male.name: male_hash, female.name: female_hash}
    reads = []
    monkeypatch.setattr(metadata, 'load', lambda *_: object())
    def binding(directory, stamp, movie, locale, formats):
        reads.append(movie.name)
        return {'publisher': stamp, 'locale': locale, 'movie': movie.name,
                'recording_sha256': hashes[movie.name]}, 2000
    monkeypatch.setattr(audio, 'binding', binding)
    def prepare():
        return films.caption_rows(tmp_path, c, {
            'en': {str(caption): 'Fixture {M#brother}{F#sister}'},
            'ja': {str(caption): '{M#兄}{F#姉}の例'}}, 'en', {})
    first, second = prepare()
    assert (first['player_voice'], second['player_voice']) == ('male', 'female')
    assert (first['text_id'], second['text_id']) == (
        f'starrail:film-{scene}-0_m', f'starrail:film-{scene}-0_f')
    assert first['audio']['movie'] == male.name and first['audio']['start_ms'] == 100
    assert second['audio']['movie'] == female.name and second['audio']['start_ms'] == 200
    assert reads == [male.name, female.name]
    assert first['source_text'] == 'Fixture brother' and first['texts']['ja'] == '兄の例'
    assert second['source_text'] == 'Fixture sister' and second['texts']['ja'] == '姉の例'
    # A changed take cannot borrow the other protagonist's reviewed window.
    hashes[male.name] = female_hash + '0'
    changed, retained = prepare()
    assert changed['audio'] is None and retained['audio'] == second['audio']
    assert c.movie_audio_incomplete
    del c.movie_files['player_m.usm']
    missing, retained = prepare()
    assert missing['player_voice'] == 'male' and missing['voice_status'] == 'unavailable'
    assert retained['audio'] == second['audio']
    # Two plausible files for one player remain ambiguous independently.
    c.movie_files['player_m.usm'] = male
    other = SimpleNamespace(name='Other_m.usm', size=80, digest='e' * 32)
    c.movie_files['other_m.usm'] = other
    source['ExcelOutput/VideoConfig.json'].append(
        source['ExcelOutput/VideoConfig.json'][0] | {'VideoID': 25, 'VideoPath': 'Other.usm'})
    ambiguous, retained = prepare()
    assert ambiguous['audio'] is None and retained['audio'] == second['audio']


def test_format_updates_change_freshness_without_game_or_toolkit_update(tmp_path, monkeypatch):
    from backend import starrail_publisher as publisher, starrail_original_provider as original
    state = {'revision': '1' * 40, 'time': 60}
    monkeypatch.setattr(original, 'release', lambda *_: ({'channel': 'starrail-global', 'version': '4.7.0'}, None))
    monkeypatch.setattr(metadata, 'check_latest', lambda *_: (state['revision'], False))
    monkeypatch.setattr(publisher.time, 'monotonic', lambda: state['time'])
    publisher._poll.cache_clear()
    previous = publisher.fingerprint('global', tmp_path)
    state.update(revision='2' * 40, time=90)
    assert publisher.fingerprint('global', tmp_path) != previous
    assert not publisher.current(previous, 'global', tmp_path)
    publisher._poll.cache_clear()


def test_optional_format_outage_retains_known_revision_and_recovers(tmp_path, monkeypatch):
    from urllib.error import URLError
    monkeypatch.setattr(metadata, 'load', lambda *_: object())
    monkeypatch.setattr(metadata, 'latest_revision', lambda: '1' * 40)
    assert metadata.check_latest(tmp_path) == ('1' * 40, False)
    def offline():
        raise URLError('offline fixture')
    monkeypatch.setattr(metadata, 'latest_revision', offline)
    assert metadata.check_latest(tmp_path) == ('1' * 40, True)
    assert metadata.check_latest(tmp_path / 'fresh') == (None, True)
    monkeypatch.setattr(metadata, 'latest_revision', lambda: '2' * 40)
    assert metadata.check_latest(tmp_path) == ('2' * 40, False)


def test_actual_worker_keeps_film_provenance_outside_validated_dialogue_rows(tmp_path, monkeypatch):
    from backend import language_worker, starrail_assets as assets, starrail_publisher as publisher
    from backend import starrail_films as films, starrail_events, hoyo_publisher_voice as voices
    c = SimpleNamespace(revision='1' * 40, revision_title='fixture')
    monkeypatch.setattr(publisher, 'prepare', lambda *_: ('publisher', c))
    monkeypatch.setattr(publisher, 'current', lambda *_: True)
    monkeypatch.setattr(assets, 'selected_tables', lambda *_: {'en': {}})
    monkeypatch.setattr(assets, 'authored_links', lambda *_: [])
    monkeypatch.setattr(assets, '_readable_records', lambda *_: [])
    monkeypatch.setattr(voices, 'inventory', lambda *_: {})
    monkeypatch.setattr(starrail_events, 'bindings', lambda *_: {})
    provenance = {'scene': 'Fixture', 'start_ms': 100, 'end_ms': 200, 'movies': []}
    row = {'text_id': 'starrail:fixture', 'source_locale': 'en', 'source_text': 'Fixture',
           'texts': {'en': 'Fixture'}, 'english': 'Fixture', 'chinese': '', 'audio_locale': 'en',
           'audio': {'publisher': 'publisher', 'locale': 'en', 'movie': 'Scene.usm'},
           'voice_status': 'voiced', 'dialogue_kind': 'cutscene_caption', 'film_caption': provenance}
    monkeypatch.setattr(films, 'caption_rows', lambda *_: [dict(row)])
    out = tmp_path / 'candidate.json'
    language_worker.build('starrail', None, tmp_path / 'data', 'en', (), out)
    prepared = json.loads(out.read_bytes())
    assert prepared['film_captions'] == {'starrail:fixture': provenance}
    assert 'film_caption' not in prepared['records'][0]
    assert prepared['dialogue_inventory']['voice_counts']['voiced'] == 1
