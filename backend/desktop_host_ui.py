"""Native tray and visible log window; all Qt operations stay on the main thread."""
from __future__ import annotations

import sys
import threading


def ensure_console():
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetConsoleWindow.argtypes, kernel.GetConsoleWindow.restype = [], wintypes.HWND
    kernel.AllocConsole.argtypes, kernel.AllocConsole.restype = [], wintypes.BOOL
    kernel.SetConsoleTitleW.argtypes, kernel.SetConsoleTitleW.restype = [wintypes.LPCWSTR], wintypes.BOOL
    if not kernel.GetConsoleWindow():
        if not kernel.AllocConsole():
            return
        sys.stdout = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
        sys.stderr = open('CONOUT$', 'w', encoding='utf-8', buffering=1)
    kernel.SetConsoleTitleW('Game immersion toolkit · Status and logs')


def show_startup_error(message):
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        application = QApplication.instance() or QApplication(sys.argv[:1])
        QMessageBox.critical(None, 'Game immersion toolkit could not start', message)
    except ImportError:
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'Game immersion toolkit could not start', 0x10)


def run_ui(host):
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import (QApplication, QLabel, QMenu, QPlainTextEdit,
                                  QPushButton, QHBoxLayout, QVBoxLayout, QWidget, QSystemTrayIcon)
    ensure_console()
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName('Game immersion toolkit')
    application.setQuitOnLastWindowClosed(False)
    icon_pixels = QPixmap(64, 64)
    icon_pixels.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon_pixels)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor('#ccff36'))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 15, 15)
    painter.setPen(QColor('#172000'))
    font = painter.font()
    font.setPixelSize(39)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(icon_pixels.rect(), Qt.AlignmentFlag.AlignCenter, 'G')
    painter.end()
    icon = QIcon(icon_pixels)
    application.setWindowIcon(icon)
    tray = QSystemTrayIcon(icon)
    tray.setToolTip('Game immersion toolkit · Starting')
    quit_pending = False

    class LogWindow(QWidget):
        def closeEvent(self, event):
            if tray.isVisible() and not host.finished.is_set():
                self.hide()
                event.ignore()
            else:
                request_quit()
                event.ignore()

    window = LogWindow()
    window.setWindowTitle('Game immersion toolkit · Status and logs')
    window.resize(860, 540)
    layout = QVBoxLayout(window)
    status = QLabel('Starting…')
    status.setStyleSheet('font-size: 20px; font-weight: 600; padding: 4px 0;')
    layout.addWidget(status)
    logs = QPlainTextEdit()
    logs.setReadOnly(True)
    logs.setMaximumBlockCount(2000)
    logs.setStyleSheet('font-family: monospace; font-size: 12px;')
    layout.addWidget(logs)
    buttons = QHBoxLayout()
    open_button = QPushButton('Open transcript')
    open_button.clicked.connect(lambda: host.open_requested.set())
    buttons.addWidget(open_button)
    buttons.addStretch()
    quit_button = QPushButton('Quit')
    buttons.addWidget(quit_button)
    layout.addLayout(buttons)
    window.setStyleSheet('QWidget {background: #11161c; color: #eef2f6;} '
        'QPlainTextEdit {border: 1px solid #34404c; background: #0c1015;} '
        'QPushButton {border: 1px solid #52606d; border-radius: 5px; padding: 8px 16px;}'
        'QPushButton:hover {background: #273240;}')

    def show_logs():
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def request_quit():
        nonlocal quit_pending
        quit_pending = True
        host.stop_requested.set()
        quit_button.setEnabled(False)
        status.setText('Stopping and saving…')
        show_logs()
        if host.finished.is_set():
            application.quit()

    quit_button.clicked.connect(request_quit)
    menu = QMenu()
    open_action = QAction('Open transcript', menu)
    open_action.triggered.connect(lambda: host.open_requested.set())
    menu.addAction(open_action)
    logs_action = QAction('Show logs', menu)
    logs_action.triggered.connect(show_logs)
    menu.addAction(logs_action)
    menu.addSeparator()
    quit_action = QAction('Quit', menu)
    quit_action.triggered.connect(request_quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: show_logs() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
    else:
        host.log.write('This desktop has no tray service. Keep this status window open to manage the toolkit.')
    window.show()
    worker = threading.Thread(target=host.run, name='desktop-supervisor', daemon=False)
    worker.start()
    timer = QTimer()

    def refresh():
        if host.show_logs_requested.is_set():
            host.show_logs_requested.clear()
            show_logs()
        while not host.log.events.empty():
            logs.appendPlainText(host.log.events.get_nowait())
        status.setText(host.status)
        tray.setToolTip('Game immersion toolkit · ' + host.status[:90])
        open_button.setEnabled(host.ready.is_set() and not host.finished.is_set())
        open_action.setEnabled(open_button.isEnabled())
        if host.finished.is_set():
            tray.hide()
            if quit_pending or (host.stop_requested.is_set() and host.exit_code == 0):
                application.quit()
            elif host.exit_code:
                show_logs()
                quit_button.setText('Close')
        elif host.stop_requested.is_set():
            status.setText('Stopping and saving…')

    timer.timeout.connect(refresh)
    timer.start(200)
    result = application.exec()
    host.stop_requested.set()
    worker.join(timeout=45)
    if worker.is_alive():
        host.log.write('Shutdown is still waiting for owned processes; the application will remain open.')
        worker.join()
    tray.hide()
    host.log.close()
    return host.exit_code or result
