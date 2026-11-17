"""Shared bounded local-data inputs without archive-import dependencies."""
import stat

MAX_TEXT = 512 * 1024**2
MAX_ROWS = 1_000_000


def _no_links(path):
    # Inspect parents first, and use lstat before any operation that follows a
    # junction. A linked parent must not expose descendant metadata/content.
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Private data cannot follow filesystem links')
