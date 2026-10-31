"""Opt-in observations of the real desktop UI, never offscreen acceptance.

The native runner binds this small, path-free result to the closed artifact.
Browser-handler success is explicitly a request acknowledgement, not proof that
the user's browser navigated, rendered or retained its ordinary profile.
"""
from __future__ import annotations

import time

from .bundle_host import _atomic_json


class DesktopUiProbe:
    def __init__(self, host, application, window, status, logs, tray, actions, *, tray_available):
        self.host, self.application, self.window = host, application, window
        self.status, self.logs, self.tray = status, logs, tray
        self.actions = actions
        self.tray_available = tray_available
        self.started = time.monotonic()
        self.phase = 'startup'
        self.requests = []
        self.error = None
        self.checks = {}
        self.platform = str(application.platformName()).casefold()
        self.non_native = self.platform in {'offscreen', 'minimal', 'minimalegl', 'vnc'}
        if self.non_native:
            host.browser = False
        original_open = host.open_browser

        def observe_open(url):
            try:
                accepted = bool(original_open(url))
            except Exception:
                self.requests.append(False)
                raise
            self.requests.append(accepted)
            return accepted
        host.open_browser = observe_open

    def visible(self):
        handle = self.window.windowHandle()
        return bool(self.window.isVisible() and handle is not None and handle.isExposed())

    def stop(self, error=None):
        self.error = error
        self.phase = 'stopping'
        self.actions['quit'].trigger()
        self.checks['quit_action'] = self.host.stop_requested.is_set()

    def tick(self):
        if self.phase == 'stopping':
            return
        if self.host.finished.is_set() or self.host.exit_code:
            self.stop('host-startup-failed')
            return
        if time.monotonic() - self.started > 120:
            self.stop('native-ui-timeout')
            return
        if not self.host.ready.is_set():
            return
        if self.non_native:
            self.stop('native-display-unavailable')
            return
        if not self.requests:
            return
        if self.phase == 'startup':
            if not self.visible() or self.logs.document().blockCount() < 2:
                return
            self.checks.update(status_window=bool(self.status.text()), log_window=True,
                tray_icon=bool(self.tray_available and self.tray.isVisible() and not self.tray.icon().isNull()),
                default_browser_request=self.requests[0],
                tray_unavailable_window_fallback=not self.tray_available and self.visible())
            self.window.hide()
            self.actions['logs'].trigger()
            self.phase = 'logs'
        elif self.phase == 'logs':
            if not self.visible():
                return
            self.checks['show_logs_action'] = True
            if not self.actions['open'].isEnabled():
                return
            self.actions['open'].trigger()
            self.phase = 'browser'
        elif self.phase == 'browser' and len(self.requests) >= 2:
            self.checks['open_transcript_action'] = self.requests[-1]
            self.stop(None if all(self.requests) else 'default-browser-handler-unavailable')

    def finish(self):
        self.checks['owned_shutdown'] = self.host.finished.is_set() and not self.host.lease.held
        unavailable = self.error in {'native-display-unavailable', 'default-browser-handler-unavailable'}
        required = ('status_window', 'log_window', 'show_logs_action', 'default_browser_request',
                    'open_transcript_action', 'quit_action', 'owned_shutdown')
        passed = self.error is None and all(self.checks.get(key) is True for key in required)
        if self.tray_available and not self.checks.get('tray_icon'):
            passed = False
        value = {'schema': 'toolkit-desktop-ui-observation-v1', 'mode': self.host.layout.mode,
            'passed': passed, 'status': 'passed' if passed else 'unavailable' if unavailable else 'failed',
            'checks': self.checks, 'native_tray': 'available' if self.tray_available else 'unavailable',
            'native_display': 'observed' if self.checks.get('status_window') else 'unavailable' if self.non_native else 'unverified',
            'browser_navigation': 'not-run', 'ordinary_browser_profile': 'not-run',
            'native_game_capture': 'not-run', 'r19_complete': False}
        if self.error:
            value['error'] = self.error
        _atomic_json(self.host.layout.state_root / 'native-ui-probe.json', value)
        return 0 if passed else 2 if unavailable else 1
