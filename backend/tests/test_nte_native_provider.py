"""Source selection/closure boundaries; no native or publisher downloads."""
from dataclasses import asdict
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import nte_native_provider as provider, nte_native_metadata as metadata
from backend import nte_publisher as publisher, nte_release as release, nte_type_metadata
from backend.nte_type_metadata import Schema
from backend.preparation_errors import PreparationFailure


def fixture(tmp_path, monkeypatch, *, partial=True, graphs=False):
    monkeypatch.setattr(publisher, '_reader_identity', lambda: 'f'*64)
    names = ['Client/Plugin.dll', 'Client/RenamedApplication.exe']
    files = {name: asdict(release.File(100+index, str(index+1)*32, 100+index, str(index+1)*32, 0))
             for index, name in enumerate(names)}
    snapshot = dict(region='nte-global', branch='PC_9', version='9.0.1', sections={}, publisher_files=files,
                    reader='f'*64, archive=['archive', 'a'*64], localization=['localization', 'b'*64])
    snapshot['type_schema'] = provider.source_reference(provider.discovery(snapshot), snapshot['reader'], dialogue_graphs=graphs)
    catalog = SimpleNamespace(snapshot=snapshot, cache=tmp_path/'cache', stamp='nte-'+'1'*64,
                              region='nte-global', format=SimpleNamespace(parameters={'nte-global': 'owned'}), containers=lambda: [])
    staging = tmp_path/'staging'; staging.mkdir()
    baseline = SimpleNamespace(identity={'native_path': names[0], 'native_md5': 'e'*32})
    monkeypatch.setattr(provider.baseline_source, 'load', lambda *_: baseline)
    monkeypatch.setattr(provider, 'seed', lambda *_: b'owned-seed')
    if graphs:
        monkeypatch.setattr(provider, '_registry', lambda _: b'checked-original-registry')
        from backend import nte_graph_prefetch
        monkeypatch.setattr(provider.assets, 'read_dialogue_inventory', lambda *_: {'HT/Content/Owned.uasset': 20})
        def prefetch(containers, packages, _progress):
            assert containers == [] and packages == {'HT/Content/Owned.uasset': 20}
        monkeypatch.setattr(nte_graph_prefetch, 'prefetch', prefetch)
    calls, candidates = [], {}
    monkeypatch.setattr(metadata, 'stage_original', lambda _v, name, _c: tmp_path/name.rsplit('/', 1)[-1])
    def prepare(_original, _seed, sources, cache, **kwargs):
        name = next(iter(sources)); calls.append(name)
        digest = hashlib.sha256(name.encode()).hexdigest()
        assert kwargs['native_classes'] is graphs
        reference = {'native_generator': metadata.CLASS_GENERATOR if graphs else metadata.ENUM_GENERATOR,
                     'generation': digest, 'sha256': digest}
        result = metadata.Candidate(Schema(reference, name.encode()), {
            'source_manifest_sha256': snapshot['type_schema']['inventory_sha256'], 'dependencies': {'reader': snapshot['reader']},
            'baseline_sha256': snapshot['type_schema']['baseline_native_sha256'], 'native_path': name,
            'generator': reference['native_generator']})
        candidates[digest] = result
        return result
    monkeypatch.setattr(metadata, 'prepare', prepare)
    monkeypatch.setattr(metadata, 'load', lambda ref, _c: candidates[ref['generation']])
    def extract(_context, _exe, output, *_args, **kwargs):
        assert kwargs['capture_schema_usage'] is True
        assert kwargs['capture_dialogue_graphs'] is graphs
        assert kwargs['dialogue_registry'] == (b'checked-original-registry' if graphs else None)
        for name in provider.OUTPUTS: (output/name).write_text('{}')
        if graphs: (output/'dialogue-graphs.json').write_text('{"owned":true}')
        return {'schema': 'nte-schema-usage-v2' if graphs else 'nte-schema-usage-v1',
                'lookups': ['RequiredDynamic'], 'classes': {},
                **({'codecs': {'OwnedPath': 'CUE4Parse.UE4.Objects.Owned.FOwnedPath'}} if graphs else {})}
    monkeypatch.setattr(provider.assets, 'run_publisher_reader', extract)
    def check(ref, cache, *_args, **kwargs):
        assert kwargs['reader_codecs'] == ({'OwnedPath': 'CUE4Parse.UE4.Objects.Owned.FOwnedPath'} if graphs else None)
        candidate = candidates[ref['generation']]
        eligible = not partial or candidate.receipt['native_path'] == names[1]
        data = b'{"owned":true}'; identity = hashlib.sha256(data).hexdigest()
        path = cache/'validations'/(identity+'.json'); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        return SimpleNamespace(eligible=eligible), identity
    monkeypatch.setattr(metadata, 'check_required', check)
    monkeypatch.setattr(nte_type_metadata, 'load', lambda *_a, **_k: pytest.fail('Followed a community mapping'))
    return catalog, staging, names, calls


