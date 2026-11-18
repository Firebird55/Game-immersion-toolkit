"""Supplier subset safety; no compiler or network is invoked by these tests."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('publisher_hash_build', ROOT/'scripts/build-android-publisher-hash.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


def archive(tmp_path, *, duplicate=False, link=False):
    path = tmp_path/'original.tar.gz'
    values = {'deps/xxhash/xxhash.h':b'authored header', 'deps/xxhash/LICENSE':b'authored upstream notice', 'LICENSE':b'authored binding notice'}
    with tarfile.open(path, 'w:gz') as out:
        for name, raw in values.items():
            row = tarfile.TarInfo('xxhash-4.1.0/'+name); row.size = len(raw)
            if link and name == 'deps/xxhash/xxhash.h': row.type=tarfile.SYMTYPE;row.linkname='outside';row.size=0
            out.addfile(row, io.BytesIO(raw))
            if duplicate:out.addfile(row, io.BytesIO(raw))
    policy = {'root':'xxhash-4.1.0','bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'members':{name:hashlib.sha256(raw).hexdigest() for name,raw in values.items()}}
    return path, policy


def test_only_three_pinned_original_members_are_materialized_and_rechecked(tmp_path):
    path, policy=archive(tmp_path); destination=tmp_path/'selected'
    assert builder.selected_source(path,destination,policy)==destination
    assert {p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}==set(policy['members'])
    (destination/'LICENSE').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):builder.selected_source(path,destination,policy)


@pytest.mark.parametrize('change',['whole-hash','member-hash','duplicate','link','unexpected-subset'])
def test_changed_or_unsafe_supplier_is_rejected_before_any_compiler(tmp_path,change):
    path,policy=archive(tmp_path,duplicate=change=='duplicate',link=change=='link')
    if change=='whole-hash':policy['sha256']='0'*64
    if change=='member-hash':policy['members']['deps/xxhash/xxhash.h']='0'*64
    if change=='unexpected-subset':policy['members']['../outside']='0'*64
    with pytest.raises(ValueError):builder.selected_source(path,tmp_path/'selected',policy)


def test_parent_guard_precedes_any_archive_open(tmp_path,monkeypatch):
    checked=[]
    def reject(path):checked.append(path);raise ValueError('Unsafe parent')
    monkeypatch.setattr(builder,'_no_links',reject)
    with pytest.raises(ValueError,match='Unsafe parent'):builder.selected_source(tmp_path/'missing',tmp_path/'out',{})
    assert checked==[tmp_path/'missing']
