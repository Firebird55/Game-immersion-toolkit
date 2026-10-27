"""Synthetic Heavy Rain presentation and update safeguards; no game resources."""
import pytest

from backend import heavy_rain_assets as assets, quantic_legacy as legacy
from backend.preparation_errors import PreparationFailure
from backend.tests.test_heavy_rain_assets import compact_localization, installation, ints, string


def test_explicit_prompt_null_is_distinct_from_unresolved_or_generic_null():
    prompt = legacy.localization(compact_localization(source_voice=0, flags=2))['HOL']
    unresolved = legacy.localization(compact_localization(declared=False))['HOL']
    generic = legacy.localization(compact_localization(source_voice=0))['HOL']
    assert prompt['text_flags'][101] == 2 and prompt['binding_states'][101] == 'none'
    assert unresolved['binding_states'][101] == 'unresolved'
    assert generic['text_flags'][101] == 1 and generic['binding_states'][101] == 'none'


def test_verified_prompt_is_unvoiced_but_missing_binding_never_is(tmp_path, monkeypatch):
    installation(tmp_path)
    original = legacy.localization
    def localized(body, locales=None):
        result = original(body, locales)
        source = result['HOL']
        for key, flag, state in [(102, 2, 'none'), (103, 1, 'none'), (104, 2, 'unresolved')]:
            source['texts'][key] = f'Synthetic entry number {key}.'
            source['bindings'][key] = None
            source['text_flags'][key] = flag
            source['binding_states'][key] = state
        return result
    monkeypatch.setattr(legacy, 'localization', localized)
    result = assets.index_language(tmp_path, tmp_path / 'cache', 'nl', ['zh-hans'])
    rows = {row['text_id'].split(':')[-1]: row for row in result['records']}
    assert rows['00000065']['voice_status'] == 'voiced'
    assert rows['00000066']['voice_status'] == 'unvoiced'
    assert rows['00000066']['dialogue_kind'] == 'choice' and rows['00000066']['audio'] is None
    assert rows['00000067']['voice_status'] == 'unknown'
    assert rows['00000068']['voice_status'] == 'unavailable'
    assert result['coverage_warnings']


def names_file(tmp_path, *, version=13, trailing=b''):
    path = (tmp_path / assets.SCENE_INDEXES[0]).with_suffix('.pdbg')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'QUANTICDREAMTABINDEX' + ints(version, 1, 1016, 1, 17)
                     + string('HR_0000_THOUGHTS_SYNTHETIC') + bytes(24) + trailing)
    return path


def test_optional_presentation_names_only_classify_and_change_fingerprint(tmp_path):
    installation(tmp_path)
    initial = assets.fingerprint(tmp_path)
    names_file(tmp_path)
    assert assets.fingerprint(tmp_path) != initial
    result = assets.index_language(tmp_path, tmp_path / 'cache', 'nl', ['zh-hans'])
    assert result['records'][0]['dialogue_kind'] == 'thought'
    assert result['records'][0]['audio']['identity'] == 42
    names_file(tmp_path, trailing=b'extra')
    fallback = assets.index_language(tmp_path, tmp_path / 'cache', 'nl', [])
    assert fallback['records'][0]['audio']['identity'] == 42
    assert fallback['records'][0]['dialogue_kind'] == 'conversation'
    assert any('presentation-name table has an unsupported format' in warning for warning in fallback['coverage_warnings'])


def test_unknown_required_archive_reports_an_update_error(tmp_path):
    installation(tmp_path)
    (tmp_path / 'Resources' / 'NewPatch.idx').write_bytes(b'unknown format')
    with pytest.raises(PreparationFailure) as error:
        assets.index_language(tmp_path, tmp_path / 'cache', 'nl', [])
    assert error.value.code == 'unsupported_game_format'
    assert 'Update the toolkit' in str(error.value)


def test_missing_voice_banks_retain_authored_text_with_actionable_warning(tmp_path):
    installation(tmp_path)
    (tmp_path / assets.VOICE_INDEXES[0]).unlink()
    result = assets.index_language(tmp_path, tmp_path / 'cache', 'nl', [])
    assert result['records'][0]['voice_status'] == 'unavailable'
    assert any('not treated as silent' in warning for warning in result['coverage_warnings'])