def test_manifest_lineage_is_only_a_hint_and_partial_plugin_cannot_publish_authoring(tmp_path, monkeypatch):
    catalog, staging, names, calls = fixture(tmp_path, monkeypatch)
    schema, _ = provider.read_authoring(catalog, tmp_path/'reader', staging)
    assert calls == names and schema['generation'] == hashlib.sha256(names[1].encode()).hexdigest()
    profile = catalog.cache/'native-epochs'/catalog.stamp/'profile.json'
    assert json.loads(profile.read_bytes())['native_path'] == names[1]
    assert all((staging/name).is_file() for name in provider.OUTPUTS)


def test_opt_in_graph_recipe_validates_complete_invocation_and_retains_immutable_profile(tmp_path, monkeypatch):
    catalog, staging, _, _ = fixture(tmp_path, monkeypatch, graphs=True)
    schema, validation = provider.read_authoring(catalog, tmp_path/'reader', staging)
    assert schema['native_generator'] == metadata.CLASS_GENERATOR
    assert (staging/'dialogue-graphs.json').read_bytes() == b'{"owned":true}'
    second = tmp_path/'second'; second.mkdir()
    assert provider.read_authoring(catalog, tmp_path/'reader', second) == (schema, validation)
    assert not provider.DIALOGUE_GRAPHS


def test_all_unsupported_required_layouts_leave_no_resolved_profile_or_partial_outputs(tmp_path, monkeypatch):
    catalog, staging, _, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(metadata, 'check_required', lambda *_a, **_k: (SimpleNamespace(eligible=False), 'a'*64))
    with pytest.raises(PreparationFailure):
        provider.read_authoring(catalog, tmp_path/'reader', staging)
    assert list(staging.iterdir()) == []
    assert not (catalog.cache/'native-epochs'/catalog.stamp/'profile.json').exists()


@pytest.mark.parametrize('stage', ['acquisition', 'reader', 'integrity'])
def test_io_timeout_or_integrity_failure_never_attempts_an_unrelated_native_source(tmp_path, monkeypatch, stage):
    catalog, staging, names, calls = fixture(tmp_path, monkeypatch)
    attempts = []
    if stage == 'acquisition':
        def failed(_value, name, _cache):
            attempts.append(name); raise OSError('Owned acquisition timeout')
        monkeypatch.setattr(metadata, 'stage_original', failed)
    elif stage == 'reader':
        def failed(*_args, **_kwargs):
            raise PreparationFailure('game_metadata_unavailable', 'Owned publisher stream timed out; retry preparation.')
        monkeypatch.setattr(provider.assets, 'run_publisher_reader', failed)
    else:
        def failed(*_args, **_kwargs): raise ValueError('Owned source authentication failure')
        monkeypatch.setattr(metadata, 'check_required', failed)
    with pytest.raises(PreparationFailure) as error:
        provider.read_authoring(catalog, tmp_path/'reader', staging)
    assert error.value.code == 'game_metadata_unavailable'
    assert (attempts if stage == 'acquisition' else calls) == [names[0]]
    assert not list(staging.iterdir())
    assert not (catalog.cache/'native-epochs'/catalog.stamp/'profile.json').exists()


