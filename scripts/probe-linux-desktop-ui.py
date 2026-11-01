"""Use a real X11 tray and isolated desktop/browser configuration for native CI.

The application's unchanged xdg-open path must launch the installed browser;
only the mounted transcript can acknowledge the native challenge. No normal
profile, global default association or browser security setting is changed.
"""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


class LinuxBrowserUnavailable(RuntimeError):
    pass


def desktop_argument(value):
    """Quote an Exec argument per the Desktop Entry Specification, not a shell.

    https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html
    """
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError('Desktop argument contains a control character.')
    # xdg-open's generic fallback uses `read first rest`, not a Desktop Entry
    # quote parser. Unnecessary quotes become part of the command/arguments.
    # Spec-safe hosted paths and options therefore use their literal spelling.
    if value and re.fullmatch(r'[A-Za-z0-9_./:=+@-]+', value):
        return value
    quoted = ''.join('\\' + character if character in '\\"`$' else character for character in value)
    return '"' + quoted.replace('\\', '\\\\').replace('%', '%%') + '"'


def prepare_browser(base, environment):
    # child_environment intentionally does not inherit the runner's HOME/XDG
    # settings. Its empty profile therefore needs its own explicit association.
    # Chrome is supplied by the hosted image, not shipped with the application.
    browser = shutil.which('google-chrome', path=environment['PATH'])
    if not browser:
        raise LinuxBrowserUnavailable('Installed Chrome is required for this hosted UI probe.')
    browser = Path(browser).resolve(strict=True)
    if not browser.is_file() or not os.access(browser, os.X_OK):
        raise LinuxBrowserUnavailable('Installed Chrome is not executable.')
    base = base.resolve(strict=True)
    for key, directory in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'xdg-data')):
        if Path(environment[key]).resolve(strict=True) != base / directory:
            raise ValueError('Native browser configuration must stay inside the probe.')
    profile = base / 'native-browser-profile'
    profile.mkdir(mode=0o700)
    applications = base / 'xdg-data/applications'
    applications.mkdir(mode=0o700)
    application = 'toolkit-native-browser.desktop'
    arguments = [str(browser), '--no-first-run', '--no-default-browser-check',
        '--user-data-dir=' + str(profile)]
    entry = ('[Desktop Entry]\nType=Application\nName=Toolkit native probe browser\n'
        'Terminal=false\nMimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;\n'
        'Exec=' + ' '.join(desktop_argument(value) for value in arguments) + ' %u\n')
    with (applications / application).open('x', encoding='utf-8', newline='\n') as output:
        output.write(entry)
    associations = ''.join(kind + '=' + application + ';\n'
        for kind in ('text/html', 'x-scheme-handler/http', 'x-scheme-handler/https'))
    with (base / 'config/mimeapps.list').open('x', encoding='utf-8', newline='\n') as output:
        output.write('[Default Applications]\n' + associations + '\n[Added Associations]\n' + associations)
    # Validate the real desktop lookup before launching the frozen application.
    selected = subprocess.run(['xdg-mime', 'query', 'default', 'x-scheme-handler/http'],
        env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, check=False)
    if selected.returncode or selected.stdout.strip() != application:
        raise LinuxBrowserUnavailable('The isolated desktop did not select its browser.')
    return {'browser_launch_context': 'isolated-xdg-default', 'browser_family': 'chromium'}


def main():
    from Xlib.display import Display
    tray = subprocess.Popen(['trayer', '--edge', 'top', '--align', 'right',
        '--widthtype', 'request', '--height', '24'], stdin=subprocess.DEVNULL)
    try:
        display = Display()
        try:
            atom = display.intern_atom('_NET_SYSTEM_TRAY_S' + str(display.get_default_screen()))
            deadline = time.monotonic() + 10
            while not display.get_selection_owner(atom):
                if tray.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Hosted X11 system tray did not become available.')
                time.sleep(.1)
        finally:
            display.close()
        specification = spec_from_file_location('desktop_native_probe',
            Path(__file__).with_name('probe-desktop-host.py'))
        probe = module_from_spec(specification)
        specification.loader.exec_module(probe)
        sys.argv.insert(1, '--ui')
        return probe.main(prepare_ui_environment=prepare_browser)
    finally:
        if tray.poll() is None:
            tray.terminate()
        try:
            tray.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tray.kill()
            tray.wait(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
