"""Retain supplier notice bytes and bind deferred Qt grants to exact sources."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('notice_review', Path(__file__).resolve().parents[2] / 'scripts/review-desktop-inputs.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.mark.parametrize('delivered', ['Copyright\r\nPermission\r\nWarranty\r\n', 'Copyright\r\nPermission\r\n'])
def test_actual_frontend_notice_preserves_crlf_without_accepting_truncation(tmp_path, monkeypatch, delivered):
    frontend = tmp_path / 'frontend'
    (frontend / 'notices').mkdir(parents=True)
    (tmp_path / 'styles').mkdir()
    (tmp_path / 'styles/GEIST-OFL.txt').write_bytes(b'Authored font terms')
    (frontend / 'notices/GEIST-OFL.txt').write_bytes(b'Authored font terms')
    (frontend / 'notices/THIRD_PARTY_LICENSES.txt').write_bytes(('supplier @ 1.0\n' + delivered).encode())
    monkeypatch.setattr(review, 'FrontendBuild', lambda _: SimpleNamespace(root=frontend, value={'lock_sha256': 'lock'}))
    audit = dict(lock_sha256='lock', records=[dict(package='supplier', version='1.0', file='LICENSE',
        text='Copyright\r\nPermission\r\nWarranty\r\n')], omissions=[], excluded=[])
    monkeypatch.setattr(review.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=json.dumps(audit).encode()))
    value = review.Review(tmp_path, {'files': []}, 'windows-x64')
    value.frontend(tmp_path, 'node')
    assert bool(value.checks['frontend_licenses']['blockers']) == ('Warranty' not in delivered)


@pytest.mark.parametrize('version', ['6.12.0', '6.11.0'])
def test_qt_source_only_primary_grant_requires_matching_source_and_notices(tmp_path, version):
    policy = tmp_path / 'packaging/desktop'
    policy.mkdir(parents=True)
    (policy / 'native-notices.json').write_text(json.dumps({'distributions': {}, 'components': []}))
    (policy / 'qt-sources.json').write_text(json.dumps({'version': '6.12.0', 'components': [dict(
        name='pyside-setup', archive='pyside-setup-everywhere-src-6.12.0.tar.xz', sha256='a'*64)]}))
    value = review.Review(tmp_path, {'files': []}, 'windows-x64')
    value.wheels = {'pyside6-essentials': {'version': version}, 'shiboken6': {'version': version}}
    if version != '6.12.0':
        with pytest.raises(ValueError, match='version'):
            value.sources(tmp_path)
        assert value.checks['complete_notices']['blockers'][0]['code'] == 'qt-source-version'
    else:
        value.sources(tmp_path)
        assert value.checks['corresponding_sources']['blockers'][0]['code'] == 'source-archive-missing'
        assert value.checks['complete_notices']['blockers'][0]['code'] == 'source-notices-missing'
