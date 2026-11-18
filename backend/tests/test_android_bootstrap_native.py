"""Actual bootstrap-native envelope audit, without claiming target execution."""
import importlib.util
import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from backend.tests.test_android_python_dependencies import authored_elf

ROOT=Path(__file__).resolve().parents[2]


def audit():
    spec=importlib.util.spec_from_file_location('authored_bootstrap_audit',ROOT/'scripts/verify-android-apk.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@pytest.mark.parametrize('fault',[None,'wrong-machine','small-pages','missing-mmap','unknown-abi','nested-native'])
def test_bootstrap_extensions_including_mmap_require_both_real_abi_and_16k_headers(fault):
    raw=io.BytesIO()
    with ZipFile(raw,'w') as archive:
        for abi,machine in [('arm64-v8a',183),('x86_64',62)]:
            if fault=='missing-mmap' and abi=='x86_64':continue
            if fault=='unknown-abi' and abi=='x86_64':abi='armeabi-v7a'
            member='nested/mmap.cpython-312.so' if fault=='nested-native' else 'mmap.cpython-312.so'
            archive.writestr('assets/chaquopy/bootstrap-native/'+abi+'/'+member,
                authored_elf(machine=62 if fault=='wrong-machine' else machine,
                    alignment=4096 if fault=='small-pages' else 16384))
            # The actual Chaquopy embedding bridge lives in a package subdir;
            # this does not authorize arbitrary nested native extensions.
            archive.writestr('assets/chaquopy/bootstrap-native/'+abi+'/java/chaquopy.so',
                authored_elf(machine=machine))
    with ZipFile(io.BytesIO(raw.getvalue())) as archive:
        if fault:
            with pytest.raises(ValueError):audit().verify_bootstrap_native(archive)
        else:
            result=audit().verify_bootstrap_native(archive)
            assert len(result)==4 and {row['machine'] for row in result.values()}=={183,62}
            assert all(row['minimum_load_alignment']==16384 for row in result.values())
