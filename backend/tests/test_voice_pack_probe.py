from backend.voice_pack_probe import _probe
from backend.tests.test_heavy_rain_assets import installation
from backend.tests.test_quantic_assets import write_archive


def test_pack_state_does_not_require_a_prepared_index(tmp_path):
    root=tmp_path/'Game'
    path=root/'archive/pc/content/lang_ja_voice.archive'
    path.parent.mkdir(parents=True)
    assert _probe('cyberpunk', root, 'ja') == 'missing'
    path.write_bytes(b'partial')
    assert _probe('cyberpunk', root, 'ja') == 'incomplete'
    path.write_bytes(bytes(128))
    assert _probe('cyberpunk', root, 'ja') == 'present'
    assert _probe('cyberpunk', root, 'en') == 'missing'
    assert _probe('nte', root, 'ja') == 'unknown'


def test_shared_bank_probe_uses_authored_locale_metadata(tmp_path):
    installation(tmp_path, locale='nl')
    assert _probe('heavyrain', tmp_path, 'nl') == 'present'
    assert _probe('heavyrain', tmp_path, 'ja') == 'unknown'
