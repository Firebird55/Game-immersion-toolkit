"""Synthetic Source fixtures only; no redistributable game assets required."""
import json
from pathlib import Path
import struct

import pytest

from backend import halflife2_assets as assets
from backend.local_game import LocalDialogue, LocalGameTextIndex
from backend.multilingual_index import MultilingualTextIndex
from backend.preparation_errors import PreparationFailure
from backend.source_dialogue import unpack_performance
from backend.source_scene import scene_image
from backend.tests.test_portal_assets import compiled, image_fixture, localization, pcm, write_vpk


def manifest(root, language='english', *, state=4):
    (root.parent.parent / 'appmanifest_220.acf').write_text(
        f'"AppState" {{ "appid" "220" "installdir" "{root.name}" "StateFlags" "{state}" '
        f'"MountedConfig" {{ "language" "{language}" }} "UserConfig" {{ "language" "{language}" }} }}')


def bsp(entities):
    data = entities.encode() + b'\0'
    header = bytearray(1036)
    struct.pack_into('<4sI4I', header, 0, b'VBSP', 20, 1036, len(data), 0, 0)
    return header + data


@pytest.fixture
def installed(tmp_path):
    root = tmp_path / 'steamapps/common/SyntheticHL2'
    root.mkdir(parents=True)
    (root / 'hl2.exe').write_bytes(b'fixture')
    manifest(root)
    for number, (mount, spec) in enumerate(assets.CAMPAIGNS.items()):
        (root / mount / 'maps').mkdir(parents=True)
        (root / mount / 'gameinfo.txt').write_text('"GameInfo" { "game" "Synthetic Source" }')
        prefix = {'hl2': 'd1', 'episodic': 'ep1', 'ep2': 'ep2'}[mount]
        (root / mount / 'maps' / f'{prefix}_synthetic.bsp').write_bytes(bsp(
            '{ "classname" "game_text" "message" "#Synthetic_Readable" "x" "-1" "y" "0.5" }'))
        files = {
            'scripts/game_sounds_manifest.txt': b'"game_sounds_manifest" { "precache_file" "scripts/speech.txt" }',
            'scripts/speech.txt': (f'"{mount}.one" {{ "channel" "CHAN_VOICE" "wave" "vo/{mount}/one.wav" }} '
                f'"{mount}.two" {{ "wave" "vo/{mount}/two.wav" }} '
                '"npc_citizen.random" { "rndwave" { "wave" "vo/a.wav" "wave" "vo/b.wav" } }').encode(),
            'scenes/scenes.image': image_fixture([(f'{mount}.one', f'{mount}.combined', 1, 2, 0),
                (f'{mount}.two', f'{mount}.combined', 2.5, 3, 1)]),
            'scripts/titles.txt': b'$position -1 0.58\nCHAPTER1_TITLE\n{\n#Synthetic_Chapter\n}\n',
            'scripts/sentences.txt': b'SYNTHETIC_DYNAMIC npc/voice/(p100) V_RANDOM\n',
        }
        for locale, native in assets.TEXT_LOCALES.items():
            rows = {f'{mount}.one': f'{native} opening words for {mount}.',
                f'{mount}.two': f'{native} later words for {mount}.',
                f'{mount}.combined': f'{native} first authored page.<delay:2>{native} second authored page.',
                'npc_citizen.random': f'{native} generic citizen words.',
                'unknown.binding': f'{native} unresolved voice.',
                f'#commentary/{mount}.wav': f'{native} commentary for {mount}.',
                'fx.noise': '<sfx>[Synthetic noise]'}
            files[f'resource/closecaption_{native}.txt'] = localization(native, rows)
            files[f'resource/closecaption_{native}.dat'] = compiled(rows)
            files[f'resource/{mount}_{native}.txt'] = localization(native, {
                'Synthetic_Readable': f'{native} readable in {mount}.',
                'Synthetic_Chapter': f'{native} chapter in {mount}.'})
        voices = {f'sound/vo/{mount}/one.wav': pcm(number * 10 + 1),
                  f'sound/vo/{mount}/two.wav': pcm(number * 10 + 2),
                  f'sound/commentary/{mount}.wav': pcm(number * 10 + 3)}
        if mount == 'hl2':
            write_vpk(root / 'hl2/hl2_sound_vo_english_dir.vpk', voices)
        else:
            files.update(voices)
        write_vpk(root / mount / f"{spec['stem']}_pak_dir.vpk", files)
    return root


