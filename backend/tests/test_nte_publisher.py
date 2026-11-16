"""Publisher orchestration contracts, using only independently authored assets."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import nte_assets as assets, nte_publisher as publisher
from backend import nte_release as release
from backend.preparation_errors import PreparationFailure
from backend.tests.test_new_game_assets import bank
from backend.tests.test_nte_locres import resource


def test_patch_precedence_is_numeric_and_equal_order_claims_never_choose_a_filename():
    base, first, later = 'Paks/chunk.pak', 'TagPatchPaks/chunk_0_P.pak', 'PatchPaks/chunk_2_P.pak'
    data = {base: ['one', 'base'], first: ['one'], later: ['one']}
    assert publisher._overlay(data, lambda paths: paths)['one'][0] == later
    assert publisher._overlay(data, lambda paths: paths)['base'][0] == base
    with pytest.raises(PreparationFailure):
        publisher._overlay({first: ['one'], 'PatchPaks/other_0_P.pak': ['ONE']}, lambda paths: paths)


def descriptor(tmp_path, generation):
    file = release.File(12, str(generation) * 32, 12, str(generation) * 32, 0)
    value = {'schema': publisher.SCHEMA, 'region': 'nte-global', 'branch': 'PC_123', 'version': '1.2.' + str(generation),
             'files': {publisher.ROOT + 'Paks/chunk.pak': vars(file)}, 'sections': {'baseTag': [12, '1.2.0']},
             'archive': ['a' * 40, 'b' * 64], 'localization': ['c' * 40, 'd' * 64], 'type_schema': {'synthetic': True}}
    raw = publisher._json(value)
    stamp = 'nte-' + hashlib.sha256(raw).hexdigest()
    publisher._atomic_file(publisher._path(tmp_path, stamp), raw)
    return stamp, value


def test_immutable_snapshot_rejects_changed_bytes_and_invalid_history_references(tmp_path):
    stamp, value = descriptor(tmp_path, 1)
    assert publisher.snapshot_available(tmp_path, stamp)
    assert publisher.snapshot(tmp_path, stamp) == value
    publisher._path(tmp_path, stamp).write_bytes(publisher._json({**value, 'version': '1.2.9'}))
    assert not publisher.snapshot_available(tmp_path, stamp)
    assert not publisher.snapshot_available(tmp_path, '../../another-source')


def test_authoring_context_includes_import_dependencies_outside_table_directories(tmp_path, monkeypatch):
    catalog = publisher.Catalog.__new__(publisher.Catalog)
    catalog.region, catalog.branch, catalog.cache = 'nte-global', 'PC_123', tmp_path
    catalog.archives = {'proof.pak': SimpleNamespace(cipher=object())}
    paths = {
        'Paks/global.utoc': {},
        'Paks/tables.utoc': {'ht/content/datatable/owned.uasset': ('HT/Content/DataTable/Owned.uasset', 0)},
        'Paks/imports.utoc': {'ht/content/blueprint/types.uasset': ('HT/Content/Blueprint/Types.uasset', 0)},
    }
    catalog.files = {}
    containers = {}
    for number, (name, entries) in enumerate(paths.items(), 1):
        item = release.File(100, str(number) * 32, 100, str(number) * 32, 0)
        catalog.files[publisher.ROOT + name] = item
        catalog.files[publisher.ROOT + name[:-5] + '.ucas'] = item
        containers[item.digest] = SimpleNamespace(paths=entries)
    monkeypatch.setattr(publisher.iostore, 'Container', lambda region, branch, toc, *_: containers[toc.digest])
    assert set(catalog.containers()) == set(paths)


@pytest.fixture
def online(monkeypatch, tmp_path):
    tools = tmp_path / 'tools'
    states = dict(descriptor(tools, n) for n in (1, 2))
    current = [next(iter(states))]
    event = 'Play_Vo_Line'
    media = 'HT/Content/WwiseAudio/Media/English/123.wem'
    bnk = 'HT/Content/WwiseAudio/Event/English/' + event + '.bnk'
    originals = {}
    for generation, stamp in enumerate(states, 1):
        text = [('ST_MainDialogue', 'line', f'Source revision {generation}.', generation)]
        # The target's unchanged source hash must not become a new translation.
        translation = [('ST_MainDialogue', 'line', 'Authored translation.', 1)]
        payload = b'owned-voice-' + bytes([generation])
        wem = b'RIFF' + (len(payload) + 4).to_bytes(4, 'little') + b'WAVE' + payload
        originals[stamp] = {
            'HT/Content/Localization/Game/en/Game.locres': resource(text, encrypted=False),
            'HT/Content/Localization/Game/fr/Game.locres': resource(translation, encrypted=False),
            bnk: bank(version=154, bank_id=assets.wwise_hash(event), language=assets.wwise_hash('English'), event=assets.wwise_hash(event)),
            media: wem,
        }

    class Catalog:
        def __init__(self, chosen_tools, stamp, progress=lambda _: None):
            self.tools, self.stamp = chosen_tools, stamp
            self.snapshot = publisher.snapshot(chosen_tools, stamp)
            self.cache = tools / 'nte-publisher'
            self.format = SimpleNamespace(parameters={'nte-global': 'synthetic-format'})
            archive = SimpleNamespace(
                entry=lambda name: SimpleNamespace(size=len(originals[stamp][name]), stored=len(originals[stamp][name])),
                read_many=lambda names: [originals[stamp][n] for n in names])
            self.locations = {n.casefold(): ('fixture.pak', archive, n) for n in originals[stamp]}

        def location(self, name):
            return self.locations.get(name.casefold())

        def read(self, name):
            return originals[self.stamp][self.location(name)[2]]

        def containers(self):
            return {'owned.utoc': self.stamp}

        def prefetch(self, paths):
            assert paths == [bnk]

    flip = [False]

    def reader(context, executable, destination, containers, parameters, **kwargs):
        # Source/native readers protect their immutable executable directory.
        # The former tools/nte-publisher staging location fails this contract.
        assert not destination.resolve().is_relative_to(executable.parent.resolve())
        assert destination != context and parameters == 'synthetic-format'
        (destination / 'dialogue-events.json').write_text(json.dumps({'line': [event.lower()]}))
        (destination / 'voice-events.json').write_text(json.dumps([event]))
        (destination / 'sequence-cues.json').write_text(json.dumps({'groups': {}, 'events': {}}))
        movie = {'StringTableID': 'Sequence', 'Path': {'FilePath': '../../../Projects/HT/Content/Movies/FFMpeg/Story/owned.mp4'},
                 'PlayVoice': {'AssetPathName': '/Game/WwiseAudio/Events/CG/Owned/Play_Vo_CG_Owned.Play_Vo_CG_Owned'}}
        (destination / 'movie-tables.json').write_text(json.dumps({
            'DT_MediaFFmpegInfo.json': [{'Type': 'DataTable', 'Rows': {'one': movie}}],
            'DT_MediaFFmpegInfo_Quest.json': [{'Type': 'DataTable', 'Rows': {}}]}))
        if flip[0]:
            current[0] = list(states)[1]

    monkeypatch.setattr(publisher, 'Catalog', Catalog)
    monkeypatch.setattr(publisher, '_current', lambda *_: (current[0], states[current[0]]))
    monkeypatch.setattr(publisher, '_discovery', lambda _: {k: states[current[0]][k] for k in ('region', 'branch', 'version', 'files', 'sections')})
    monkeypatch.setattr(publisher.metadata, 'load_localization', lambda **_: SimpleNamespace(parameter=None))
    monkeypatch.setattr(publisher.type_metadata, 'load', lambda *args, **_: SimpleNamespace(reference={'sha256': 'f' * 64}, data=b'owned schema'))
    monkeypatch.setattr(assets, 'ensure_extractor', lambda path: path / 'NteReader.dll')
    monkeypatch.setattr(assets, 'run_publisher_reader', reader)
    publisher._voices.cache_clear()
    yield SimpleNamespace(root=tmp_path, tools=tools, states=states, current=current, originals=originals, media=media, flip=flip)
    publisher._voices.cache_clear()


def test_normal_adapter_prepares_updates_and_replays_its_original_snapshot_without_discovery(online, monkeypatch):
    first = assets.index_language(None, online.root, 'en', ['fr'])
    row = first['records'][0]
    assert row['texts'] == {'en': 'Source revision 1.', 'fr': 'Authored translation.'}
    assert row['audio']['publisher'] == first['fingerprint'] and first['install'] is None
    assert row['voice_status'] == 'voiced' and first['source_mode'] == 'publisher'
    first_audio = dict(row['audio'])
    online.current[0] = list(online.states)[1]
    second = assets.index_language(None, online.root, 'en', ['fr'])
    assert second['records'][0]['source_text'] == 'Source revision 2.'
    assert 'fr' not in second['records'][0]['texts']
    assert second['missing_translation_locales'] == ['fr']
    assert any('did not match' in w for w in second['coverage_warnings'])
    assert second['fingerprint'] != first['fingerprint']
    monkeypatch.setattr(publisher, '_discovery', lambda *_: pytest.fail('Playback consulted current discovery'))
    executable = online.tools / 'NteReader.dll'
    before = assets.extract_voice(None, first_audio, executable, online.root / 'unused')
    after = assets.extract_voice(None, second['records'][0]['audio'], executable, online.root / 'unused')
    assert before == online.originals[first['fingerprint']][online.media]
    assert before != after
    assert assets.extract_voices(None, [first_audio, first_audio], executable, online.root / 'unused') == [before, before]
    forged = {**first_audio, 'archive': 'older.pak'}
    with pytest.raises(PreparationFailure):
        assets.extract_voice(None, forged, executable, online.root / 'unused')


def test_mid_preparation_revision_change_never_returns_an_activatable_partial_index(online):
    previous = assets.index_language(None, online.root, 'en', [])
    online.flip[0] = True
    with pytest.raises(PreparationFailure, match='changed during preparation'):
        assets.index_language(None, online.root, 'en', [])
    assert previous['records'][0]['source_text'] == 'Source revision 1.'
    assert publisher.snapshot_available(online.tools, previous['fingerprint'])
