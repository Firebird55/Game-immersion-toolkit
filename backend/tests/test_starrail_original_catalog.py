"""Original discovery preserves saved IDs without a data-publication inventory."""
import hashlib
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_design as design, starrail_films as films
from backend.starrail_caption_compat import LEGACY_IDENTITIES
from backend.starrail_original_catalog import OriginalCatalog
from backend.starrail_original_configs import OriginalConfigs
from backend.xxhash64 import xxhash64


def uint(number):
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128); number >>= 7
    return bytes(result + bytes([number]))


class Descriptions:
    registries = {}

    def binary_path(self, path):
        return 'Original/' + path[:-5] + '.bin'

    def enum(self, name):
        return None

    def description(self, name):
        # A synthetic changed native field order: EndTime is bit 2, not the
        # frozen fallback caption codec's bit 3.
        return {'fields': [('CaptionList', 'RPG.GameCore.VideoCaption[]')] if name.endswith('Config')
            else [('CaptionTextID', 'RPG.Client.TextID'), ('StartTime', 'float'), ('EndTime', 'float')],
            'defaults': {}}


def fixture(tmp_path, monkeypatch, paths, *, anonymous=(), legacy=None, folder=''):
    descriptions = Descriptions()
    raw, entries, resources, texts = bytearray(), [], {}, {}
    for number, path in enumerate([*paths, *anonymous], 1):
        key = xxhash64(descriptions.binary_path(path).encode())
        body = b'\x01\x02\x05\x00' + uint(number) + struct.pack('<f', 1.)
        entries.append((key, len(body), len(raw)))
        texts[str(number)] = 'A fixture caption ' + str(number)
        raw.extend(body)
    package = bytes(raw)
    digest = hashlib.md5(package).hexdigest()
    asset = SimpleNamespace(size=len(package), digest=digest)
    resources.update({key: (asset, start, length) for key, length, start in entries})
    def authenticated(selected):
        assert selected.digest == hashlib.md5(package).hexdigest() and selected.size == len(package)
        return package
    source = {'VideoConfig': [{'VideoID': i, 'VideoPath': f'Movie{i}.usm', 'CaptionPath': path}
                             for i, path in enumerate(paths, 1)],
              'CutSceneConfig': [], 'LoopCGConfig': [], 'PerformanceVideo': [], 'VoiceConfig': []}
    tables = SimpleNamespace(directory=tmp_path, resources=resources, _package=authenticated,
        file=lambda path, optional=False: source[path.removeprefix('ExcelOutput/').removesuffix('.json')])
    monkeypatch.setattr(design.hotfix, 'audio_roots', lambda build: ({'design': 'https://publisher.invalid/'}, {}))
    monkeypatch.setattr(design.hotfix, 'index', lambda *args: b'original-index')
    monkeypatch.setattr(design, '_packages', lambda data, with_folder=False: [(digest, len(package), entries, folder)])
    monkeypatch.setattr(design.hotfix.AudioFile, 'read', lambda *args: pytest.fail('Use the whole authenticated package'))
    configs = OriginalConfigs(tables, descriptions)
    catalog = OriginalCatalog(tables, configs, {}, revision='original-test', build={}, legacy=legacy)
    return catalog, source, texts


def test_all_old_identities_and_new_generic_captions_survive_without_inventory_entries(tmp_path, monkeypatch):
    assert len(LEGACY_IDENTITIES) == 173
    old_paths = ['Config/CutSceneCaption/' + name for name in LEGACY_IDENTITIES]
    new_paths = [f'Config/CutSceneCaption/Unseen{i}_Caption.json' for i in range(138)]
    # One historical caption is discovered as an anonymous neighbor, never
    # requested through the compatibility map.
    catalog, source, texts = fixture(tmp_path, monkeypatch, old_paths[1:] + new_paths,
        anonymous=[old_paths[0], 'Config/CutSceneCaption/UnknownNeighbor_Caption.json'])
    scripts = dict(catalog.caption_scripts())
    assert len(scripts) == 312
    assert set(LEGACY_IDENTITIES.values()) <= set(catalog.caption_identities.values())
    for path in new_paths:
        filename = path.rsplit('/', 1)[1]
        assert catalog.caption_identities[filename] == f'design_{xxhash64(catalog.configs.descriptions.binary_path(path).encode()):016x}'
    assert len(catalog.caption_identity_aliases) == 1
    rows = films.caption_rows(tmp_path, catalog, {'en': texts}, 'en', {})
    ids = {row['text_id'] for row in rows}
    assert {f'starrail:film-{identity}-0' for identity in LEGACY_IDENTITIES.values()} <= ids
    assert all(row['voice_status'] == 'unavailable' and row['audio'] is None for row in rows)
    assert catalog.caption_scripts() is catalog.caption_scripts()


