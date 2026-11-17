import stat
from types import SimpleNamespace

import pytest

from backend.private_data_paths import _no_links


@pytest.mark.parametrize('mode,attributes', [(stat.S_IFLNK, 0), (stat.S_IFDIR, 0x400)])
def test_linked_parent_is_rejected_before_any_descendant_metadata(mode, attributes):
    seen = []
    def metadata(name, bits, flags=0):
        seen.append(name)
        return SimpleNamespace(st_mode=bits, st_file_attributes=flags)
    root = SimpleNamespace(lstat=lambda: metadata('root', stat.S_IFDIR))
    parent = SimpleNamespace(lstat=lambda: metadata('parent', mode, attributes))
    def forbidden(): raise AssertionError('A linked parent exposed descendant metadata')
    leaf = SimpleNamespace(parents=(parent, root), lstat=forbidden)
    with pytest.raises(ValueError, match='filesystem links'):
        _no_links(leaf)
    assert seen == ['root', 'parent']


def test_ordinary_private_data_and_missing_new_file_are_allowed(tmp_path):
    (tmp_path / 'ordinary').mkdir()
    _no_links(tmp_path / 'ordinary' / 'new-file.json')
