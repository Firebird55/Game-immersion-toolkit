"""Actionable public preparation failures, separate from private tool diagnostics."""
import subprocess


class PreparationFailure(ValueError):
    def __init__(self, code, message, *, game_files_changed=False, previous_snapshot_retained=False):
        self.code = code
        self.game_files_changed = game_files_changed
        self.previous_snapshot_retained = previous_snapshot_retained
        super().__init__(message)


def public_failure(error):
    if isinstance(error, PreparationFailure):
        return {'code': error.code, 'message': str(error), 'game_files_changed': error.game_files_changed,
                'previous_snapshot_retained': error.previous_snapshot_retained}
    if isinstance(error, subprocess.TimeoutExpired):
        return {'code': 'reader_timeout', 'message': 'The game reader exceeded its time limit. Close any game update or file verification, then retry preparation.'}
    if isinstance(error, (MemoryError,)):
        return {'code': 'reader_memory', 'message': 'The game reader ran out of memory. Close memory-heavy applications, then retry preparation.'}
    if isinstance(error, OSError):
        return {'code': 'files_unavailable', 'message': 'A required game file or reader could not be accessed. Check the game folder and tools in Settings, then retry preparation.'}
    return {'code': 'reader_failed', 'message': 'The installed game data could not be prepared by this reader. Update the toolkit and verify game files, then retry. Details are saved in the local preparation log.'}
