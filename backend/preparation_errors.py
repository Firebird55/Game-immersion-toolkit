"""Actionable public preparation failures, separate from private tool diagnostics."""
import subprocess
from urllib.error import HTTPError, URLError


class PreparationFailure(ValueError):
    def __init__(self, code, message, *, game_files_changed=False, previous_snapshot_retained=False, retry_seconds=120):
        self.code = code
        self.game_files_changed = game_files_changed
        self.previous_snapshot_retained = previous_snapshot_retained
        self.retry_seconds = min(3600, max(120, retry_seconds))
        super().__init__(message)


def public_failure(error):
    if isinstance(error, PreparationFailure):
        return {'code': error.code, 'message': str(error), 'game_files_changed': error.game_files_changed,
                'previous_snapshot_retained': error.previous_snapshot_retained, 'retry_seconds': error.retry_seconds}
    if isinstance(error, HTTPError):
        if error.code == 429:
            try:
                delay = int(error.headers.get('Retry-After', '900'))
            except (ValueError, TypeError, AttributeError):
                delay = 900
            return {'code': 'metadata_rate_limited', 'retry_seconds': min(3600, max(120, delay)),
                    'message': 'The game-data download service is limiting requests. Preparation will retry after a cooldown; your installed game files do not need repairing for this error.'}
        return {'code': 'metadata_unavailable', 'retry_seconds': 300,
                'message': f'The game-data download service returned HTTP {error.code}. Preparation will retry; update the toolkit if this continues.'}
    if isinstance(error, URLError):
        return {'code': 'metadata_network', 'retry_seconds': 300,
                'message': 'The game-data download service could not be reached. Check the connection; preparation will retry automatically.'}
    if isinstance(error, subprocess.TimeoutExpired):
        return {'code': 'reader_timeout', 'message': 'The game reader exceeded its time limit. Close any game update or file verification, then retry preparation.'}
    if isinstance(error, (MemoryError,)):
        return {'code': 'reader_memory', 'message': 'The game reader ran out of memory. Close memory-heavy applications, then retry preparation.'}
    if isinstance(error, PermissionError):
        return {'code': 'file_access_denied', 'message': 'Access to a local file was denied. A game or toolkit file may be locked or its folder may not be writable. Close programs using those files, then retry. The local preparation log identifies the affected file.'}
    if isinstance(error, OSError):
        return {'code': 'files_unavailable', 'message': 'A required local file could not be read or written. Check the game folder, toolkit storage and reader tools, then retry. The local preparation log identifies the affected file.'}
    return {'code': 'reader_failed', 'message': 'The installed game data could not be prepared by this reader. Update the toolkit and verify game files, then retry. Details are saved in the local preparation log.'}
