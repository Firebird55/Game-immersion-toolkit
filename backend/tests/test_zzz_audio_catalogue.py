"""The context-bound catalogue preserves original dub/event/media semantics."""
from pathlib import Path

import pytest

from backend import hoyo_publisher_voice, zzz_publisher_cinematics as cinema
from backend.zzz_audio_catalogue import Catalogue
from backend.tests.test_zzz_publisher_cinematics import package, stream_package, link, registry


@pytest.mark.parametrize('locale', ['en', 'zh-Hans', 'ja', 'ko'])
@pytest.mark.parametrize('stream', [False, True])
def test_bound_original_banks_and_complete_streams_require_no_global_voice_lookup(tmp_path, monkeypatch, locale, stream):
    source, wem = package(tmp_path, locale, stream_type=1 if stream else 0, memory_size=16 if stream else None)
    root = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/' + cinema.VOICE_FOLDERS[locale] + '/'
    files = {root + 'Bank.pck': source}
    if stream:files[root + 'Stream.pck'] = stream_package(wem, locale)
    def forbidden(*args, **kwargs):raise AssertionError('Bound catalogue entered legacy source discovery')
    monkeypatch.setattr(hoyo_publisher_voice, '_files', forbidden)
    monkeypatch.setattr(hoyo_publisher_voice, '_archive', forbidden)
    catalogue = Catalogue(files, locale, 'source-generation', lambda asset, start, size: asset.read(None, start, size))
    bound = catalogue.bindings([link()], registry())['SyntheticCaption']
    name, entry = catalogue.recording(bound)
    assert bound['publisher'] == 'source-generation' and bound['locale'] == locale
    assert bound['audio_scope'] == 'context' and entry.size == len(wem)
    # Ownership is metadata-only: the complete media is read only explicitly.
    assert all(start + size <= entry.offset or start >= entry.offset + entry.size for start, size in files[name].reads)
    assert catalogue.extract(bound) == wem
    with pytest.raises(ValueError):catalogue.recording({**bound, 'publisher': 'other-generation'})


def test_equal_priority_conflict_is_not_rescued_by_a_base_recording(tmp_path):
    first, _ = package(tmp_path, suffix=b'A')
    second, _ = package(tmp_path, suffix=b'B')
    root = 'ZenlessZoneZero_Data/Persistent/Audio/Windows/Full/En/'
    files = {root + 'One.pck': first, root + 'Two.pck': second,
             root.replace('/Persistent/', '/StreamingAssets/') + 'Base.pck': first}
    catalogue = Catalogue(files, 'en', 'generation', lambda asset, start, size: asset.read(None, start, size))
    assert catalogue.bindings([link()], registry()) == {}


def test_selected_dub_catalogue_rejects_foreign_package_before_any_read(tmp_path):
    source, _ = package(tmp_path, 'ja')
    def forbidden(*args):raise AssertionError('Foreign-dub source was read')
    with pytest.raises(ValueError):
        Catalogue({'ZenlessZoneZero_Data/StreamingAssets/Audio/Windows/Full/Jp/Bank.pck': source}, 'en', 'generation', forbidden)