def test_complete_campaign_pipeline_and_no_future_caption_join(installed, tmp_path):
    result = assets.index_language(installed, tmp_path, 'en', ['zh-Hant', 'ja'])
    assert set(result['campaign_coverage']) == set(assets.CAMPAIGNS)
    assert result['missing_translation_locales'] == []
    assert assets.discover_install([installed]) == installed
    assert assets.probe_voice_pack(installed, 'en') == 'present'
    for mount in assets.CAMPAIGNS:
        rows = {row['text_id']: row for row in result['records']}
        first = rows[f'halflife2:{mount}:caption:{mount}.one']
        later = rows[f'halflife2:{mount}:caption:{mount}.two']
        assert later['source_text'] not in first['source_text']
        pages = [row for row in result['records'] if row['text_id'].startswith(f'halflife2:{mount}:caption:{mount}.combined:page:')]
        assert len(pages) == 2
        assert pages[0]['audio'] == pages[1]['audio']
        assert pages[0]['source_text'] != pages[1]['source_text']
        assert pages[0]['dialogue_kind'] == 'subtitle_full_track'
        assert pages[0]['audio']['playback_scope'] == 'full_track'
        assert [part['at_ms'] for part in pages[0]['audio']['parts']] == [0, 1500]
        blobs = unpack_performance(assets.extract_voice(installed, pages[0]['audio'], None, tmp_path))
        assert len(blobs) == 2 and blobs[0] != blobs[1]
        assert result['campaign_coverage'][mount]['excluded_sound_effect_captions'] == 1
        assert result['campaign_coverage'][mount]['unresolved_caption_bindings'] == 2
    assert len([row for row in result['records'] if row['voice_status'] == 'unvoiced']) == 6
    assert all('ja' in row['texts'] for row in result['records'])
    for row in result['records']:
        LocalDialogue(**row)


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_all_official_campaign_voice_locales_and_absent_packs(installed, tmp_path, locale):
    if locale != 'en':
        assert assets.probe_voice_pack(installed, locale) == 'missing'
        missing = assets.index_language(installed, tmp_path, locale, [])
        assert not any(row['audio'] for row in missing['records'])
        assert any('Install the official' in message for message in missing['coverage_warnings'])
        assert all(row['voice_status'] == 'unavailable' for row in missing['records'] if row['dialogue_kind'] != 'readable')
    native = assets.TEXT_LOCALES[locale]
    for mount, spec in assets.CAMPAIGNS.items():
        write_vpk(installed / mount / f"{spec['stem']}_sound_vo_{native}_dir.vpk", {
            f'sound/vo/{mount}/one.wav': pcm(77)})
    result = assets.index_language(installed, tmp_path, locale, [])
    assert assets.probe_voice_pack(installed, locale) == 'present'
    for mount, spec in assets.CAMPAIGNS.items():
        row = next(row for row in result['records'] if row['text_id'] == f'halflife2:{mount}:caption:{mount}.one')
        if locale in spec['voices']:
            assert row['audio']['locale'] == locale
            assert unpack_performance(assets.extract_voice(installed, row['audio'], None, tmp_path)) == [pcm(77)]
        else:
            assert row['audio'] is None
            assert row['voice_status'] == 'unavailable'


