"""Stdlib-only shared checks for independent frozen probe images."""
import hashlib
import json
import os
import shutil
from pathlib import Path

from .runtime_bundle import RuntimeBundleError


def developer_environment():
    if any(shutil.which(name) for name in ('python', 'python3', 'pip', 'node', 'npm', 'npx', 'dotnet', 'csc', 'cl', 'wrangler')):
        raise RuntimeBundleError('Developer tools are still discoverable in the probe environment.')


def synthetic_roots(layout):
    marker = layout.state_root / 'synthetic-probe.json'
    if (not marker.is_file() or marker.is_symlink()
            or json.loads(marker.read_text()) != {'build_id': layout.build_id, 'synthetic': True}
            or any(layout.settings_root not in root.parents for root in
                   (layout.data_root, layout.cache_root, layout.tool_root, layout.work_root,
                    layout.state_root, layout.default_export_root))):
        raise RuntimeBundleError('Probes require newly owned synthetic roots and their build-bound marker.')


def block_remote_access(event, arguments):
    if event == 'socket.connect':
        address = arguments[1]
        if not isinstance(address, tuple) or address[0] != '127.0.0.1':
            raise RuntimeBundleError('Synthetic runtime probes cannot contact remote services.')


def loaded_native(layout):
    """Observe actual loaded images; never return host paths in public metadata."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.K32EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.K32GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    modules = (wintypes.HMODULE * 4096)()
    required = wintypes.DWORD()
    process = kernel.GetCurrentProcess()
    if not kernel.K32EnumProcessModules(process, modules, ctypes.sizeof(modules), ctypes.byref(required)) or required.value > ctypes.sizeof(modules):
        raise RuntimeBundleError('Loaded-module inventory is unavailable or truncated.')
    result = []
    system = Path(os.environ['WINDIR']).resolve()
    for module in modules[:required.value // ctypes.sizeof(wintypes.HMODULE)]:
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel.K32GetModuleFileNameExW(process, module, buffer, len(buffer))
        if not length or length >= len(buffer) - 1:
            raise RuntimeBundleError('Loaded-module path is unavailable or truncated.')
        path = Path(buffer.value).resolve()
        if path == layout.executable or layout.application_root in path.parents:
            origin = 'application'
            relative = path.relative_to(layout.application_root).as_posix()
        elif system in path.parents:
            origin, relative = 'windows-system', path.name
        else:
            raise RuntimeBundleError('A native image was loaded from outside the application and Windows.')
        if layout.executable.name == 'GameImmersionToolkit.exe' and relative.startswith('asr/'):
            raise RuntimeBundleError('Main runtime loaded a native image from the ASR tree.')
        with path.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        result.append({'file': relative, 'origin': origin, 'sha256': checksum})
    return sorted(result, key=lambda item: (item['origin'], item['file']))
