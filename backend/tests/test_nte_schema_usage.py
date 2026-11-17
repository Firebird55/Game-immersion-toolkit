"""Current-invocation evidence and compiled owned comparer/logging guards."""
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from backend import nte_assets as assets
from backend.nte_type_metadata import Schema
from backend.preparation_errors import PreparationFailure
from backend.tests.test_nte_native_schema import seed


def packet():
    return dict(schema='nte-schema-usage-v1', complete=True, nonce='b'*32, schema_sha256='a'*64,
                lookups=['Known', 'NewDynamic'], classes={'EngineTable': 'CUE4Parse.UE4.Assets.Exports.Engine.UEngineTable'})


@pytest.mark.parametrize('change', [
    lambda p: p.update(complete=False), lambda p: p.update(nonce='c'*32), lambda p: p.update(schema_sha256='d'*64),
    lambda p: p.update(lookups=[]), lambda p: p.update(lookups=['Known', 'Known']),
    lambda p: p.update(lookups=['../Unknown']), lambda p: p.update(classes={'EngineTable': 'Game.Client.UEngineTable'}),
    lambda p: p.update(classes={'EngineTable': 'CUE4Parse.UE4.Assets.Exports.Engine.UDifferent'}),
    lambda p: p.pop('complete'), lambda p: p.update(extra='unexpected'),
])
def test_stale_incomplete_or_unattested_usage_is_not_accepted(tmp_path, change):
    value = packet(); change(value)
    (tmp_path/'schema-usage.json').write_text(json.dumps(value))
    with pytest.raises(PreparationFailure) as error:
        assets.read_schema_usage(tmp_path, 'a'*64, 'b'*32)
    assert error.value.code == 'game_metadata_unavailable'


def test_valid_current_invocation_usage_is_returned_without_inventing_a_type_list(tmp_path):
    value = packet()
    (tmp_path/'schema-usage.json').write_text(json.dumps(value))
    assert assets.read_schema_usage(tmp_path, 'a'*64, 'b'*32) == value


def codec_packet():
    return packet() | dict(schema='nte-schema-usage-v2', codecs_origin='zero-without-package-v1',
        codecs={'CustomPath': 'CUE4Parse.UE4.Objects.UObject.FCustomPath'})


def test_concrete_codec_contract_retains_actual_lookups_and_generic_factory_origin(tmp_path):
    value = codec_packet()
    (tmp_path/'schema-usage.json').write_text(json.dumps(value))
    assert assets.read_schema_usage(tmp_path, 'a'*64, 'b'*32) == value


@pytest.mark.parametrize('change', [
    lambda p: p.update(codecs_origin='guessed'), lambda p: p.update(codecs=[]),
    lambda p: p.update(codecs={'Known': 'CUE4Parse.UE4.Objects.UObject.FKnown'}),
    lambda p: p.update(codecs={'CustomPath': 'CUE4Parse.UE4.Assets.Objects.FStructFallback'}),
    lambda p: p.update(codecs={'CustomPath': 'Game.Client.FCustomPath'}),
    lambda p: p.update(codecs={'../Bad': 'CUE4Parse.UE4.Objects.UObject.FCustomPath'}),
    lambda p: p.pop('codecs_origin'), lambda p: p.update(extra='unattested'),
])
def test_unattested_fallback_or_actually_looked_up_codec_is_rejected(tmp_path, change):
    value = codec_packet(); change(value)
    (tmp_path/'schema-usage.json').write_text(json.dumps(value))
    with pytest.raises(PreparationFailure): assets.read_schema_usage(tmp_path, 'a'*64, 'b'*32)


@pytest.mark.parametrize('capture', [False, True])
def test_usage_is_opt_in_and_preserves_legacy_four_output_contract(tmp_path, monkeypatch, capture):
    from backend import nte_publisher_stream
    class Broker:
        descriptors, failures = [], []
        def __init__(self, _): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
    monkeypatch.setattr(nte_publisher_stream, 'Broker', Broker)
    monkeypatch.setattr(assets, '_reader_invocation', lambda *_: (['owned'], None, tmp_path))
    requests = []
    def run(_command, **kwargs):
        value = json.loads(kwargs['input']); requests.append(value)
        for name in ('dialogue-events.json', 'sequence-cues.json', 'voice-events.json', 'movie-tables.json'):
            (tmp_path/name).write_text('{}')
        if capture:
            usage = packet() | {'schema_sha256': value['type_schema_sha256'], 'nonce': value['schema_usage_nonce']}
            (tmp_path/'schema-usage.json').write_text(json.dumps(usage))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(assets.subprocess, 'run', run)
    data = seed('Known'); mapping = Schema({'sha256': hashlib.sha256(data).hexdigest()}, data)
    result = assets.run_publisher_reader(tmp_path/'context', tmp_path/'reader', tmp_path, [], 'owned-format',
        schema_cache=tmp_path/'cache', table_schema=mapping, capture_schema_usage=capture)
    if capture:
        assert result['complete'] and len(requests[0]['schema_usage_nonce']) == 32
        assert requests[0]['capture_schema_usage'] is True
    else:
        assert result is None and 'capture_schema_usage' not in requests[0]
        assert not (tmp_path/'schema-usage.json').exists()