def test_explicit_native_derivation_rejection_can_try_the_next_original_owner(tmp_path, monkeypatch):
    catalog, staging, names, calls = fixture(tmp_path, monkeypatch)
    prepare = metadata.prepare
    rejected = []
    def selected(*args, **kwargs):
        name = next(iter(args[2]))
        if name == names[0]:
            rejected.append(name); raise metadata.NativeDerivationRejected('Owned non-schema source')
        return prepare(*args, **kwargs)
    monkeypatch.setattr(metadata, 'prepare', selected)
    provider.read_authoring(catalog, tmp_path/'reader', staging)
    assert rejected == [names[0]] and calls == [names[1]]


def test_declared_native_byte_and_file_budgets_do_not_accept_a_partial_plugin(tmp_path, monkeypatch):
    catalog, staging, names, calls = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(provider, 'MAX_SOURCE_BYTES', 100)
    with pytest.raises(PreparationFailure):
        provider.read_authoring(catalog, tmp_path/'reader', staging)
    assert calls == [names[0]] and not list(staging.iterdir())


def test_renamed_manifest_entry_uses_generic_pe_order_without_a_game_filename_list():
    entries = {'Client/OtherTool.exe': release.File(10, 'a'*32, 10, 'a'*32, 0),
               'Client/ChangedName.EXE': release.File(30, 'b'*32, 30, 'b'*32, 0),
               'Client/Library.dll': release.File(99, 'c'*32, 99, 'c'*32, 0)}
    assert provider._order(entries, 'Client/AbsentOldOwner.exe') == ['Client/ChangedName.EXE', 'Client/OtherTool.exe', 'Client/Library.dll']


def test_changed_reader_identity_cannot_use_a_stale_source_recipe(tmp_path, monkeypatch):
    catalog, staging, _, calls = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(publisher, '_reader_identity', lambda: 'e'*64)
    with pytest.raises(ValueError):
        provider.read_authoring(catalog, tmp_path/'reader', staging)
    assert calls == [] and not list(staging.iterdir())


def test_fingerprint_uses_complete_original_recipe_and_frozen_parameter_sources(tmp_path, monkeypatch):
    original = {'Client/WindowsNoEditor/HT/Content/Game.pak': release.File(10, 'a'*32, 10, 'a'*32, 0),
                'Client/OriginalApplication.exe': release.File(20, 'b'*32, 20, 'b'*32, 0)}
    monkeypatch.setattr(publisher.release, 'discover', lambda _: ('PC_9', '9.0.1', original, {}))
    monkeypatch.setattr(publisher, '_reader_identity', lambda: 'f'*64)
    observed = []
    def load(**kwargs):
        observed.append(kwargs); return SimpleNamespace(revision=kwargs['revision'], digest=kwargs['digest'])
    monkeypatch.setattr(publisher.metadata, 'load', load)
    monkeypatch.setattr(publisher.metadata, 'load_localization', load)
    monkeypatch.setattr(nte_type_metadata, 'load', lambda *_a, **_k: pytest.fail('Followed current community mappings'))
    publisher._current.cache_clear()
    try:
        stamp, value = publisher._current(tmp_path, 1, 'nte-global')
        assert value['type_schema']['kind'] == provider.KIND and set(value['publisher_files']) == set(original)
        assert len(value['files']) == 1 and publisher.snapshot(tmp_path, stamp) == value
        assert [(r['revision'], r['digest']) for r in observed] == [publisher.NATIVE_ARCHIVE, publisher.NATIVE_LOCALIZATION]
        # Historical readers keep their stored identities, even after a later
        # toolkit uses a different generator/validator for new source recipes.
        monkeypatch.setattr(metadata, 'ENUM_GENERATOR', 'nte-owned-next-generator')
        assert publisher.snapshot(tmp_path, stamp) == value
    finally:
        publisher._current.cache_clear()
