from pathlib import Path
import struct

from flatbuffers import flexbuffers
import pytest

from backend import hoyo_publisher_voice as voice, zzz_assets
from backend import zzz_publisher_cinematics as cinema
from backend.hoyo_dialogue import voice_namespace
from backend.nte_assets import wwise_hash
from backend.tests.test_zzz_cinematics import cinematic_package


def registry(event='Play_vo_Synthetic_01'):
    return cinema.audio_registry(flexbuffers.Dumps({'eventReferenceBanks': [wwise_hash(event), 77, 88, 0],
                                                  'futureUnrelatedField': ['synthetic']}))


def link(event='Play_vo_Synthetic_01', **changes):
    return {'text_id': 'SyntheticCaption', 'source': '', 'cinematic_event': event,
            'audio_scope': 'context', 'voice_status': 'unavailable', **changes}


class OriginalPackage:
    def __init__(self, data):
        self.data, self.size, self.reads = data, len(data), []

    def read(self, _directory, start, size):
        assert 0 <= start <= self.size - size
        self.reads.append((start, size))
        return self.data[start:start + size]


def package(tmp_path, locale='en', *, dynamic=False, multi=False, suffix=b'A', stream_type=0, memory_size=None):
    path = tmp_path / ('synthetic-' + locale + suffix.hex() + '.pck')
    old = cinematic_package(path, voice_namespace('zzz', locale).lower(), dynamic=dynamic, multi=multi)
    payload = b'WAVE' + suffix + bytes(len(old) - 13)
    wem = b'RIFF' + struct.pack('<I', len(payload)) + payload
    assert len(wem) == len(old)
    raw = path.read_bytes()[:-len(old)] + wem
    token = struct.pack('<IIBII', 10, 262145, 1, 123, 200)
    assert raw.count(token) == 1
    raw = raw.replace(token, struct.pack('<IIBII', 10, 262145, stream_type, 123, len(wem) if memory_size is None else memory_size))
    return OriginalPackage(raw), wem


def stream_package(wem, locale='en'):
    language = (voice_namespace('zzz', locale).lower() + '\0').encode('utf-16-le')
    languages = struct.pack('<3I', 1, 12, 2) + language
    sizes = (len(languages), 4, 24, 4)
    header_size = 20 + sum(sizes)
    return OriginalPackage(b'AKPK' + struct.pack('<6I', header_size, 1, *sizes) + languages + bytes(4)
                           + struct.pack('<6I', 1, 123, 1, len(wem), header_size + 8, 2) + bytes(4) + wem)


def sources(monkeypatch, snapshots):
    cinema._tables.cache_clear()
    cinema._bank.cache_clear()
    monkeypatch.setattr(voice, '_files', lambda _directory, stamp, _locale, game: snapshots[stamp])


@pytest.mark.parametrize('locale', ['en', 'zh-Hans', 'ja', 'ko'])
def test_original_cinema_banks_supply_explicit_context_in_each_selected_publisher_dub(tmp_path, monkeypatch, locale):
    original, wem = package(tmp_path, locale)
    name = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/' + cinema.VOICE_FOLDERS[locale] + '/Patch.pck'
    sources(monkeypatch, {'snapshot': {name: original}})
    result = cinema.bindings(tmp_path, 'snapshot', locale, [link()], registry())
    audio = result['SyntheticCaption']
    assert audio['audio_scope'] == 'context' and audio['event_bank'] == 77 and audio['media_bank'] == 88
    assert audio['locale'] == locale and audio['source'] == ''
    # Preparation reads ownership metadata; embedded film media waits for extraction.
    _, media = cinema._bank(tmp_path / 'tools/sophon', 'snapshot', locale, name, 88)
    entry = next(iter(media.values()))
    assert all(start + size <= entry.offset or start >= entry.offset + entry.size
               for start, size in original.reads)
    # The normal original-voice dispatch also serves bank media without an installation.
    assert zzz_assets.extract_voice(None, audio, tmp_path / 'tools', None) == wem
    records = zzz_assets._dialogue_records({locale: {'SyntheticCaption': 'Synthetic caption'}}, locale, {locale},
        {'SyntheticCaption': {'cinematic'}}, {'SyntheticCaption': {'unavailable'}},
        {'SyntheticCaption': {'cutscene'}}, result)
    assert records[0]['voice_status'] == 'voiced' and records[0]['audio_scope'] == 'context'
    with pytest.raises(ValueError, match='locales'):
        cinema.extract({**audio, 'locale': 'ja' if locale != 'ja' else 'en'}, tmp_path / 'tools')


def test_actual_event_and_referenced_media_are_required_and_unanimous(tmp_path, monkeypatch):
    original, _ = package(tmp_path)
    name = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/En/Patch.pck'
    sources(monkeypatch, {'snapshot': {name: original}})
    for uses in ([link(), link('Play_vo_Other')], [link(), link(None)], [link(), link(source='Unrelated')]):
        assert cinema.bindings(tmp_path, 'snapshot', 'en', uses, registry()) == {}
    assert cinema.bindings(tmp_path, 'snapshot', 'en', [link()], {wwise_hash('Play_vo_Synthetic_01'): {77}}) == {}
    assert cinema.bindings(tmp_path, 'snapshot', 'en', [link('Play_vo_Other')], registry('Play_vo_Other')) == {}