@pytest.mark.parametrize('bad', [None, 'nonce', 'hash', 'incomplete', 'count', 'case', 'path', 'size', 'budget'])
def test_registry_inventory_is_complete_unique_and_bound_to_this_source_invocation(tmp_path, monkeypatch, bad):
    from backend import nte_publisher_stream
    class Broker:
        descriptors, failures = [], []
        def __init__(self, _): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
    monkeypatch.setattr(nte_publisher_stream, 'Broker', Broker)
    def invocation(_context, _exe, _destination, mode):
        assert mode == 'publisher-dialogue-inventory'
        return ['owned'], None, tmp_path
    monkeypatch.setattr(assets, '_reader_invocation', invocation)
    registry = b'owned original registry bytes'
    def run(_command, **kwargs):
        request = json.loads(kwargs['input'])
        assert request['dialogue_registry_sha256'] == hashlib.sha256(registry).hexdigest()
        assert (tmp_path/'dialogue-registry.bin').read_bytes() == registry
        result = dict(schema='nte-original-dialogue-inventory-v1', complete=True,
            registry_sha256=request['dialogue_registry_sha256'], nonce=request['inventory_nonce'],
            package_count=1, packages={'HT/Content/Owned.uasset': 80})
        if bad == 'nonce': result['nonce'] = '0'*32
        elif bad == 'hash': result['registry_sha256'] = '0'*64
        elif bad == 'incomplete': result['complete'] = False
        elif bad == 'count': result['package_count'] = 2
        elif bad == 'case':
            result.update(package_count=2, packages={'HT/Content/Owned.uasset': 80, 'HT/Content/owned.uasset': 80})
        elif bad == 'path': result['packages'] = {'HT/Content/../Other.uasset': 80}
        elif bad == 'size': result['packages'] = {'HT/Content/Owned.uasset': True}
        elif bad == 'budget':
            result['packages'] = {f'HT/Content/Owned{i}.uasset': 4*1024**2 for i in range(33)}
            result['package_count'] = 33
        (tmp_path/'dialogue-inventory.json').write_text(json.dumps(result))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(assets.subprocess, 'run', run)
    if bad:
        with pytest.raises(PreparationFailure):
            assets.read_dialogue_inventory(tmp_path/'context', tmp_path/'reader', tmp_path, [], 'owned', registry)
    else:
        assert assets.read_dialogue_inventory(tmp_path/'context', tmp_path/'reader', tmp_path, [], 'owned', registry) == {
            'HT/Content/Owned.uasset': 80}


def test_actual_compiled_comparer_and_supplier_parse_warning_contract(tmp_path):
    sdk = assets.dotnet_sdk()
    if sdk is None:
        pytest.skip('The owned managed fixture requires the .NET 10 SDK')
    root = Path(__file__).resolve().parents[2]
    project = ElementTree.Element('Project', Sdk='Microsoft.NET.Sdk')
    properties = ElementTree.SubElement(project, 'PropertyGroup')
    for key, value in {'OutputType':'Exe', 'TargetFramework':'net10.0', 'AssemblyName':'Serilog',
                       'StartupObject':'UsageFixture', 'ImplicitUsings':'enable', 'Nullable':'enable',
                       'EnableDefaultCompileItems':'false'}.items():
        ElementTree.SubElement(properties, key).text = value
    includes = ElementTree.SubElement(project, 'ItemGroup')
    for path in [root/'scripts/game-readers/NteReader.cs', root/'backend/tests/fixtures/NteSchemaUsage.cs']:
        ElementTree.SubElement(includes, 'Compile', Include=str(path))
    path = tmp_path/'Owned.csproj'
    ElementTree.ElementTree(project).write(path, encoding='utf-8', xml_declaration=True)
    output = tmp_path/'out'
    result = subprocess.run([str(sdk), 'build', str(path), '--nologo', '-v', 'quiet', '-o', str(output)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    probe = subprocess.run([str(sdk), str(output/'Serilog.dll'), str(tmp_path/'cases')], capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert all(json.loads(probe.stdout).values())
