"""No native module may hide in an unaccounted owned software container."""
import io
from zipfile import ZipFile

import pytest

from backend.tests.test_android_bootstrap_native import audit
from backend.tests.test_android_python_dependencies import authored_elf


def fixture(fault=None):
    result=io.BytesIO()
    with ZipFile(result,'w') as apk:
        for abi,machine in [('arm64-v8a',183),('x86_64',62)]:
            native=authored_elf(machine=machine)
            apk.writestr('lib/'+abi+'/libc++_shared.so',native)
            apk.writestr('assets/chaquopy/bootstrap-native/'+abi+'/mmap.cpython-312.so',native)
            apk.writestr('assets/chaquopy/bootstrap-native/'+abi+'/java/chaquopy.so',native)
            for kind in ('stdlib','requirements'):
                if fault=='missing-container' and kind=='stdlib' and abi=='x86_64':continue
                contents=io.BytesIO()
                with ZipFile(contents,'w') as software:
                    if kind=='stdlib':
                        member='nested/_ssl.cpython-312.so' if fault=='stdlib-namespace' else '_ssl.cpython-312.so'
                        raw=authored_elf(machine=62 if abi=='arm64-v8a' and fault=='machine' else machine,
                            alignment=4096 if fault=='pages' else 16384)
                        software.writestr(member,raw)
                        if fault!='missing-sqlite':software.writestr('_sqlite3.cpython-312.so',native)
                    else:
                        member='unreviewed/extra.so' if fault=='dependency-namespace' else 'zstandard/backend_c.cpython-312.so'
                        software.writestr(member,native)
                apk.writestr('assets/chaquopy/'+kind+'-'+abi+'.imy',contents.getvalue())
        for kind in ('app','bootstrap','stdlib-common','requirements-common'):
            contents=io.BytesIO()
            with ZipFile(contents,'w') as software:
                if fault=='pure-native' and kind=='stdlib-common':software.writestr('hidden.so',authored_elf())
                else:software.writestr('owned.pyc',b'Authored package inventory fixture')
            apk.writestr('assets/chaquopy/'+kind+'.imy',contents.getvalue())
        if fault=='unknown-container':apk.writestr('assets/chaquopy/new-archive.imy',contents.getvalue())
        if fault=='loose-native':apk.writestr('assets/unreviewed.so',authored_elf())
        if fault=='unknown-abi':apk.writestr('lib/armeabi-v7a/libc.so',authored_elf())
    return ZipFile(io.BytesIO(result.getvalue()))


def test_every_actual_software_container_is_accounted_in_one_native_inventory():
    with fixture() as archive:value=audit().verify_native_inventory(archive)
    assert value['root_abis']==['arm64-v8a','x86_64']
    assert len(value['files'])==12 and len(value['containers'])==10
    assert sum(row['native_count'] for row in value['containers'].values())==12
    for abi in ('arm64-v8a','x86_64'):
        assert value['containers']['assets/chaquopy/stdlib-'+abi+'.imy']['native_count']==2


@pytest.mark.parametrize('fault',['missing-container','stdlib-namespace','machine','pages','missing-sqlite',
    'dependency-namespace','pure-native','unknown-container','loose-native','unknown-abi'])
def test_native_namespace_machine_and_alignment_are_never_silently_omitted(fault):
    with fixture(fault) as archive,pytest.raises(ValueError):audit().verify_native_inventory(archive)
