import hashlib
import io
from pathlib import Path
import tarfile
import zipfile

import pytest

from backend import cyberpunk_build as build
from backend import cyberpunk_toolchain as tools


def archive(path, rows):
    with tarfile.open(path, 'w') as tar:
        for name, data in rows:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))


def test_source_selection_keeps_build_inputs_but_no_game_samples_or_opaque_natives(tmp_path):
    source = tmp_path / 'source.tar'
    rows = [('LICENSE', b'Full supplier terms'), ('Directory.Build.props', b'Authored props'),
            ('WolvenKit.Core/reader.cs', b'Authored reader source'),
            ('WolvenKit.Common/Resources/hashes.kark', b'Authored required embedded data'),
            ('WolvenKit.Core/lib/kraken.dll', b'Excluded opaque binary'),
            ('Tests/sample.wem', b'Never redistribute game samples'),
            ('WolvenKit/Assimp64.dll', b'Excluded unrelated editor')]
    archive(source, [('WolvenKit-9.0.1/' + name, data) for name, data in rows])
    first, second = tmp_path / 'first.zip', tmp_path / 'second.zip'
    selected = build.corresponding_source(source, first)
    build.corresponding_source(source, second)
    assert first.read_bytes() == second.read_bytes()
    assert set(selected) == {name for name, _ in rows[:4]}
    with zipfile.ZipFile(first) as zip:
        assert zip.read('WolvenKit.Core/reader.cs') == b'Authored reader source'


def test_source_selection_rejects_ambiguous_case_aliases(tmp_path):
    source = tmp_path / 'source.tar'
    archive(source, [('WolvenKit-9.0.1/WolvenKit.Core/a.cs', b'a'),
                     ('WolvenKit-9.0.1/WolvenKit.Core/A.cs', b'b')])
    with pytest.raises(ValueError, match='Duplicate'):
        build.corresponding_source(source, tmp_path / 'out.zip')


def test_mingw_patch_requires_exact_context_and_preserves_decoder_sources():
    data = '\n'.join(old for old, _new in build.HEADER_REPLACEMENTS).encode()
    patched = build.patch_header(data)
    assert b'<immintrin.h>' in patched and b'!defined(__MINGW32__)' in patched
    assert b'#ifndef __forceinline' in patched
    with pytest.raises(ValueError, match='differs'):
        build.patch_header(data.replace(b'limits.h', b'changed.h'))
    with pytest.raises(ValueError, match='differs'):
        build.patch_header(data + b'\n#include <limits.h>')


def test_native_compiler_cannot_authorize_new_output_bytes(tmp_path, monkeypatch):
    native_source = tmp_path / 'kraken.tar'
    header = '\n'.join(old for old, _new in build.HEADER_REPLACEMENTS).encode()
    archive(native_source, [('kraken-' + build.KRAKEN_REVISION + '/kraken.h', header)])
    monkeypatch.setattr(tools, 'verify_archive', lambda *_: None)
    compiler = tmp_path / 'compiler/bin/g++.exe'
    compiler.parent.mkdir(parents=True)
    compiler.write_bytes(b'Authored compiler')
    monkeypatch.setattr(build, 'COMPILER_SHA256', hashlib.sha256(compiler.read_bytes()).hexdigest())
    destination = tmp_path / 'runtime'
    (destination / 'reader').mkdir(parents=True)
    (destination / 'sources').mkdir()
    events = []
    class Compiler:
        def __init__(self, args, **kwargs):
            assert '-static' in args and '-Wl,--no-insert-timestamp,--exclude-all-symbols' in args
            assert not any('march=native' in flag for flag in args)
            (kwargs['cwd'] / 'kraken.dll').write_bytes(b'Changed compiler output')
            self.process, self.returncode = self, 0
        def communicate(self, timeout):
            return b'', b''
        def stop(self):
            events.append('stopped')
        def close_streams(self):
            events.append('closed')
    monkeypatch.setattr('backend.owned_process.OwnedProcess', Compiler)
    with pytest.raises(ValueError, match='reproduce'):
        build.build_kraken(native_source, destination, toolchain=compiler.parent.parent)
    assert not (destination / 'reader/kraken.dll').exists()
    assert events == ['stopped', 'closed']
