"""Desktop export of the complete contract consumed by the native shared core."""
from contextlib import contextmanager
from pathlib import Path

from .mobile_export_layout import file_title
from .prepared_library import write_prepared_library


def export_library(snapshot, output, *, voice, check, include_audio=True, progress=lambda _: None):
    output = Path(output)
    destination = output / (file_title(snapshot['game']) + ' - Android Library.zip')
    rows = snapshot['records']
    total = sum(bool(row.get('audio')) for row in rows)
    done = voiced = 0

    def clip(row):
        nonlocal done, voiced
        check()
        done += 1
        result = voice(row, done) if include_audio else None
        voiced += result is not None
        progress({'state': 'exporting', 'progress': int(90 * done / max(1, total)),
                  'done': done, 'total': total, 'message': 'Preparing the Android library'})
        return result

    @contextmanager
    def publication():
        # Source/account checks are repeated immediately before the shared
        # writer atomically replaces the previous completed library.
        getattr(check, 'force', check)()
        yield

    write_prepared_library(snapshot, destination, clip, publish_guard=publication)
    result = {'state': 'complete', 'progress': 100, 'game': snapshot['game'],
              'folder': str(output), 'bundle': str(destination), 'bytes': destination.stat().st_size,
              'coverage': {'dialogue': len(rows), 'exportedVoices': voiced},
              'message': 'Android library ready. Import this ZIP in the app.'}
    progress(result)
    return result