@pytest.mark.parametrize('options', [{'dynamic': True}, {'multi': True}])
def test_dynamic_and_multi_action_hierarchies_cannot_be_promoted_to_a_film_recording(tmp_path, monkeypatch, options):
    original, _ = package(tmp_path, **options)
    name = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/En/Patch.pck'
    sources(monkeypatch, {'snapshot': {name: original}})
    assert cinema.bindings(tmp_path, 'snapshot', 'en', [link()], registry()) == {}


def test_persistent_sources_override_base_and_historical_contexts_keep_their_descriptor(tmp_path, monkeypatch):
    first, first_wem = package(tmp_path, suffix=b'A')
    second, second_wem = package(tmp_path, suffix=b'B')
    base = 'ZenlessZoneZero_Data/StreamingAssets/Audio/Windows/Full/En/SoundBank_En_0.pck'
    patch = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/En/Patch.pck'
    sources(monkeypatch, {'old': {base: first}, 'new': {base: first, patch: second}})
    old = cinema.bindings(tmp_path, 'old', 'en', [link()], registry())['SyntheticCaption']
    new = cinema.bindings(tmp_path, 'new', 'en', [link()], registry())['SyntheticCaption']
    assert old['package'] == base and new['package'] == patch
    assert cinema.extract(old, tmp_path / 'tools') == first_wem
    assert cinema.extract(new, tmp_path / 'tools') == second_wem
    assert cinema.extract(old, tmp_path / 'tools') == first_wem
    with pytest.raises(ValueError, match='recording'):
        cinema.extract({**new, 'event': 'Play_vo_Other'}, tmp_path / 'tools')


def test_conflicting_same_layer_packages_and_registry_groups_remain_unresolved(tmp_path, monkeypatch):
    first, _ = package(tmp_path, suffix=b'A')
    second, _ = package(tmp_path, suffix=b'B')
    prefix = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/En/'
    sources(monkeypatch, {'snapshot': {prefix + 'Patch.pck': first, prefix + 'Hotfix.pck': second}})
    assert cinema.bindings(tmp_path, 'snapshot', 'en', [link()], registry()) == {}
    with pytest.raises(ValueError, match='Ambiguous'):
        cinema.audio_registry(flexbuffers.Dumps({'eventReferenceBanks': [1, 77, 0, 1, 88, 0]}))


@pytest.mark.parametrize('stream_type,memory_size', [(1, 32), (2, 0)])
def test_streamed_sources_use_the_complete_media_instead_of_the_embedded_prefix(tmp_path, monkeypatch, stream_type, memory_size):
    original, wem = package(tmp_path, stream_type=stream_type, memory_size=memory_size)
    prefix = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/En/'
    sources(monkeypatch, {'snapshot': {prefix + 'Patch.pck': original, prefix + 'Streamed_En_0.pck': stream_package(wem)}})
    audio = cinema.bindings(tmp_path, 'snapshot', 'en', [link()], registry())['SyntheticCaption']
    assert audio['media_bank'] is None and audio['package'].endswith('/Streamed_En_0.pck')
    assert cinema.extract(audio, tmp_path / 'tools') == wem
    with pytest.raises(ValueError, match='prefix'):
        cinema.extract({**audio, 'media_bank': 88, 'package': prefix + 'Patch.pck'}, tmp_path / 'tools')
    sources(monkeypatch, {'snapshot': {prefix + 'Patch.pck': original}})
    assert cinema.bindings(tmp_path, 'snapshot', 'en', [link()], registry()) == {}


def test_data_source_ignores_unrelated_stream_copy_and_unknown_source_kinds(tmp_path, monkeypatch):
    original, wem = package(tmp_path)
    prefix = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/En/'
    sources(monkeypatch, {'snapshot': {prefix + 'Patch.pck': original, prefix + 'Streamed_En_0.pck': stream_package(wem)}})
    assert cinema.bindings(tmp_path, 'snapshot', 'en', [link()], registry())['SyntheticCaption']['media_bank'] == 88
    unknown, _ = package(tmp_path, stream_type=3)
    sources(monkeypatch, {'snapshot': {prefix + 'Patch.pck': unknown}})
    assert cinema.bindings(tmp_path, 'snapshot', 'en', [link()], registry()) == {}


@pytest.mark.parametrize('value', [[], {'eventReferenceBanks': True}, {'eventReferenceBanks': [True]},
    {'eventReferenceBanks': [1, -1, 0]}, {'eventReferenceBanks': [1, 2**32, 0]},
    {'eventReferenceBanks': [1, 77]}, {'eventReferenceBanks': [1, 77.5, 0]}, {'other': []}])
def test_changed_registry_shapes_do_not_supply_silence_or_guessed_bindings(value):
    with pytest.raises(ValueError):
        cinema.audio_registry(flexbuffers.Dumps(value))
