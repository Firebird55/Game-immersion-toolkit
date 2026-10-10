from backend.config import SettingsStore
from backend.models import AppSettings, CaptureRegion


def test_pc_settings_migrate_once_then_remain_independent(tmp_path):
    shared = tmp_path / 'shared' / 'settings.json'
    SettingsStore(shared).save(AppSettings(hito_region=CaptureRegion(top=.72, height=.2)))
    first = SettingsStore(tmp_path / 'pc-a' / 'settings.json', legacy_path=shared)
    second = SettingsStore(tmp_path / 'pc-b' / 'settings.json', legacy_path=shared)
    adjusted = first.get().model_copy(update={'hito_auto_regions': False,
                                             'hito_region': CaptureRegion(top=.6, height=.3)})
    first.save(adjusted)
    assert second.get().hito_region.top == .72
    assert SettingsStore(shared).get().hito_region.top == .72
    restarted = SettingsStore(first.path, legacy_path=shared).get()
    assert restarted.hito_region.top == .6
    assert restarted.hito_auto_regions is False


def test_picture_area_and_new_defaults_never_overwrite_saved_calibration(tmp_path):
    old = CaptureRegion(left=.08, top=.68, width=.84, height=.30)
    store = SettingsStore(tmp_path / 'settings.json')
    store.save(AppSettings(honkai3_region=old, nte_picture_area='16:9'))
    loaded = SettingsStore(store.path).get()
    assert loaded.honkai3_region == old
    assert loaded.nte_picture_area == '16:9'
    assert loaded.honkai3_picture_area == 'window'
    assert AppSettings().honkai3_region.width == .96
