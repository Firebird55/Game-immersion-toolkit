"""Hosted browser setup cannot substitute launch requests for mounted evidence."""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


spec = spec_from_file_location('linux_desktop_ui', Path(__file__).resolve().parents[2] / 'scripts/probe-linux-desktop-ui.py')
linux = module_from_spec(spec)
spec.loader.exec_module(linux)


def environment(base):
    result = {'PATH': os.environ.get('PATH', ''), 'HOME': str(base / 'home'),
        'XDG_CONFIG_HOME': str(base / 'config'), 'XDG_DATA_HOME': str(base / 'xdg-data')}
    for directory in ('home', 'config', 'xdg-data'):
        (base / directory).mkdir()
    return result


def browser(monkeypatch, base):
    executable = base / 'chrome with spaces'
    executable.write_text('authored executable fixture')
    executable.chmod(0o700)
    monkeypatch.setattr(linux.shutil, 'which', lambda *_a, **_k: str(executable))
    monkeypatch.setattr(linux.os, 'access', lambda *_a: True)
    return executable


def test_default_association_and_profile_are_owned_without_fabricating_navigation(monkeypatch, tmp_path):
    base = tmp_path.resolve()
    env = environment(base)
    before = dict(env)
    executable = browser(monkeypatch, base)
    calls = []
    def query(arguments, **options):
        calls.append((arguments, options))
        return SimpleNamespace(returncode=0, stdout='toolkit-native-browser.desktop\n')
    monkeypatch.setattr(linux.subprocess, 'run', query)
    result = linux.prepare_browser(base, env)
    entry = (base / 'xdg-data/applications/toolkit-native-browser.desktop').read_text()
    assert linux.desktop_argument(str(executable)) in entry and '--no-first-run' in entry
    assert '--no-default-browser-check' in entry and linux.desktop_argument('--user-data-dir=' + str(base / 'native-browser-profile')) in entry
    assert entry.endswith(' %u\n') and 'Terminal=false' in entry
    assert '--no-sandbox' not in entry and '--headless' not in entry
    assert '--disable-web-security' not in entry and 'native-browser-probe' not in entry
    assert env == before
    assert calls[0][0] == ['xdg-mime', 'query', 'default', 'x-scheme-handler/http']
    assert calls[0][1]['env'] == env and calls[0][1]['timeout'] == 15
    assert result == {'browser_launch_context': 'isolated-xdg-default', 'browser_family': 'chromium'}
    assert not list(base.rglob('native-browser-probe.json'))
    assert (base / 'config/mimeapps.list').read_text().count('x-scheme-handler/http=toolkit-native-browser.desktop;') == 2


@pytest.mark.parametrize('selected,returncode', [('other-browser.desktop\n', 0), ('toolkit-native-browser.desktop\n', 1)])
def test_desktop_selection_failure_is_not_browser_acceptance(monkeypatch, tmp_path, selected, returncode):
    base = tmp_path.resolve()
    env = environment(base)
    browser(monkeypatch, base)
    monkeypatch.setattr(linux.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(returncode=returncode, stdout=selected))
    with pytest.raises(linux.LinuxBrowserUnavailable, match='did not select'):
        linux.prepare_browser(base, env)


def test_config_cannot_change_an_existing_users_desktop(monkeypatch, tmp_path):
    base = tmp_path.resolve()
    env = environment(base)
    browser(monkeypatch, base)
    outside = base / 'unrelated-config'
    outside.mkdir()
    env['XDG_CONFIG_HOME'] = str(outside)
    with pytest.raises(ValueError, match='stay inside'):
        linux.prepare_browser(base, env)
    assert not list(outside.iterdir())


def test_missing_installed_browser_fails_without_a_request_fallback(monkeypatch, tmp_path):
    env = environment(tmp_path)
    monkeypatch.setattr(linux.shutil, 'which', lambda *_a, **_k: None)
    with pytest.raises(linux.LinuxBrowserUnavailable, match='Installed Chrome'):
        linux.prepare_browser(tmp_path, env)


def test_desktop_exec_escapes_field_codes_and_string_reserved_characters():
    assert linux.desktop_argument('/opt/google/chrome/google-chrome') == '/opt/google/chrome/google-chrome'
    assert linux.desktop_argument('--user-data-dir=/tmp/authored-profile') == '--user-data-dir=/tmp/authored-profile'
    assert linux.desktop_argument('/path with spaces/chrome') == '"/path with spaces/chrome"'
    assert linux.desktop_argument('a%u') == '"a%%u"'
    assert linux.desktop_argument('a"$`\\b') == '"a\\\\"\\\\$\\\\`\\\\\\\\b"'
    for value in ('line\nbreak', 'line\rbreak', 'nul\0byte'):
        with pytest.raises(ValueError, match='control character'):
            linux.desktop_argument(value)


@pytest.mark.skipif(os.name == 'nt' or not __import__('sys').platform.startswith('linux'), reason='Actual Linux desktop lookup')
def test_actual_xdg_mime_selects_only_the_private_default(monkeypatch, tmp_path):
    # No browser is launched here; the native hosted probe supplies that evidence.
    base = tmp_path.resolve()
    env = environment(base)
    browser(monkeypatch, base)
    assert linux.prepare_browser(base, env)['browser_launch_context'] == 'isolated-xdg-default'


@pytest.mark.skipif(not __import__('sys').platform.startswith('linux'), reason='Actual Linux desktop opener')
def test_actual_xdg_open_routes_exact_url_and_profile_through_private_default(monkeypatch, tmp_path):
    # This authored executable proves desktop routing only. The separate frozen
    # native probe still requires the real browser to mount the transcript.
    import json
    import subprocess
    import sys
    base = tmp_path.resolve()
    env = environment(base)
    env['DISPLAY'] = ':authored-routing-fixture'
    env['XDG_CURRENT_DESKTOP'] = 'X-Generic'
    executable = base / 'authored-browser'
    output = base / 'observed-arguments.json'
    executable.write_text('#!' + sys.executable + '\nimport json,sys\n'
        + 'open(' + repr(str(output)) + ', "w").write(json.dumps(sys.argv[1:]))\n')
    executable.chmod(0o700)
    monkeypatch.setattr(linux.shutil, 'which', lambda *_a, **_k: str(executable))
    linux.prepare_browser(base, env)
    url = 'http://127.0.0.1:17866/transcript?authored=1#fragment'
    result = subprocess.run(['/usr/bin/xdg-open', url], env=env,
        stdin=subprocess.DEVNULL, capture_output=True, timeout=15, check=False)
    assert result.returncode == 0
    assert json.loads(output.read_text()) == ['--no-first-run', '--no-default-browser-check',
        '--user-data-dir=' + str(base / 'native-browser-profile'), url]
