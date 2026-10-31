"""Private PATH query for the explicitly selected experimental build Python.

This neither resolves a dependency nor approves a native source. The existing
Analysis observer remains authoritative and may still refuse the frozen build.
"""
import argparse
import json
import os
import struct
import sys


SCHEMA = 'proxy-r19-runtime-build-environment-v1'
MAX_PATH_UNITS = 32766
MAX_ROOTS = 5


class BuildEnvironmentError(ValueError):
    def __init__(self):
        super().__init__('Experimental build PATH query refused.')


def runtime_build_environment(selected_python, *, system_directory_provider=None, windows_directory_provider=None):
    """Return private canonical roots only; no inherited PATH or env fallback."""
    try:
        from record_runtime import native_path, native_system_directory, native_windows_directory
        if sys.platform != 'win32' or struct.calcsize('P') != 8:
            raise BuildEnvironmentError()
        def checked(path, *, directory=False):
            raw = os.fspath(path)
            if (not isinstance(raw, str) or not raw or ';' in raw or '"' in raw
                    or any(ord(char) < 32 or ord(char) == 127 for char in raw)
                    or len(raw.encode('utf-16-le')) // 2 > MAX_PATH_UNITS):
                raise BuildEnvironmentError()
            return native_path(raw, directory=directory)
        selected = checked(selected_python)
        executable = checked(sys.executable)
        prefix = checked(sys.prefix, directory=True)
        base = checked(sys.base_prefix, directory=True)
        scripts = checked(prefix / 'Scripts', directory=True)
        if (os.path.normcase(str(selected)) != os.path.normcase(str(executable))
                or selected.parent not in {prefix, scripts}):
            raise BuildEnvironmentError()
        system = checked((system_directory_provider or native_system_directory)(), directory=True)
        windows = checked((windows_directory_provider or native_windows_directory)(), directory=True)
        if windows not in system.parents:
            raise BuildEnvironmentError()
        roots, seen = [], set()
        for root in (selected.parent, scripts, base, system, windows):
            key = os.path.normcase(str(root))
            if key not in seen:
                seen.add(key)
                roots.append(str(root))
        value = ';'.join(roots)
        if not 1 <= len(roots) <= MAX_ROOTS or len(value.encode('utf-16-le')) // 2 > MAX_PATH_UNITS:
            raise BuildEnvironmentError()
        return {'schema': SCHEMA, 'path': value}
    except BuildEnvironmentError:
        raise
    except Exception:
        raise BuildEnvironmentError() from None


def main():
    parser = argparse.ArgumentParser(description='Query private experimental freezer PATH; never print it to a public receipt.')
    parser.add_argument('--selected-python', required=True)
    args = parser.parse_args()
    try:
        value = runtime_build_environment(args.selected_python)
    except Exception:
        print('Experimental build PATH query refused.', file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