def test_no_shared_english_when_manifest_is_localized_or_incomplete(installed, tmp_path):
    manifest(installed, 'french')
    result = assets.index_install(installed, tmp_path)
    assert any(row['audio'] for row in result['records'] if row['text_id'].startswith('halflife2:hl2:'))
    assert not any(row['audio'] for row in result['records'] if row['text_id'].startswith('halflife2:ep2:'))
    manifest(installed, state=6)
    assert not assets._voices(installed, 'episodic', 'en').locate('sound/vo/episodic/one.wav')


def test_voice_reference_revalidated_and_pcm_decoded(installed, tmp_path):
    row = next(row for row in assets.index_install(installed, tmp_path)['records'] if row['audio'])
    data = assets.extract_voice(installed, row['audio'], None, tmp_path)
    output = tmp_path / 'decoded.wav'
    assets.decode_voice_source(data, row['audio'], output, None, tmp_path)
    assert output.read_bytes() == unpack_performance(data)[0]
    for altered in (dict(row['audio'], campaign='ep2'), dict(row['audio'], locale='fr'),
                    dict(row['audio'], token='../invalid'), dict(row['audio'], parts=[])):
        with pytest.raises(PreparationFailure):
            assets.extract_voice(installed, altered, None, tmp_path)


def test_episode_windows_1252_scene_strings_are_explicit_and_bounded():
    image = image_fixture([('Speech.One', 'Caption.One', 0, 1, 0)])
    # Replace one single-byte actor label character, preserving authored offsets.
    native = image.replace(b'actor\0', b'act\x92r\0')
    with pytest.raises(PreparationFailure, match='encoding'):
        scene_image(native)
    assert scene_image(native, string_encoding='cp1252') == scene_image(image)
    with pytest.raises(PreparationFailure):
        scene_image(native[:-1], string_encoding='cp1252')


def test_native_hud_entities_are_text_only_and_malformed_maps_are_explicit(installed, tmp_path):
    path = installed / 'hl2/maps/d1_synthetic.bsp'
    assert assets._map_entities(path)[0]['classname'] == 'game_text'
    damaged = bytearray(path.read_bytes())
    struct.pack_into('<I', damaged, 8, len(damaged) + 1)
    path.write_bytes(damaged)
    with pytest.raises(PreparationFailure, match='bounds'):
        assets._map_entities(path)
    result = assets.index_install(installed, tmp_path)
    assert result['campaign_coverage']['hl2']['unsupported_map_readables'] == 1
    assert any('map entity resources could not be decoded' in message for message in result['coverage_warnings'])


def test_both_indexes_exact_match_and_unvoiced_toggle(installed, tmp_path):
    result = assets.index_language(installed, tmp_path, 'en', ['zh-Hans'])
    (tmp_path / 'textmap.json').write_text(json.dumps(result), encoding='utf-8')
    current = next(row for row in result['records'] if row['text_id'] == 'halflife2:hl2:caption:hl2.one')
    readable = next(row for row in result['records'] if row['voice_status'] == 'unvoiced')
    unknown = next(row for row in result['records'] if row['voice_status'] == 'unavailable')
    for index in (MultilingualTextIndex('halflife2', tmp_path), LocalGameTextIndex('halflife2', tmp_path)):
        assert index.ready
        hit = index.match_lines([current['source_text']])
        assert hit and hit.text_id == current['text_id']
        assert index.match_lines([readable['source_text']]) is None
        index.capture_unvoiced = True
        assert index.match_lines([readable['source_text']]).voice_status == 'unvoiced'
        assert index.match_lines([unknown['source_text']]) is None


def test_installed_mount_inventory_never_imports_half_life_source_or_lost_coast(installed, tmp_path):
    for mount in ('hl1', 'lostcoast', 'hl2mp'):
        write_vpk(installed / mount / f'{mount}_pak_dir.vpk', {'sound/vo/unrelated.wav': pcm(88)})
    assert set(assets._campaigns(installed)) == {'hl2', 'episodic', 'ep2'}
    assert not any(part in str(path) for path in assets.archive_sources(installed) for part in ('lostcoast', 'hl2mp', '/hl1/'))
