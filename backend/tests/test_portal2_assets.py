"""Synthetic Portal 2 base/DLC, localized packs, movies and credit timelines."""
from pathlib import Path
import json
import struct

import pytest

from backend import portal2_assets as assets
from backend.preparation_errors import PreparationFailure
from backend.source_dialogue import unpack_performance
from backend.tests.test_portal_assets import compiled, image_fixture, localization, pcm, write_vpk


def image_v3():
    # VSIF3 inserts last-speech time between duration and sound count.
    raw = bytearray(image_fixture([('Test.One', 'group', 0, 1, 0)]))
    entries = struct.unpack_from('<I', raw, 16)[0]
    identity, offset, size, summary = struct.unpack_from('<4I', raw, entries)
    raw[4:8] = struct.pack('<I', 3)
    raw[summary + 4:summary + 4] = struct.pack('<I', 1000)
    struct.pack_into('<4I', raw, entries, identity, offset + 4, size, summary)
    return bytes(raw)


def manifest(root, language='english', state=4):
    (root.parent.parent / 'appmanifest_620.acf').write_text(
        f'"AppState" {{ "appid" "620" "installdir" "{root.name}" "StateFlags" "{state}" '
        f'"MountedConfig" {{ "language" "{language}" }} "UserConfig" {{ "language" "{language}" }} }}')


def bink_header():
    value = bytearray(b'BIKi' + struct.pack('<10I', 84, 1, 1, 1, 1280, 720, 24, 1, 0, 4))
    value += bytes(16)
    value += b''.join(struct.pack('<HH', 44100, 0x7000 if stereo else 0x5000) for stereo in (True, False, False, True))
    return bytes(value + struct.pack('<4I', 0, 1, 2, 3))


@pytest.fixture
def installed(tmp_path):
    root = tmp_path / 'steamapps/common/SyntheticPortal2'
    root.mkdir(parents=True)
    (root / 'portal2.exe').write_bytes(b'fixture')
    (root / 'portal2').mkdir()
    (root / 'portal2/gameinfo.txt').write_text('"GameInfo" { "FileSystem" { "SteamAppId" "620" "SearchPaths" { "Game" "|gameinfo_path|." } } }')
    manifest(root)
    base = {
        'scripts/game_sounds_manifest.txt': b'"game_sounds_manifest" { "precache_file" "scripts/speech.txt" [!$GAMECONSOLE] }',
        'scripts/speech.txt': b'''"Test.One" { "wave" "vo/test/one.wav" }
            "Test.Dlc" { "wave" "vo/test/dlc.wav" }
            "Test.Random" { "rndwave" { "wave" "vo/test/one.wav" "wave" "vo/test/dlc.wav" } }
            "music.sp_a5_credits" { "wave" "music/song.wav" }''',
        'scenes/scenes.image': image_v3(),
        'scripts/credits.txt': b'''"credits.txt" { "OutroSongLyrics" {
            "[1.0]Synthetic report" "Font" "[1.0]Synthetic heading" "Font"
            "[1.0]^" "Font" "[2.0]Synthetic first lyric" "Font" "[1.0] " "Font"
            "[2.0]Synthetic second lyric" "Font" } }''',
        'sound/vo/test/one.wav': pcm(11),
        'sound/music/song.wav': pcm(12),
    }
    base_rows = {'test.one': 'Original synthetic caption.', 'test.random': 'A random caption.',
                 'test.missing': 'An unavailable caption.', 'fx.sound': '<sfx>[Synthetic sound]',
                 'commentary_title_one': 'A commentary heading.', '#commentary/test.wav': 'Synthetic commentary.'}
    for locale, native in assets.TEXT_LOCALES.items():
        base[f'resource/subtitles_{native}.txt'] = localization(native, base_rows)
        base[f'resource/subtitles_{native}.dat'] = compiled(base_rows)
        base[f'resource/portal2_{native}.txt'] = localization(native, {
            'cheaptitles_test.movie': 'Only the current synthetic movie cue.',
            'cheaptitles_test.later': 'A later synthetic movie cue.'})
    write_vpk(root / 'portal2/pak01_dir.vpk', base)
    dlc = {'sound/vo/test/dlc.wav': pcm(22)}
    for locale, native in assets.TEXT_LOCALES.items():
        rows = {'test.one': 'Updated synthetic caption.', 'test.dlc': 'Synthetic DLC caption.',
                'test.movie_dlc': 'Synthetic DLC movie caption.'}
        dlc[f'resource/subtitles_{native}.txt'] = localization(native, rows)
        dlc[f'resource/subtitles_{native}.dat'] = compiled(rows)
    write_vpk(root / 'portal2_dlc1/pak01_dir.vpk', dlc)
    (root / 'portal2_dlc1/gameinfo.txt').write_text('"GameInfo" { "FileSystem" { "SteamAppId" "620" "SearchPaths" { "Game" "|gameinfo_path|." "Game" "portal2" } } }')
    media = root / 'portal2/media'; media.mkdir()
    (media / 'coop_outro_captions.txt').write_text('#cheaptitles_test.movie\n0xFFFFFFFF\n1.25\n2.75\n#cheaptitles_test.later\n0xFFFFFFFF\n3\n4\n')
    (media / 'coop_outro.bik').write_bytes(bink_header())
    media_dlc = root / 'portal2_dlc1/media';media_dlc.mkdir()
    (media_dlc / 'dlc1_endmovie_captions.txt').write_text('#cheaptitles_test.movie_dlc\n0xFFFFFFFF\n1\n2\n')
    (media_dlc / 'dlc1_endmovie.bik').write_bytes(bink_header())
    return root


