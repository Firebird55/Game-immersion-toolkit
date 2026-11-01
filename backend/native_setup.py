"""Small local setup dialogs shared by all packaged desktop platforms."""
from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout)

from .accounts import AccountStore
from .game_paths import GAME_NAMES, GAMES, clear_install, load_paths, save_install
from .lexirise import LexiriseError
from .protected_storage import ProtectedStorageError


class Task(QThread):
    progress = Signal(str)
    completed = Signal(object, str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.completed.emit(self.operation(self.progress.emit), '')
        except (LexiriseError, ProtectedStorageError, ValueError) as error:
            self.completed.emit(None, str(error))
        except Exception:
            self.completed.emit(None, 'The local operation could not finish. Check the installation and try again.')
        finally:
            self.operation = None


class SetupDialog(QDialog):
    def __init__(self, title):
        super().__init__()
        self.setWindowTitle(title + ' — Game immersion toolkit')
        self.setMinimumWidth(460)
        self.layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.task = None
        self.success = False

    def run_task(self, operation, finished):
        self.task = Task(operation, self)
        self.task.progress.connect(self.status.setText)
        self.task.completed.connect(finished)
        self.task.start()

    def closeEvent(self, event):
        if self.task and self.task.isRunning():
            self.status.setText('Finishing the local operation. This window will be ready to close shortly.')
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        if not self.task or not self.task.isRunning():
            super().reject()


class FolderDialog(SetupDialog):
    def __init__(self):
        super().__init__('Game folders')
        self.game = QComboBox()
        for game in sorted(GAMES, key=lambda item: GAME_NAMES[item]):
            self.game.addItem(GAME_NAMES[game], game)
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        form = QFormLayout()
        form.addRow('Game', self.game)
        form.addRow('Installed folder', self.path)
        self.layout.addLayout(form)
        browse = QPushButton('Choose folder…')
        browse.clicked.connect(self.choose)
        automatic = QPushButton('Use automatic detection')
        automatic.clicked.connect(self.automatic)
        self.layout.addWidget(browse)
        self.layout.addWidget(automatic)
        self.layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)
        self.game.currentIndexChanged.connect(self.selected)
        self.selected()

    def selected(self):
        self.path.setText(load_paths().get(self.game.currentData(), ''))
        self.status.setText('Choose the installed game folder. Game files remain in place.')

    def choose(self):
        selected = QFileDialog.getExistingDirectory(self, 'Choose installed game folder', self.path.text())
        if not selected:
            return
        try:
            root = save_install(self.game.currentData(), Path(selected))
        except ValueError as error:
            self.status.setText(str(error))
        except OSError:
            self.status.setText('Cannot read or save this folder. Check access and try again.')
        else:
            self.path.setText(str(root))
            self.status.setText('Folder saved. The transcript will check its game files.')
            self.success = True

    def automatic(self):
        try:
            clear_install(self.game.currentData())
        except OSError:
            self.status.setText('Cannot save this setting. Check access and try again.')
        else:
            self.path.clear()
            self.status.setText('Automatic detection enabled for this game.')
            self.success = True


class AccountDialog(SetupDialog):
    def __init__(self, store=None):
        super().__init__('Add Lexirise account')
        self.store = store if store is not None else AccountStore()
        self.name = QLineEdit()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('lx_…')
        form = QFormLayout()
        form.addRow('Account label', self.name)
        form.addRow('API key', self.key)
        self.layout.addLayout(form)
        self.status.setText('Enter your key here on this computer. Verification reads your account identity; the key stays in protected local storage.')
        self.layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText('Verify and save')
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def save(self):
        key, name = self.key.text().strip(), self.name.text().strip()
        if not key.startswith('lx_') or not 20 <= len(key) <= 512:
            self.status.setText('Enter a valid Lexirise API key.')
            return
        self.key.clear()
        self.key.setEnabled(False)
        self.name.setEnabled(False)
        self.buttons.setEnabled(False)
        self.status.setText('Verifying account identity and saving to protected storage…')
        self.run_task(lambda _progress: self.store.add(key, name), self.saved)

    def saved(self, profile, error):
        self.key.setEnabled(True)
        self.name.setEnabled(True)
        self.buttons.setEnabled(True)
        if error:
            self.status.setText(error)
            return
        self.success = True
        self.status.setText('Account verified, saved and selected.')
        self.buttons.button(QDialogButtonBox.Cancel).setText('Close')


def check_components(progress):
    """Check actual bundled OCR and desktop access without reading accounts."""
    from .media_tools import ffmpeg_executable
    from .ocr_engine import OcrEngine
    from .windows import list_visible_windows
    import mss
    from PIL import Image, ImageDraw, ImageFont
    progress('Checking desktop access…')
    try:
        list_visible_windows()
        with mss.MSS() as capture:
            if not capture.monitors[1:]:
                raise ValueError('No desktop display is available. Open this check from your desktop session.')
    except OSError as error:
        if hasattr(error, 'code'):
            raise ValueError(str(error)) from None
        raise ValueError('Desktop capture is unavailable. Check display access and screen-recording permission.') from None
    progress('Loading offline subtitle OCR…')
    engine = OcrEngine()
    sample = Image.new('RGB', (1000, 160), '#111820')
    ImageDraw.Draw(sample).text((25, 40), 'Enemies incoming!', font=ImageFont.load_default(size=54), fill='white')
    lines = engine.recognize_pil(sample).get('lines', [])
    if not any('enemies incoming' in item.get('text', '').casefold() for item in lines):
        raise ValueError('Subtitle OCR could not read the test sentence. Repair the toolkit installation.')
    progress('Checking original-voice audio conversion…')
    if not ffmpeg_executable():
        raise ValueError('The audio converter is missing. Repair the toolkit installation.')
    return {'desktop': True, 'ocr': True, 'audio': True}


class CheckDialog(SetupDialog):
    def __init__(self):
        super().__init__('Capture check')
        self.layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)
        self.status.setText('Starting capture check…')
        self.run_task(check_components, self.checked)

    def checked(self, result, error):
        self.success = bool(result) and not error
        self.status.setText(error or 'Desktop access, subtitle OCR and audio conversion are ready. Start your game to verify its actual dialogue capture.')


def main(arguments=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=('folders', 'lexirise', 'checks'))
    args = parser.parse_args(arguments)
    app = QApplication.instance() or QApplication(['Game immersion toolkit setup'])
    dialog = {'folders': FolderDialog, 'lexirise': AccountDialog, 'checks': CheckDialog}[args.kind]()
    dialog.show()
    app.exec()
    return 0 if args.kind != 'checks' or dialog.success else 1


if __name__ == '__main__':
    raise SystemExit(main())