def test_unseen_film_repacked_under_new_folder_needs_no_compatibility_entry(tmp_path, monkeypatch):
    path = 'Config/CutSceneCaption/NewRelease_Caption.json'
    catalog, _, _ = fixture(tmp_path, monkeypatch, [path], legacy={}, folder='ja')
    script, = catalog.caption_scripts()
    assert script[0] == 'NewRelease_Caption.json'
    assert catalog.caption_identities[script[0]].startswith('design_')
    assert not catalog.unresolved_caption_paths


@pytest.mark.parametrize('legacy', [
    {'A_Caption.json': 'Other'}, {'../A_Caption.json': '../A'},
    {'A_Caption.json': 'A', 'B_Caption.json': 'A'}])
def test_conflicting_or_unsafe_saved_identity_aliases_fail_before_original_inventory(legacy):
    with pytest.raises(ValueError):
        OriginalCatalog(None, None, {}, revision='original-test', build={}, legacy=legacy)


def test_compatibility_names_cannot_request_absent_content(tmp_path, monkeypatch):
    catalog, _, _ = fixture(tmp_path, monkeypatch, ['Config/CutSceneCaption/Actual_Caption.json'],
                           legacy={'Missing_Caption.json': 'Missing'})
    scripts = dict(catalog.caption_scripts())
    assert set(scripts) == {'Actual_Caption.json'}
    assert 'Missing' not in catalog.caption_identities.values()


@pytest.mark.parametrize('owner,video,authored', [(5, 1, True), (6, 1, False), (5, 99, False)])
def test_only_original_movie_mission_and_action_owners_name_a_conditional_caption(tmp_path, monkeypatch, owner, video, authored):
    primary, alternate = [f'Config/CutSceneCaption/{name}_Caption.json' for name in ('Primary', 'Alternate')]
    catalog, source, _ = fixture(tmp_path, monkeypatch, [primary], anonymous=[alternate], legacy={})
    mission = 'Config/Level/Mission/5/Act/Act77.json'
    source['PerformanceVideo'] = [{'PerformanceID': 999, 'PerformancePath': mission}]
    catalog.movie_files = {'movie1.usm': SimpleNamespace(task_ids=(owner,))}
    read, loaded = catalog.configs.file, []
    def config(path):
        loaded.append(path)
        return {'OnStartSequece': [{'TaskList': [{'$type': 'RPG.GameCore.PlayVideo',
            'VideoID': video, 'OverrideCaptionPath': alternate}]}]} if path == mission else read(path)
    catalog.configs.file = config
    scripts = dict(catalog.caption_scripts())
    assert ('Alternate_Caption.json' in scripts) is authored
    assert (mission in loaded) is (owner == 5)
    assert len(scripts) == 2  # Unowned neighboring captions remain anonymous.


def test_original_textmap_locales_do_not_invent_mirror_transport_splits():
    assert len(OriginalCatalog.text_locales) == 13
    assert OriginalCatalog.text_locales['ko'] == ('MainKR', 'KR')
    assert OriginalCatalog.text_locales['ru'] == ('MainRU', 'RU')
    assert OriginalCatalog.text_locales['th'] == ('MainTH', 'TH')


def test_existing_language_preparation_uses_the_catalog_textmap_contract(tmp_path, monkeypatch):
    from backend import starrail_assets, starrail_publisher, publisher_regions
    from backend.dialogue_catalog import selected_tables
    calls = []
    catalog = SimpleNamespace(text_locales=OriginalCatalog.text_locales,
        file=lambda path, optional=False: calls.append(path) or {'1': 'Fixture'})
    assert selected_tables(catalog, catalog.text_locales, 'en', ['ko', 'ru', 'th']).keys() == {'en', 'ko', 'ru', 'th'}
    assert {'TextMap/TextMapKR.json', 'TextMap/TextMapRU.json', 'TextMap/TextMapTH.json'} <= set(calls)
    assert not any('_0' in path or '_1' in path for path in calls)
    monkeypatch.setattr(publisher_regions, 'selected_region', lambda *args: 'global')
    monkeypatch.setattr(starrail_publisher, 'prepare', lambda *args: ('original-stamp', catalog))
    class ReachedOriginalTextmaps(Exception):
        pass
    def read(selected, mapping, source, targets):
        assert selected is catalog and mapping is OriginalCatalog.text_locales
        raise ReachedOriginalTextmaps
    monkeypatch.setattr(starrail_assets, 'selected_tables', read)
    with pytest.raises(ReachedOriginalTextmaps):
        starrail_assets.index_language(None, tmp_path, 'en', ['ko'])