def test_base_and_dlc_captions_are_additive_with_priority(installed, tmp_path):
    result = assets.index_language(installed, tmp_path, 'en', ['ja', 'zh-Hans'])
    rows = {r['text_id']: r for r in result['records']}
    assert rows['portal2:caption:test.one']['source_text'] == 'Updated synthetic caption.'
    assert rows['portal2:caption:test.dlc']['audio']['parts'][0]['archive'].startswith('portal2_dlc1/')
    assert rows['portal2:caption:test.random']['voice_status'] == 'unavailable'
    assert rows['portal2:caption:test.missing']['voice_status'] == 'unavailable'
    assert rows['portal2:caption:commentary_title_one']['voice_status'] == 'unvoiced'
    assert result['diagnostics']['excluded_sound_effect_captions'] == 1
    assert result['diagnostics']['movie_caption_segments'] == 3
    assert result['diagnostics']['credits_lyric_segments'] == 2
    assert all('ja' in r['texts'] for r in result['records'] if ':credits:' not in r['text_id'])
    assert assets.discover_install([installed]) == installed
    assert assets.probe_voice_pack(installed, 'en') == 'present'


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_all_official_voice_locales_are_isolated_even_with_missing_packs(installed, tmp_path, locale):
    if locale != 'en':
        assert assets.probe_voice_pack(installed, locale) == 'missing'
        result = assets.index_language(installed, tmp_path, locale, [])
        assert not any(row['audio'] for row in result['records'])
        assert not any(row['dialogue_kind'] == 'song_full_track' for row in result['records'])
    native = assets.TEXT_LOCALES[locale]
    write_vpk(installed / f'portal2_{native}/pak01_dir.vpk', {'sound/vo/test/one.wav': pcm(77)})
    result = assets.index_language(installed, tmp_path, locale, [])
    audio = next(r['audio'] for r in result['records'] if r['text_id'] == 'portal2:caption:test.one')
    assert audio['locale'] == locale
    assert unpack_performance(assets.extract_voice(installed, audio, None, tmp_path)) == [pcm(77)]
    assert assets.probe_voice_pack(installed, locale) == 'present'


def test_high_priority_loose_files_override_lower_vpk_and_fingerprint_tracks_them(installed):
    before = assets.fingerprint(installed)
    path = installed / 'update/scripts/speech.txt';path.parent.mkdir(parents=True)
    path.write_text('"Test.One" { "wave" "vo/test/dlc.wav" }')
    assert assets._files(installed).read('scripts/speech.txt') == path.read_bytes()
    assert assets.fingerprint(installed) != before
    manifest(installed, 'french')
    assert assets.probe_voice_pack(installed, 'en') == 'missing'
    assert assets.probe_voice_pack(installed, 'fr') == 'missing'


def test_gameinfo_searchpath_priority_is_honored_without_external_mounts(installed):
    path = installed / 'portal2_dlc1/gameinfo.txt'
    path.write_text('"GameInfo" { "FileSystem" { "SteamAppId" "620" "SearchPaths" { "Game" "portal2" "Game" "|gameinfo_path|." "Game" "../external" } } }')
    assert assets._mounts(installed) == ['update', 'portal2', 'portal2_dlc1']
    assert assets._tables(assets._files(installed), 'en')[0]['test.one'] == 'Original synthetic caption.'
    path.write_text('"GameInfo" { "FileSystem" { "SteamAppId" "999" } }')
    with pytest.raises(PreparationFailure, match='identity'):
        assets._files(installed)


def test_duplicate_named_text_uses_compiled_caption(installed):
    root = installed / 'update/resource';root.mkdir(parents=True)
    (root / 'subtitles_english.txt').write_bytes(localization('english', {'test.one': 'Stale fixture.'}).replace(
        '"test.one" "Stale fixture."'.encode('utf-16-le'), '"test.one" "Stale fixture." "test.one" "Other stale fixture."'.encode('utf-16-le')))
    (root / 'subtitles_english.dat').write_bytes(compiled({'test.one': 'Authoritative compiled fixture.'}))
    assert assets._tables(assets._files(installed), 'en')[0]['test.one'] == 'Authoritative compiled fixture.'


