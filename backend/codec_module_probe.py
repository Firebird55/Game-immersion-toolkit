"""Observe real modules of the exact owned native codec, without host paths.

The spy captures the existing real Windows Job Object, not a simulated process
or module list. A held stdin lets the probe inspect the CLI before releasing an
authored frame and confirming that same process's decoded output and cleanup.
"""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from . import preparation_worker
from .prebuilt_codecs import PINNED_FILES
from .prebuilt_readers import reader_environment
from .runtime_bundle import RuntimeBundleError
from .runtime_probe_common import loaded_native
from .windows_preparation_process import WindowsPreparationProcess


def checked_modules(layout, decoder, records):
    relative = decoder.executable.parent.relative_to(layout.application_root).as_posix()
    prefix = '' if relative == '.' else relative + '/'
    expected = {(prefix + name).casefold(): PINNED_FILES[name] for name in ('flac.exe', 'FLAC.dll')}
    actual = {r['file'].casefold(): r['sha256'] for r in records if r['origin'] == 'application'}
    system = {r['file'].casefold() for r in records if r['origin'] == 'windows-system'}
    if (actual != expected or len(records) != len({(r['origin'], r['file'].casefold()) for r in records})
            or any(r['origin'] not in {'application', 'windows-system'} for r in records)
            or not {'vcruntime140.dll', 'ucrtbase.dll'} <= system):
        raise RuntimeBundleError('Codec DLL origins differ from the pinned sibling files and Windows CRT prerequisites.')
    return records


def observe(layout, decoder, data, expected):
    if os.name != 'nt':
        raise RuntimeBundleError('Actual codec module observation requires Windows.')
    cancelled = threading.Event()
    job = preparation_worker.PreparationJob(SimpleNamespace(stop_event=cancelled, _publication_lock=threading.RLock()), cancelled)
    trees, errors, statuses = [], [], []
    def capture_tree():
        tree = WindowsPreparationProcess()
        trees.append(tree)
        return tree
    with tempfile.TemporaryDirectory(prefix='DLL observation 漢字 ', dir=layout.work_root) as tmp:
        cwd = Path(tmp); output = cwd / 'observed.pcm'
        # Authored invalid bytes in CWD must never replace app-local/OS images.
        for name in ('FLAC.dll', 'VCRUNTIME140.dll'):
            (cwd / name).write_bytes(b'authored DLL-search bait; not executable')
        read_fd, write_fd = os.pipe()
        reader, writer = os.fdopen(read_fd, 'rb'), os.fdopen(write_fd, 'wb', buffering=0)
        def run():
            try:
                statuses.append(job.run(decoder._command('-', output, 512), cwd=cwd, timeout=10,
                    stdin=reader, env=layout.child_environment('windows-bootstrap', reader_environment())))
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=run, name='owned-codec-module-probe')
        records = None
        # Constructor observation only: all Win32 ownership, process creation,
        # execution, module queries and shutdown use the actual implementations.
        with patch.object(preparation_worker, 'WindowsPreparationProcess', capture_tree):
            thread.start()
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and thread.is_alive() and records is None:
                    if trees:
                        tree = trees[0]; kernel = tree.kernel
                        kernel.K32GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
                        kernel.K32GetModuleFileNameExW.restype = wintypes.DWORD
                        for pid in tree._process_ids(deadline):
                            handle = kernel.OpenProcess(0x410, False, pid)  # QUERY_INFORMATION | VM_READ
                            if not handle: continue
                            try:
                                member = wintypes.BOOL()
                                if not kernel.IsProcessInJob(handle, tree.handle, ctypes.byref(member)) or not member.value:
                                    continue
                                path = ctypes.create_unicode_buffer(32768)
                                length = kernel.K32GetModuleFileNameExW(handle, None, path, len(path))
                                if not length or length >= len(path)-1 or Path(path.value).resolve() != decoder.executable:
                                    continue
                                try:
                                    found = loaded_native(layout, process=handle)
                                except RuntimeBundleError as error:
                                    if 'unavailable' in str(error): continue  # Loader initialization race.
                                    raise
                                names = {r['file'].casefold().split('/')[-1] for r in found}
                                if {'flac.exe', 'flac.dll', 'vcruntime140.dll', 'ucrtbase.dll'} <= names:
                                    records = checked_modules(layout, decoder, found)
                            finally:
                                if not kernel.CloseHandle(handle):
                                    raise RuntimeBundleError('Owned codec observation handle close could not be confirmed.')
                    if records is None: time.sleep(.02)
                if records is None:
                    raise RuntimeBundleError('Owned codec DLL inventory was not observable before its deadline.')
                writer.write(data); writer.close()
                thread.join(15)
                if thread.is_alive():
                    raise RuntimeBundleError('Observed codec thread did not finish before its deadline.')
                if errors:
                    raise RuntimeBundleError('Observed codec process failed: ' + type(errors[0]).__name__)
                if statuses != [0]:
                    raise RuntimeBundleError('Observed codec exited with status ' + str(statuses))
                if not output.is_file() or output.read_bytes() != expected:
                    count = output.stat().st_size if output.is_file() else -1
                    raise RuntimeBundleError('Observed codec PCM mismatch; actual bytes ' + str(count))
            finally:
                cancelled.set()
                writer.close()
                thread.join(15)
                reader.close()
                if thread.is_alive():
                    raise RuntimeBundleError('Owned codec observation thread did not finish cleanup.')
    return {'status': 'passed', 'phase': 'owned codec waiting for stdin, followed by verified PCM decode',
        'loaded_native': records, 'cwd_dll_bait': 'ignored', 'owned_cleanup': 'passed',
        'scope': 'actual snapshot for this decoder/input; not every future dynamic load or Windows 11 acceptance'}
