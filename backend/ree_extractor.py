"""Build a selective reader from verified upstream source in the private tool cache.

REE's project lists resolve names; they do NOT limit extraction. Never invoke
the stock all-files unpacker for language preparation or on-demand voices.
Upstream source and binaries are downloaded locally, not redistributed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile

from . import game_tools
from .preparation_errors import PreparationFailure

SOURCE_REVISION = 'd22c15314e84eecd31480acfe692092c48043ac0'
SOURCE_SHA256 = 'eb868e19fe42ccc2f374a4c33963d9f2c5bbf996ca27f212b4de226c7d0f1776'
SOURCE_URL = f'https://codeload.github.com/Ekey/REE.PAK.Tool/zip/{SOURCE_REVISION}'
ADAPTER_VERSION = 1


def patch_source(name: str, source: str) -> str:
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('Verified REE source no longer matches the selective adapter')
        source = source.replace(old, new)
    if name.endswith('/PakUnpack.cs'):
        replace('var lpTable = TPakStream.ReadBytes(m_Header.dwTotalFiles * dwEntrySize);', '''
                if (m_Header.dwTotalFiles < 0 || m_Header.dwTotalFiles > 2000000)
                    throw new InvalidDataException("Invalid PAK entry count");
                var lpTable = TPakStream.ReadBytes(checked(m_Header.dwTotalFiles * dwEntrySize));''')
        replace('String m_FullPath = m_DstFolder + m_FileName.Replace("/", @"\\");', '''
                    if (m_FileName.StartsWith("__Unknown/", StringComparison.Ordinal)) continue;
                    String root = Path.GetFullPath(m_DstFolder).TrimEnd('\\\\') + "\\\\";
                    String m_FullPath = Path.GetFullPath(Path.Combine(root, m_FileName.Replace('/', '\\\\')));
                    if (!m_FullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("PAK output escapes destination");
                    if (m_Entry.dwCompressedSize < 0 || m_Entry.dwDecompressedSize < 0 ||
                        m_Entry.dwCompressedSize > 268435456 || m_Entry.dwDecompressedSize > 268435456)
                        throw new InvalidDataException("Selected PAK resource exceeds the reader limit");''')
    elif name.endswith('/PakFlags.cs'):
        replace('enum Compression : Int32', 'enum Compression : int')
        replace('enum Encryption : Int32', 'enum Encryption : int')
        replace('enum Features : Int16', 'enum Features : short')
    elif name.endswith('/Utils.cs'):
        replace('public static void iSetError(String m_String)\n        {', '''public static void iSetError(String m_String)
        {
            throw new InvalidDataException(m_String);
        }

        private static void UnusedErrorDisplay(String m_String)
        {''')
    return source


def ensure_extractor(tools: Path) -> Path:
    tools = tools.resolve()
    game_tools.install_archive(game_tools.REE_URL, game_tools.REE_SHA, tools,
                               ('REE.Unpacker.exe', 'Zstandard.Net.dll', 'System.Buffers.dll', 'libzstd.dll'))
    executable = tools / 'Toolkit.REE.Selective.exe'
    receipt = tools / 'selective-reader.json'
    adapter_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        state = json.loads(receipt.read_text(encoding='utf-8'))
        if (state['source'] == SOURCE_SHA256 and state['adapter'] == adapter_hash
                and state['binary'] == hashlib.sha256(executable.read_bytes()).hexdigest()):
            return executable
    except (OSError, ValueError, KeyError, TypeError):
        pass
    compiler = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
    if not compiler.is_file():
        raise PreparationFailure('reader_compiler_missing', 'The selective PRAGMATA reader requires the Windows .NET Framework compiler. Repair .NET Framework, then retry preparation.')
    archive = game_tools.download(SOURCE_URL)
    if hashlib.sha256(archive).hexdigest() != SOURCE_SHA256:
        raise PreparationFailure('reader_checksum', 'PRAGMATA reader source checksum mismatch; no reader was installed. Retry after checking your connection.')
    with tempfile.TemporaryDirectory(prefix='selective-ree-', dir=tools) as temporary:
        staging = Path(temporary)
        sources = []
        prefix = f'REE.PAK.Tool-{SOURCE_REVISION}/REE.Unpacker/REE.Unpacker/'
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            for entry in zipped.infolist():
                if not entry.filename.startswith(prefix) or not entry.filename.endswith('.cs'):
                    continue
                relative = PurePosixPath(entry.filename[len(prefix):])
                if relative.is_absolute() or '..' in relative.parts or entry.file_size > 1024 * 1024:
                    raise ValueError('Unsafe selective reader source')
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(patch_source('/' + relative.as_posix(), zipped.read(entry).decode('utf-8-sig').replace('\r\n', '\n')), encoding='utf-8')
                sources.append(str(path))
        if len(sources) != 17:
            raise ValueError('Selective reader source is incomplete')
        binary = staging / executable.name
        result = subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x86', '/optimize+',
            '/out:' + str(binary), '/reference:System.Numerics.dll',
            '/reference:' + str(tools / 'Zstandard.Net.dll'), '/reference:' + str(tools / 'System.Buffers.dll'),
            *sources], capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or not binary.is_file():
            raise PreparationFailure('reader_build_failed', 'The selective PRAGMATA reader could not be built. Repair .NET Framework, then retry preparation.')
        binary.replace(executable)
    game_tools._atomic_file(receipt, json.dumps({'source': SOURCE_SHA256, 'adapter': adapter_hash,
        'binary': hashlib.sha256(executable.read_bytes()).hexdigest()}).encode())
    return executable


def extract_project(tools: Path, project: str, archive: Path, destination: Path) -> None:
    if not project or any(character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for character in project):
        raise ValueError('Invalid selective extraction project')
    lines = (tools / 'Projects' / (project + '.list')).read_text(encoding='utf-8-sig').splitlines()
    if not lines or len(lines) > 100000:
        raise ValueError('Selective extraction requires a bounded list of files')
    for line in lines:
        path = PurePosixPath(line)
        if not line.startswith('natives/') or '..' in path.parts or '\\' in line or ':' in line or not line.isascii():
            raise ValueError('Unsafe requested game asset path')
    executable = ensure_extractor(tools)
    result = subprocess.run([str(executable), project, str(archive.resolve()), str(destination.resolve())],
        cwd=tools, capture_output=True, timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        if b'exceeds the reader limit' in result.stderr:
            raise PreparationFailure('reader_resource_limit', 'A requested PRAGMATA voice file exceeds this reader\'s safe memory limit. Update the toolkit before retrying.')
        raise PreparationFailure('archive_unreadable', 'The selective PRAGMATA reader could not read the installed archive. Verify game files in Steam, then retry language preparation.')