def test_shipped_latam_cr_insertion_is_reversed_without_translation_fallback(installed):
    root = installed / 'update/resource';root.mkdir(parents=True)
    source = '"lang" {\r\n"Language" "latam"\r\n"Tokens" { "test.one" "Synthetic local text." }\r\n}\r\n'.encode('utf-16')
    damaged = source.replace(b'\n', b'\r\n')
    (root / 'subtitles_latam.txt').write_bytes(damaged)
    (root / 'subtitles_latam.dat').write_bytes(compiled({'test.one': 'Compiled regional text.'}))
    assert assets._localized_bytes(damaged, 'latam') == source
    assert assets._localized_bytes(damaged, 'french') == damaged
    assert assets._tables(assets._files(installed), 'es-419')[0]['test.one'] == 'Compiled regional text.'
    assert assets._localized_bytes(b'\xff\xfe\x00\xd8', 'latam') == b'\xff\xfe\x00\xd8'


def test_movie_and_song_rows_never_include_later_cues_and_revalidate_offsets(installed, tmp_path, monkeypatch):
    result = assets.index_install(installed, tmp_path)
    movies = [r for r in result['records'] if r['dialogue_kind'] == 'cinematic']
    assert movies[0]['audio']['clip_ms'] == [1250, 2750]
    assert 'later' not in movies[0]['source_text']
    songs = [r for r in result['records'] if r['dialogue_kind'] == 'song_full_track']
    assert songs[0]['audio']['playback_scope'] == 'full_track'
    assert songs[0]['audio'] == songs[1]['audio']
    assert 'clip_ms' not in songs[0]['audio']
    assert 'second' not in songs[0]['source_text']
    changed = dict(movies[0]['audio'], clip_ms=[0, 4000])
    with pytest.raises(PreparationFailure, match='binding changed'):
        assets.extract_voice(installed, changed, None, tmp_path)
    calls = []
    monkeypatch.setattr('backend.media_tools.ffmpeg_executable', lambda: Path('decoder'))
    def decode(command, **options):
        calls.append(command)
        # A complete synthetic 1.5-second clip.
        import io, wave
        stream=io.BytesIO()
        with wave.open(stream,'wb') as writer:
            writer.setparams((1,2,8000,0,'NONE','not compressed'));writer.writeframes(bytes(24000))
        Path(command[-1]).write_bytes(stream.getvalue())
    monkeypatch.setattr(assets.subprocess, 'run', decode)
    assert unpack_performance(assets.extract_voice(installed, movies[0]['audio'], None, tmp_path))[0][:4] == b'RIFF'
    assert '[0:a:0][0:a:1][0:a:2][0:a:3]amix=inputs=4:normalize=1[out]' in calls[0]


def test_scene_movie_layout_and_caption_timing_bounds(installed):
    assert len(assets._scene_image(image_v3())) == 1
    assert assets._movie_layout(installed / 'portal2/media/coop_outro.bik') == 4
    for raw in (image_v3()[:-1], b'VSIF\x02' + image_v3()[5:]):
        with pytest.raises(PreparationFailure):
            assets._scene_image(raw)
    movie = installed / 'portal2/media/coop_outro.bik'
    movie.write_bytes(bink_header()[:-1])
    with pytest.raises(PreparationFailure, match='layout'):
        assets._movie_layout(movie)
    captions = installed / 'portal2/media/coop_outro_captions.txt'
    captions.write_text('#cheaptitles_test.movie\n0xFFFFFFFF\nnan\n2\n')
    with pytest.raises(PreparationFailure, match='timing'):
        assets._movies(assets._files(installed))


def test_normalized_snapshot_capture_toggle_and_ambiguous_performances(installed, tmp_path):
    from backend.local_game import LocalDialogue
    from backend.multilingual_index import MultilingualTextIndex
    result = assets.index_install(installed, tmp_path)
    for row in result['records']:
        assert LocalDialogue(**row).source_text
        assert row['texts'][row['source_locale']] == row['source_text']
        assert all(text.strip() for text in row['texts'].values())
    original = next(row for row in result['records'] if row['text_id'] == 'portal2:caption:test.one')
    alternative = next(row for row in result['records'] if row['text_id'] == 'portal2:caption:test.dlc')
    result['records'].append(dict(original, text_id='portal2:caption:another-performance', audio=alternative['audio']))
    (tmp_path / 'textmap.json').write_text(json.dumps(result))
    index = MultilingualTextIndex('portal2', tmp_path)
    assert index.ready
    assert index.match_lines([original['source_text']]) is None
    assert index.match_lines(['A commentary heading.']) is None
    index.capture_unvoiced = True
    heading = index.match_lines(['A commentary heading.'])
    assert heading.voice_status == 'unvoiced'
    assert heading.text_id == 'portal2:caption:commentary_title_one'
