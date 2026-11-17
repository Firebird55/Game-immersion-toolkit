"""Read selected NTE localization and exact original Wwise event references.

The native reader is toolkit-owned glue for separately downloaded UEExtractor.
Only installed game data is extracted, into private caches outside the game.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import shutil
import struct
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from .bilingual import contains_han
from .game_tools import download, install_archive
from .pragmata_audio import read_bank_play_layers
from .preparation_errors import PreparationFailure
from .textmaps import display_text

READER_URL = "https://github.com/SolicenTEAM/UEExtractor/releases/download/v.1.0.8.7/UEExtractor.zip"
READER_SHA = "e89ffece53cc11970d08f6d0a683b67ca58882e8c51fb99de07923175eb96660"
READER_REVISION = "1dff3554320d530efff26a827819f0e011f1b892"
TABLE_SCHEMA_SHA256 = '7651a4e56f79b2c6c9d7bde31a8dadbfc929b2e923691461c6970ce0bdb0ff58'
TABLE_SCHEMA_URL = ('https://raw.githubusercontent.com/555me/NTE-usmap/'
                    '1b92d5267092dac6bcfec605bcaf6ae05b664746/mapping/HT-1.4-1413.usmap')
MEDIA_ROOT = "HT/Content/WwiseAudio/Media/Chinese/"
LANGUAGE_INDEX_VERSION = 10
SUPPORTED_LOCALES = ('en', 'zh-Hans', 'zh-Hant', 'ja', 'ko')
TEXT_LOCALES = {'en': 'en', 'zh-Hans': 'zh-CN', 'zh-Hant': 'zh-Hant', 'ja': 'ja', 'ko': 'ko',
    'fr': 'fr', 'de': 'de', 'es-ES': 'es', 'pt-BR': 'pt-BR', 'ru': 'ru', 'th': 'th', 'vi': 'vi', 'id': 'id'}
VOICE_LOCALES = {'en': 'English', 'zh-Hans': 'Chinese', 'zh-Hant': 'Chinese', 'ja': 'Japanese', 'ko': 'Korean'}


def wwise_hash(value: str) -> int:
    result = 2166136261
    for byte in value.lower().encode("utf-8"):
        result = ((result * 16777619) & 0xffffffff) ^ byte
    return result


def dotnet_sdk() -> Path | None:
    candidates = [shutil.which("dotnet"), str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "dotnet/dotnet.exe")]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            result = subprocess.run([candidate, "--list-sdks"], capture_output=True, timeout=15,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode == 0 and re.search(rb"(?m)^10\.\d+\.\d+ ", result.stdout):
                return Path(candidate)
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def ensure_extractor(directory: Path) -> Path:
    from .runtime_bundle import discover_layout
    if discover_layout().mode == 'bundle':
        from .nte_toolchain import resolve
        return resolve().executable
    sdk = dotnet_sdk()
    if sdk is None:
        raise ValueError("NTE needs the .NET 10 SDK. Install it from https://dotnet.microsoft.com/download/dotnet/10.0, then prepare tools again.")
    upstream = directory / "upstream"
    install_archive(READER_URL, READER_SHA, upstream, ("UEExtractor.dll", "UEExtractor.runtimeconfig.json"))
    notice = upstream / "UEEXTRACTOR-LICENSE.txt"
    if not notice.is_file():
        data = download(f"https://raw.githubusercontent.com/SolicenTEAM/UEExtractor/{READER_REVISION}/LICENSE")
        if b"MIT License" not in data:
            raise ValueError("Game reader license notice is unavailable")
        notice.write_bytes(data)
    source = Path(__file__).resolve().parents[1] / "scripts/game-readers"
    inputs = [source / "NteReader.cs", source / "NteReader.csproj"]
    revision = hashlib.sha256(b"".join(path.read_bytes() for path in inputs)).hexdigest()
    target, marker = directory / "NteReader.dll", directory / "reader-build.json"
    try:
        receipt = json.loads(marker.read_text(encoding="utf-8"))
        if receipt["source"] == revision and all((directory / name).is_file() and
                hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
                for name, digest in receipt["files"].items()) and target.is_file():
            return target
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Build intermediates and binaries stay in the ignored tool cache. No NuGet
    # package is needed; use the installed .NET 10 framework reference packs.
    with tempfile.TemporaryDirectory(prefix="nte-build-", dir=directory) as value:
        build = Path(value)
        result = subprocess.run([str(sdk), "build", str(inputs[1]), "-c", "Release", "-o", str(build / "out"),
            f"-p:BaseIntermediateOutputPath={build / 'obj'}/", "--nologo", "--ignore-failed-sources"],
            capture_output=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("NTE reader build failed; install or repair the .NET 10 SDK")
        files = {}
        for name in ("NteReader.dll", "NteReader.deps.json", "NteReader.runtimeconfig.json"):
            content = (build / "out" / name).read_bytes()
            files[name] = hashlib.sha256(content).hexdigest()
            (directory / name).write_bytes(content)
        marker.write_text(json.dumps({"source": revision, "files": files}), encoding="utf-8")
    return target


def archive_sources(install: Path) -> list[Path]:
    root = install / "Client/WindowsNoEditor/HT/Content"
    return sorted((p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in
                   {".pak", ".utoc", ".ucas", ".hpw"}), key=str)


def fingerprint(install: Path) -> str:
    # Hotfixes can change loose localization, configuration, movies or assets
    # without touching a voice bank. Include every installed content/config file,
    # but never mutable Saved logs, preferences or account files.
    game = install / 'Client/WindowsNoEditor/HT'
    sources = sorted((p for folder in ('Content', 'Config') for p in (game / folder).rglob('*')
                      if p.is_file()), key=str)
    executable = install / "Client/WindowsNoEditor/HT/Binaries/Win64/HTGame.exe"
    if executable.is_file():
        sources.append(executable)
    values = [f"{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in sources]
    from .nte_cinematics import CATALOG_REVISION
    reader = Path(__file__).resolve().parents[1] / 'scripts/game-readers'
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    if layout.mode == 'bundle':
        from .prebuilt_readers import reader_source_identity
        revision = reader_source_identity('nte', layout=layout)
    else:
        revision = hashlib.sha256(b''.join((reader / name).read_bytes() for name in
                                          ('NteReader.cs', 'NteReader.csproj'))).hexdigest()
    return hashlib.sha256((f'reader5|{LANGUAGE_INDEX_VERSION}|{READER_SHA}|{revision}|' +
                          CATALOG_REVISION + '|' + '|'.join(values)).encode()).hexdigest()


def publisher_fingerprint(tools: Path) -> str:
    from . import nte_publisher
    return nte_publisher.fingerprint(tools)


def publisher_snapshot_available(tools: Path, stamp: str) -> bool:
    from . import nte_publisher
    return nte_publisher.snapshot_available(tools, stamp)


def _metadata_path(install: Path, stamp: str) -> Path:
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    root = (layout.settings_root if layout.mode == 'bundle' else
            Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "Proxy Transcript")
    identity = hashlib.sha256((str(install.resolve()) + stamp).encode()).hexdigest()
    return root / "nte-archive" / (identity + ".dpapi")


@lru_cache(maxsize=2)
def _archive_metadata(install: Path, stamp: str) -> str:
    from .lexirise import _protect
    path = _metadata_path(install, stamp)
    if path.is_file():
        try:
            value = _protect(path.read_bytes(), decrypt=True).decode()
            if re.fullmatch(r"0x[0-9a-fA-F]{64}", value):
                return value
        except Exception:
            pass
    from .nte_archive_metadata import for_install, load
    return for_install(install, load(fetch=download))


def _stage_table_schema(cache: Path, destination: Path) -> None:
    """Cache format metadata; actual row values come from the selected original release."""
    cached = cache / (TABLE_SCHEMA_SHA256 + '.usmap')
    limit = 8 * 1024 * 1024
    try:
        if cached.stat().st_size <= limit:
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() == TABLE_SCHEMA_SHA256:
                (destination / 'dialogue.usmap').write_bytes(data)
                return
    except FileNotFoundError:
        pass
    try:
        data = download(TABLE_SCHEMA_URL, limit=limit)
    except OSError as error:
        raise PreparationFailure('game_metadata_unavailable',
            'NTE dialogue type metadata is unavailable. Retry preparation when the provider is reachable. The previous index is retained.') from error
    if hashlib.sha256(data).hexdigest() != TABLE_SCHEMA_SHA256:
        raise PreparationFailure('unsupported_game_format', 'NTE dialogue type metadata failed verification. Retry preparation to retain the last verified index.')
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        pending = Path(tmp) / 'verified.usmap'
        pending.write_bytes(data)
        pending.replace(cached)
    (destination / 'dialogue.usmap').write_bytes(data)


def _reader_invocation(install: Path, executable: Path, destination: Path, mode: str):
    if destination.resolve().is_relative_to(install.resolve()):
        raise ValueError("Reader outputs must stay outside the selected source context")
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    if layout.mode == 'bundle':
        from .nte_toolchain import command
        invocation, environment, working_directory = command(install, destination, mode, layout=layout)
        if str(executable) != invocation[0]:
            raise ValueError('The selected archive reader differs from the bundled executable')
    else:
        sdk = dotnet_sdk()
        if sdk is None or not executable.is_file():
            raise ValueError("Prepare NTE tools in Setup before indexing")
        working_directory = executable.resolve().parent / 'upstream'
        invocation = [str(sdk), str(executable.resolve()), mode, str(install.resolve()), str(working_directory), str(destination.resolve())]
        environment = None
    return invocation, environment, working_directory


def _publisher_key_bindings(containers, keys):
    """Bind only current-original-proved ciphers to their authenticated TOC GUID."""
    if not isinstance(keys, list):
        return {}
    from .nte_archive_metadata import check
    check(0 < len(keys) <= 8 and len(set(keys)) == len(keys))
    result = {}
    for container in containers.values():
        if not container.encrypted:
            continue
        check(container.selected_key in keys and len(container.encryption_guid) == 16)
        # Unreal FGuid serializes four little-endian uint32 components; its
        # managed digit representation prints those components in that order.
        guid = ''.join(f'{part:08x}' for part in struct.unpack('<4I', container.encryption_guid))
        index = keys.index(container.selected_key)
        check(guid not in result or result[guid] == index)
        result[guid] = index
    return {'archive_key_guids': result}


def run_publisher_reader(context: Path, executable: Path, destination: Path, containers, archive_metadata,
                         *, schema_cache: Path | None = None, inventory=False, table_schema=None,
                         capture_schema_usage=False, capture_dialogue_graphs=False, dialogue_registry=None,
                         capture_original_authoring=False):
    """Read authoring from checked publisher streams, never an installed game."""
    from .nte_publisher_stream import Broker
    mode = 'inventory' if inventory else 'publisher-tables'
    outputs = ('inventory.json',) if inventory else ('dialogue-events.json', 'sequence-cues.json', 'voice-events.json', 'movie-tables.json')
    if capture_original_authoring:
        if not capture_dialogue_graphs:
            raise ValueError('Original NTE authoring requires current original registry and schema validation')
        outputs += ('original-authoring.json',)
    if capture_schema_usage:
        if inventory or table_schema is None:
            raise ValueError('NTE schema usage requires an explicit publisher table schema')
        outputs += ('schema-usage.json',)
    if capture_dialogue_graphs:
        if not capture_schema_usage or not isinstance(dialogue_registry, bytes) or not 0 < len(dialogue_registry) <= 256*1024**2:
            raise ValueError('NTE dialogue graphs require current-invocation schema validation')
        outputs += ('dialogue-graphs.json',)
        registry_path = destination/'dialogue-registry.bin'
        if registry_path.exists():
            raise ValueError('NTE dialogue registry requires a fresh staging directory')
        registry_path.write_bytes(dialogue_registry)
    elif dialogue_registry is not None:
        raise ValueError('NTE dialogue registry requires graph extraction')
    if any((destination / name).exists() for name in outputs):
        raise ValueError('NTE publisher extraction requires a fresh staging directory')
    invocation, environment, working_directory = _reader_invocation(context, executable, destination, mode)
    if not inventory:
        if schema_cache is None:
            raise ValueError('NTE publisher authoring requires verified type metadata')
        if table_schema is None:
            _stage_table_schema(schema_cache, destination)
        else:
            data, digest = table_schema.data, table_schema.reference['sha256']
            if (not isinstance(data, bytes) or not 16 <= len(data) <= 8 * 1024**2 or
                    hashlib.sha256(data).hexdigest() != digest):
                raise PreparationFailure('game_metadata_unavailable', 'The selected NTE dialogue type data failed verification.')
            (destination / 'dialogue.usmap').write_bytes(data)
    with Broker(containers) as broker:
        request = {'archive_metadata': archive_metadata, 'publisher_streams': broker.descriptors}
        request.update(_publisher_key_bindings(containers, archive_metadata))
        nonce = secrets.token_hex(16) if capture_schema_usage else None
        if not inventory:
            request['type_schema_sha256'] = TABLE_SCHEMA_SHA256 if table_schema is None else table_schema.reference['sha256']
            if capture_schema_usage:
                request.update(capture_schema_usage=True, schema_usage_nonce=nonce)
            if capture_dialogue_graphs:
                request['capture_dialogue_graphs'] = True
                request['dialogue_registry_sha256'] = hashlib.sha256(dialogue_registry).hexdigest()
            if capture_original_authoring:
                request['capture_original_authoring'] = True
        try:
            result = subprocess.run(invocation, input=json.dumps(request).encode(), capture_output=True,
                timeout=600, cwd=working_directory, env=environment,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.SubprocessError):
            raise PreparationFailure('game_metadata_unavailable',
                'The NTE publisher reader could not finish. Retry preparation; the previous index is retained.') from None
        if broker.failures:
            failure = broker.failures[0]
            code = failure.code if isinstance(failure, PreparationFailure) else 'game_metadata_unavailable'
            raise PreparationFailure(code,
                'NTE publisher resources could not be verified. Retry preparation; the previous index is retained.') from None
    if result.returncode or not all((destination / name).is_file() for name in outputs):
        raise PreparationFailure('unsupported_game_format',
            'The NTE publisher dialogue format is unsupported or incomplete. Retry preparation; the previous index is retained.')
    if capture_schema_usage:
        if capture_original_authoring:
            from .nte_authoring import read_original_authoring
            read_original_authoring(destination/'original-authoring.json',
                schema_sha256=table_schema.reference['sha256'], nonce=nonce,
                registry_sha256=hashlib.sha256(dialogue_registry).hexdigest())
        return read_schema_usage(destination, table_schema.reference['sha256'], nonce)


def read_schema_usage(destination, schema_sha256, nonce):
    """Accept only complete lookup/class evidence from this reader invocation."""
    path = destination / 'schema-usage.json'
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= 16*1024**2:
            raise ValueError()
        value = json.loads(path.read_bytes())
        base = {'schema', 'complete', 'nonce', 'schema_sha256', 'lookups', 'classes'}
        if not isinstance(value, dict):
            raise ValueError()
        version = value.get('schema')
        if (version not in ('nte-schema-usage-v1', 'nte-schema-usage-v2')
                or set(value) != (base | {'codecs', 'codecs_origin'} if version == 'nte-schema-usage-v2' else base)
                or value['complete'] is not True
                or value['nonce'] != nonce or value['schema_sha256'] != schema_sha256
                or not isinstance(value['lookups'], list) or not 0 < len(value['lookups']) <= 100_000
                or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,255}', n) for n in value['lookups'])
                or len(set(value['lookups'])) != len(value['lookups']) or not isinstance(value['classes'], dict)
                or len(value['classes']) > 100_000):
            raise ValueError()
        for name, implementation in value['classes'].items():
            if (not isinstance(name, str) or not isinstance(implementation, str) or len(implementation) > 512
                    or not re.fullmatch(r'CUE4Parse\.UE4\.Assets\.Exports\.(?:[A-Za-z_][A-Za-z0-9_]*\.)*U[A-Za-z_][A-Za-z0-9_]*', implementation)
                    or implementation.rsplit('.', 1)[-1] != 'U'+name):
                raise ValueError()
        if version == 'nte-schema-usage-v2':
            if (value['codecs_origin'] != 'zero-without-package-v1' or not isinstance(value['codecs'], dict)
                    or len(value['codecs']) > 100_000):
                raise ValueError()
            for name, implementation in value['codecs'].items():
                if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,255}', name)
                        or name in value['lookups'] or not isinstance(implementation, str) or len(implementation) > 512
                        or not re.fullmatch(r'CUE4Parse\.(?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*', implementation)
                        or implementation.rsplit('.', 1)[-1] == 'FStructFallback'):
                    raise ValueError()
        return value
    except (OSError, ValueError, TypeError):
        raise PreparationFailure('game_metadata_unavailable',
            'The NTE reader could not verify its required format metadata. The previous completed index is retained.') from None


def read_dialogue_inventory(context, executable, destination, containers, archive_metadata, registry,
                            *, capture_original_authoring=False):
    """Read complete registry-selected package claims before bounded prefetch."""
    from .nte_publisher_stream import Broker
    destination = Path(destination)
    if (not isinstance(registry, bytes) or not 0 < len(registry) <= 256*1024**2
            or any((destination/name).exists() for name in ('dialogue-registry.bin', 'dialogue-inventory.json'))):
        raise ValueError('NTE dialogue inventory requires a fresh staging directory and original registry')
    sha, nonce = hashlib.sha256(registry).hexdigest(), secrets.token_hex(16)
    (destination/'dialogue-registry.bin').write_bytes(registry)
    invocation, environment, working = _reader_invocation(context, executable, destination, 'publisher-dialogue-inventory')
    with Broker(containers) as broker:
        request = {'archive_metadata': archive_metadata, 'publisher_streams': broker.descriptors,
                   'dialogue_registry_sha256': sha, 'inventory_nonce': nonce}
        request.update(_publisher_key_bindings(containers, archive_metadata))
        if capture_original_authoring:
            request['capture_original_authoring'] = True
        try:
            result = subprocess.run(invocation, input=json.dumps(request).encode(), capture_output=True, timeout=180,
                cwd=working, env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.SubprocessError):
            raise PreparationFailure('game_metadata_unavailable',
                'The original NTE dialogue inventory could not finish. Retry preparation; '
                'the previous completed index is retained.') from None
        if broker.failures:
            raise PreparationFailure('game_metadata_unavailable',
                'Original NTE package indexes could not be verified. Retry preparation; '
                'the previous completed index is retained.')
    try:
        from pathlib import PurePosixPath
        path = destination/'dialogue-inventory.json'
        if result.returncode or not path.is_file() or not 0 < path.stat().st_size <= 16*1024**2:
            raise ValueError()
        value = json.loads(path.read_bytes())
        if (not isinstance(value, dict) or set(value) != {'schema', 'complete', 'registry_sha256', 'nonce', 'package_count', 'packages'}
                or value['schema'] != 'nte-original-dialogue-inventory-v1' or value['complete'] is not True
                or value['nonce'] != nonce or value['registry_sha256'] != sha or type(value['package_count']) is not int
                or not isinstance(value['packages'], dict) or not 0 < len(value['packages']) <= 8192
                or value['package_count'] != len(value['packages'])):
            raise ValueError()
        packages = value['packages']
        if (len({name.casefold() for name in packages}) != len(packages)
                or any(not name.startswith('HT/Content/') or not name.endswith('.uasset')
                    or name != str(PurePosixPath(name)) or '..' in PurePosixPath(name).parts
                    or '\\' in name or any(char in name for char in '\r\n\0')
                    or type(size) is not int or not 0 < size <= 4*1024**2 for name, size in packages.items())
                or sum(packages.values()) > 128*1024**2):
            raise ValueError()
        return packages
    except (OSError, ValueError, TypeError, KeyError):
        raise PreparationFailure('unsupported_game_format',
            'The original NTE dialogue inventory is incomplete or unsupported. '
            'The previous completed index is retained.') from None


def run_reader(install: Path, executable: Path, destination: Path, mode: str, depot: str | None = None, cinema_events: list[str] | None = None, depots: list[str] | None = None, *, locales=None, voice_language=None, schema_cache: Path | None = None) -> None:
    invocation, environment, working_directory = _reader_invocation(install, executable, destination, mode)
    install, executable, destination = install.resolve(), executable.resolve(), destination.resolve()
    stamp = fingerprint(install)
    root = install / "Client/WindowsNoEditor/HT/Content"
    if any(any(part.startswith("~") for part in path.relative_to(root).parts) or
           not re.fullmatch(r"pakchunk\d+[-A-Za-z0-9_]*\.pak", path.name)
           for path in root.rglob("*.pak")):
        raise ValueError("NTE indexing requires official archives; remove unsupported mod archives before indexing")
    # Metadata is never an argument or a log entry. Keep it in memory and pass
    # via stdin. A host-protected cache allows playback without a network call.
    key = _archive_metadata(install, stamp)
    request = {"archive_metadata": key}
    if mode == 'index' and schema_cache is not None:
        _stage_table_schema(schema_cache, destination)
        request['read_dialogue_tables'] = True
    if locales is not None:
        request['locales'] = locales
    if voice_language is not None:
        if voice_language not in set(VOICE_LOCALES.values()):
            raise ValueError('Unsupported NTE voice locale')
        request['voice_language'] = voice_language
    if depot is not None:
        request["depot"] = depot
    if depots is not None:
        request['depots'] = depots
    if cinema_events is not None:
        request['cinema_events'] = cinema_events
    try:
        result = subprocess.run(invocation,
            input=json.dumps(request).encode(), capture_output=True, timeout=600, cwd=working_directory, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("NTE reader could not complete") from None
    if result.returncode == 3:
        raise PreparationFailure('unsupported_game_format',
            'This NTE update uses an unsupported localization or dialogue-table format. Update the toolkit, then retry preparation; the previous index is retained.')
    if result.returncode:
        raise RuntimeError("NTE extraction failed; check installed archives and reader compatibility")
    if request.get('read_dialogue_tables') and not (destination / 'dialogue-events.json').is_file():
        raise PreparationFailure('unsupported_game_format', 'The NTE reader did not return the declared dialogue table. Update the toolkit and retry.')
    if os.name == "nt":
        from .lexirise import _protect
        path = _metadata_path(install, stamp)
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".pending")
            temporary.write_bytes(_protect(key.encode()))
            temporary.replace(path)


def punctuation_anchors(text):
    # Native OCR can read the game's authored opening double dash as one or
    # two Han horizontal strokes. Keep the official text and voice unchanged;
    # ordinary words and unsupported dialogue rewrites remain exact-only.
    match = re.match(r'^[—–―]{2,}\s*(.+)', text)
    return [prefix + match[1] for prefix in ('一', '一一', 'ー', 'ーー')] if match else []


def ocr_anchors(text, locale):
    forms = [text, *punctuation_anchors(text)]
    if locale == 'ja':
        # A repeated vowel may be typeset small for expressive speech. Native
        # OCR sometimes gives it full size. Do not fold digraphs such as ティ
        # or small ゃ/ゅ/ょ, whose size can change the actual syllable.
        vowels = [('あかがさざただなはばぱまやらわ', 'ぁ', 'あ'),
                  ('いきぎしじちぢにひびぴみり', 'ぃ', 'い'),
                  ('うくぐすずつづぬふぶぷむゆる', 'ぅ', 'う'),
                  ('えけげせぜてでねへべぺめれ', 'ぇ', 'え'),
                  ('おこごそぞとどのほぼぽもよろを', 'ぉ', 'お')]
        for form in list(forms):
            changes = [(i, full) for preceding, small, full in vowels for i in range(1, len(form))
                       if form[i] == small and form[i - 1] in preceding]
            if len(changes) <= 4:
                for mask in range(1, 1 << len(changes)):
                    value = list(form)
                    for bit, (position, full) in enumerate(changes):
                        if mask & (1 << bit):
                            value[position] = full
                    forms.append(''.join(value))
    return list(dict.fromkeys(value for value in forms if value != text))


def dialogue_presentation(namespace: str, key: str) -> tuple[str, bool]:
    """Classify reviewed authored tables, never infer silence from missing media."""
    if namespace in {'ST_Bagel_Reply', 'ST_Bagel_TitleContent'}:
        return 'social_message', True
    if namespace == 'ST_PlayerBirthdayMail' and '_Content_' in key:
        return 'mail', True
    if namespace.startswith('ST_Sequence'):
        return 'cinematic', False
    if namespace == 'ST_AmbianceDialogue' and '_option_Player_' in key:
        return 'response_option', False
    if namespace == 'ST_AmbianceDialogue' or namespace.startswith('ST_Bubble_') or namespace == 'ST_StoryBubble':
        return 'ambient_dialogue', False
    if namespace == 'ST_File':
        return 'character_archive', False  # Contains both profiles and playable voice lines.
    if namespace == 'ST_Likeability':
        return 'bond_dialogue', False  # Chat and interaction tables require row-level ownership.
    if namespace == 'ST_DialogueSumUP':
        return 'narrative_summary', True
    if namespace.startswith('ST_Dialogue_') or namespace in {
            'ST_MainDialogue', 'ST_Miandialogue_Wuchao', 'ST_Main_BlackBird',
            'ST_Legend_Shinku', 'ST_Legend_Celebration', 'ST_WorldActorDialogue', 'ST_RideAlong'}:
        return 'conversation', False
    return 'uncategorized', False


def coverage_warnings(records: list[dict], *, publisher=False) -> list[str]:
    warnings = [
        'NTE comic panels and text embedded in textures or movies have no verified general subtitle binding.',
        'Phone chats, response options, combat barks and mixed character archives have partial classification; unknown voice status is excluded from unvoiced capture.',
        ('Publisher cinematic tables refresh with game data; unresolved movie text ownership and ambiguous events remain unavailable.'
         if publisher else 'Cinematic audio covers reviewed movie bindings and resolvable events only; new story sequences may need a reader/catalog update.'),
    ]
    missing = sum(row.get('voice_status') == 'unavailable' for row in records)
    if missing:
        warnings.append(f'{missing:,} authored voice references have missing media or unresolved playback; they are not silent dialogue.')
    unresolved_text = sum(bool(row.get('text_binding_unresolved')) for row in records)
    if unresolved_text:
        warnings.append(f'{unresolved_text:,} NTE text records contain unresolved protagonist text; their recordings remain unavailable.')
    unresolved_targets = sum(len(set(row.get('unresolved_text_locales', ())) -
                                 {row.get('source_locale')}) for row in records)
    if unresolved_targets:
        warnings.append(f'{unresolved_targets:,} NTE translation variants could not be resolved and were excluded.')
    return warnings


def build_records(cache: Path, cinema_bindings: list[dict] | None = None, *, source_locale=None, target_locales=(),
                  dialogue_graphs=False) -> list[dict]:
    localization = json.loads((cache / "localization.json").read_text(encoding="utf-8"))
    source_code = TEXT_LOCALES[source_locale] if source_locale else 'en'
    if not localization.get(source_code):
        raise ValueError('Install the selected official NTE text pack before preparing this language.')
    english = {(r["ns"], r["key"]): r["value"] for r in localization[source_code]}
    chinese = english if source_locale else {(r["ns"], r["key"]): r["value"] for r in localization['zh-CN']}
    voice_language = VOICE_LOCALES[source_locale] if source_locale else 'Chinese'
    media_root = 'HT/Content/WwiseAudio/Media/' + voice_language + '/'
    media = set(json.loads((cache / "media.json").read_text(encoding="utf-8")))
    events = {}
    cinema_events = {}
    event_inventory = cache / 'voice-events.json'
    authored_events = {name.lower() for name in json.loads(event_inventory.read_text(encoding='utf8'))} if event_inventory.is_file() else set()
    for path in (cache / "banks").glob("Play_Vo_*.bnk"):
        data = path.read_bytes()
        if len(data) >= 20 and data[:4] == b'BKHD' and struct.unpack_from('<I', data, 8)[0] != 154:
            raise PreparationFailure('unsupported_game_format',
                'This NTE update uses an unsupported Wwise bank version. Update the toolkit, then retry preparation; the previous index is retained.')
        authored_events.add(path.stem.lower())
        if len(data) < 20 or data[:4] != b"BKHD" or struct.unpack_from("<I", data, 16)[0] != wwise_hash(voice_language):
            continue
        event = path.stem
        if struct.unpack_from("<I", data, 12)[0] != wwise_hash(event):
            continue
        try:
            layers = read_bank_play_layers(path, allowed_versions=(154,), include_storage_type=True).get(wwise_hash(event), [])
        except (ValueError, IndexError, struct.error):
            continue
        variants = [(None, layers)]
        if not layers:
            try:
                variants = [(gender, read_bank_play_layers(path, allowed_versions=(154,),
                             include_storage_type=True,
                             switch_states={wwise_hash('Sex_Switch'): wwise_hash(gender)}).get(wwise_hash(event), []))
                            for gender in ['female', 'male']]
            except (ValueError, IndexError, struct.error):
                continue
            if not any(len(selected) == 1 for _, selected in variants):
                continue
        for gender, selected in variants:
            audio = None
            if len(selected) == 1:
                layer = selected[0]
                depot = f"{media_root}{layer['media_id']}.wem"
                if depot in media and math.isfinite(layer['gain_db']) and -60 <= layer['gain_db'] <= 24:
                    audio = {"depot": depot, "event": event, 'gain_db': layer['gain_db'],
                             **({'locale': 'zh-Hans' if source_locale == 'zh-Hant' else source_locale} if source_locale else {})}
            events.setdefault(event.lower(), []).append({'player_voice': gender, 'audio': audio})
            # Storage 0/1 media may load correctly without sharing the caption
            # clock. Keep those cinematic bindings unresolved until their
            # authored owner/clock contract is supported; do not filter layers.
            if audio and layer['delay_seconds'] == 0 and layer.get('storage_type') == 2:
                cinema_events.setdefault(event.lower(), []).append({'player_voice': gender,
                    'audio': audio})
    pairs_by_key = {}
    unique_namespace = {}
    for (ns, key), en in english.items():
        lower = key.lower()
        pairs_by_key.setdefault(lower, set()).add((en, chinese.get((ns, key), "")))
        if unique_namespace.setdefault(lower, ns) != ns:
            unique_namespace[lower] = None
    aliases_file = cache / 'dialogue-events.json'
    aliases = json.loads(aliases_file.read_text(encoding='utf8')) if aliases_file.is_file() else {}
    records = []
    for (ns, key), en in english.items():
        zh = chinese.get((ns, key), "")
        lower = key.lower()
        conventional = 'play_vo_' + lower
        declarations = aliases.get(lower)
        if declarations is None:
            event = conventional
        else:
            event = declarations[0] if len(declarations) == 1 else ''
        performances = events.get(event) if len(pairs_by_key[lower]) == 1 and (event == conventional or unique_namespace[lower]) else None
        kind, text_only = dialogue_presentation(ns, key)
        for performance in performances or [{'player_voice': None, 'audio': None}]:
            audio, gender = performance['audio'], performance['player_voice']
            status = 'voiced' if audio else ('unavailable' if event in authored_events or any(declarations or ())
                                             else 'unvoiced' if text_only else 'unknown')
            if display_text(en) and (source_locale or (contains_han(zh) and (audio or status == 'unvoiced'))):
                suffix = ':' + gender if gender else ''
                records.append({"text_id": f"nte:{ns}:{key}{suffix}", "english": en, "chinese": zh, "audio": audio,
                                **({'player_voice': gender} if gender else {}),
                                'voice_status': status, 'dialogue_kind': kind})
    sequences_file = cache / 'sequence-cues.json'
    if cinema_bindings or sequences_file.is_file():
        from .nte_cinematics import movie_records, subtitle_cues, timed_sequence_cues
        try:
            sequences = timed_sequence_cues(json.loads(sequences_file.read_text(encoding='utf8')),
                                             source_locale or 'zh-Hans') if sequences_file.is_file() else []
        except (KeyError, TypeError, ValueError):
            raise PreparationFailure('unsupported_game_format', 'NTE sequence timing or culture data changed. Update the toolkit and retry.') from None
        subtitles = json.loads((cache / 'cinema-subtitles.json').read_text(encoding='utf8')) if cinema_bindings else {}
        cinema_keys = {f"nte:{cue['namespace']}:{cue['key']}" for _, cues in sequences for cue in cues}
        for binding in cinema_bindings or ():
            if not subtitles.get(binding['subtitle']):
                continue
            try:
                cues = subtitle_cues(subtitles[binding['subtitle']])
            except ValueError:
                raise PreparationFailure('unsupported_game_format',
                    'This NTE update uses an unsupported movie subtitle layout. Update the toolkit, then retry preparation; the previous index is retained.') from None
            cinema_keys.update(f"nte:{binding['namespace']}:{cue['key']}" for cue in cues)
        movies = movie_records(cinema_bindings or (), subtitles, english, chinese, cinema_events,
                               require_han=source_locale is None, sequences=sequences)
        for row in movies:
            row.update(voice_status='voiced', dialogue_kind='cinematic')
        def caption_id(row):
            return row['text_id'].removesuffix(':' + row['player_voice']) if row.get('player_voice') else row['text_id']
        movie_ids = {r['text_id'] for r in movies}
        movie_roots = {caption_id(r) for r in movies}
        retained = []
        for row in records:
            identity = caption_id(row)
            if identity in cinema_keys:
                # A caption owned by a film must never play its whole mix.
                if row['text_id'] in movie_ids or not row.get('player_voice') and identity in movie_roots:
                    continue
                row.update(audio=None, voice_status='unavailable', dialogue_kind='cinematic')
            retained.append(row)
        records = retained + movies
    from .nte_text import localized_records
    locales = {source_locale, *target_locales} if source_locale else {'en', 'zh-Hans'}
    tables = {locale: {(r['ns'], r['key']): r['value'] for r in localization.get(TEXT_LOCALES[locale], [])}
              for locale in locales}
    records = localized_records(records, tables, source_locale)
    if source_locale:
        from .languages import audio_locale
        for row in records:
            row['audio_locale'] = audio_locale(source_locale)
            row['ocr_texts'] = {locale: anchors for locale, text in row['texts'].items()
                                if (anchors := ocr_anchors(text, locale))}
    if dialogue_graphs:
        from .nte_dialogue_graph import annotate, read_pairs
        try:
            annotate(records, read_pairs(cache/'dialogue-graphs.json', schema_usmap=(cache/'dialogue.usmap').read_bytes()))
        except (OSError, ValueError, TypeError, KeyError):
            raise PreparationFailure('unsupported_game_format',
                'The original NTE dialogue graph is incomplete or unsupported. The previous completed index is retained.') from None
    return records


def refresh_catalog(data_dir: Path, force=False) -> dict:
    from .game_catalogs import refresh_catalog as refresh
    from .nte_cinematics import catalog_rows
    return refresh('nte', data_dir, catalog_rows, force)


def index_install(install: Path, data_dir: Path, progress=lambda _message: None) -> dict:
    from .nte_cinematics import load_catalog, catalog_rows, movie_bindings, movie_namespaces, CATALOG_REVISION
    from .game_catalogs import read_snapshot
    snapshot = read_snapshot('nte', data_dir)
    bindings = movie_bindings(catalog_rows(snapshot['catalog']) if snapshot else load_catalog(data_dir / 'movie-catalog' / CATALOG_REVISION))
    stamp = fingerprint(install)
    executable = ensure_extractor(data_dir / "tools")
    # New movie bindings must invalidate extracted event caches even when the
    # game files themselves have not changed. Voice staleness remains physical.
    cache_id = hashlib.sha256(json.dumps([stamp, snapshot['digest'] if snapshot else CATALOG_REVISION,
                                        LANGUAGE_INDEX_VERSION]).encode()).hexdigest()
    cache = data_dir / "index-cache" / cache_id[:16]
    if (cache / "complete.json").is_file():
        records = json.loads((cache / "complete.json").read_text(encoding="utf-8"))
    else:
        progress("Reading installed NTE English and Chinese dialogue and exact Chinese voice events")
        with tempfile.TemporaryDirectory(prefix="nte-index-", dir=data_dir) as value:
            staging = Path(value)
            run_reader(install, executable, staging, "index", cinema_events=sorted({r['event'] for r in bindings}),
                       schema_cache=data_dir / 'schemas')
            if (staging / 'movie-tables.json').is_file():
                original = json.loads((staging / 'movie-tables.json').read_bytes())
                bindings = movie_bindings(catalog_rows(original), movie_namespaces(original, required=True))
            records = build_records(staging, bindings)
            if fingerprint(install) != stamp:
                raise PreparationFailure('game_files_changed', 'NTE files changed during preparation. Finish the game update and retry; the previous index is retained.')
            if not records:
                raise ValueError("NTE files contain no supported bilingual voices; finish the game download and retry")
            cache.mkdir(parents=True, exist_ok=True)
            staged_index = staging / 'complete.json'
            staged_index.write_text(json.dumps(records, ensure_ascii=False), encoding='utf8')
            staged_index.replace(cache / 'complete.json')
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed', 'NTE files changed during preparation. Finish the game update and retry; the previous index is retained.')
    if not records:
        raise ValueError('NTE dialogue cache is empty; retry preparation.')
    return {"format": 1, "install": str(install), "fingerprint": stamp, "records": records,
            "catalog_digest": snapshot['digest'] if snapshot else None,
            "catalog_revision": snapshot['revision'] if snapshot else CATALOG_REVISION,
            'coverage_warnings': coverage_warnings(records),
            "message": f"{len(records):,} official bilingual NTE lines; {sum(bool(row.get('audio')) for row in records):,} original Mandarin voices"}


def index_language(install: Path, data_dir: Path, source_locale: str, target_locales, progress=lambda _message: None) -> dict:
    from .languages import resolve_locale
    from .nte_cinematics import load_catalog, catalog_rows, movie_bindings, movie_namespaces, CATALOG_REVISION
    from .game_catalogs import read_snapshot
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported NTE study/audio locale')
    if install is None:
        from . import nte_publisher
        return nte_publisher.build_language(data_dir / 'tools', source_locale, target_locales, progress)
    snapshot = read_snapshot('nte', data_dir)
    bindings = movie_bindings(catalog_rows(snapshot['catalog']) if snapshot else load_catalog(data_dir / 'movie-catalog' / CATALOG_REVISION))
    targets = {target: resolve_locale(target, TEXT_LOCALES) for target in target_locales}
    selected = {source_locale, *(locale for locale in targets.values() if locale)}
    stamp = fingerprint(install)
    cache_id = hashlib.sha256(json.dumps([stamp, source_locale, sorted(selected),
        snapshot['digest'] if snapshot else CATALOG_REVISION, LANGUAGE_INDEX_VERSION]).encode()).hexdigest()[:16]
    cache = data_dir / 'language-cache' / cache_id
    tool = ensure_extractor(data_dir / 'tools')
    if (cache / 'complete.json').is_file():
        result = json.loads((cache / 'complete.json').read_text(encoding='utf8'))
    else:
        progress(f'Reading selected NTE {source_locale} text and original voice events')
        with tempfile.TemporaryDirectory(prefix='nte-language-', dir=data_dir) as value:
            staging = Path(value)
            run_reader(install, tool, staging, 'index', cinema_events=sorted({r['event'] for r in bindings}),
                       locales=[TEXT_LOCALES[locale] for locale in sorted(selected)], voice_language=VOICE_LOCALES[source_locale],
                       schema_cache=data_dir / 'schemas')
            if (staging / 'movie-tables.json').is_file():
                original = json.loads((staging / 'movie-tables.json').read_bytes())
                bindings = movie_bindings(catalog_rows(original), movie_namespaces(original, required=True))
            localization = json.loads((staging / 'localization.json').read_text(encoding='utf8'))
            available = {locale for locale in selected if TEXT_LOCALES[locale] in localization}
            rows = build_records(staging, bindings, source_locale=source_locale, target_locales=available - {source_locale})
            if fingerprint(install) != stamp:
                raise PreparationFailure('game_files_changed', 'NTE files changed during preparation. Finish the game update and retry; the previous index is retained.')
            if not rows:
                raise ValueError('NTE selected dialogue is incomplete; previous table retained.')
            result = {'records': rows, 'available': sorted(available)}
            cache.mkdir(parents=True, exist_ok=True)
            staged_index = staging / 'complete.json'
            staged_index.write_text(json.dumps(result, ensure_ascii=False), encoding='utf8')
            staged_index.replace(cache / 'complete.json')
    if fingerprint(install) != stamp:
        raise PreparationFailure('game_files_changed', 'NTE files changed during preparation. Finish the game update and retry; the previous index is retained.')
    rows = result['records']; mapped = sum(bool(row.get('audio')) for row in rows)
    missing = [target for target, locale in targets.items() if locale not in result['available']]
    return {'format': 2, 'game': 'nte', 'source_locale': source_locale, 'install': str(install),
        'fingerprint': stamp, 'records': rows, 'missing_translation_locales': missing,
        'coverage_warnings': coverage_warnings(rows),
        'message': f'{len(rows):,} official {source_locale} lines; {mapped:,} original voices' +
        (f'; official translations unavailable: {", ".join(missing)}' if missing else '') +
        ('; install the selected official voice pack' if not mapped else '')}


def _voice_language(audio):
    locale = audio.get('locale', 'zh-Hans')
    language = VOICE_LOCALES.get(locale)
    if language is None or not re.fullmatch(re.escape('HT/Content/WwiseAudio/Media/' + language + '/') + r'\d+\.wem', audio.get('depot', '')):
        raise ValueError('Invalid NTE original voice locale or reference')
    return language


def extract_voice(install: Path, audio: dict, executable: Path, destination: Path) -> bytes:
    language = _voice_language(audio)
    if install is None:
        from . import nte_publisher
        return nte_publisher.extract(executable.parent, audio)
    from .nte_toolchain import voice_executable
    executable = voice_executable(executable)
    options = {'voice_language': language} if audio.get('locale') else {}
    run_reader(install, executable, destination, "voice", audio["depot"], **options)
    data = (destination / "voice.wem").read_bytes()
    if data[:4] != b"RIFF":
        raise ValueError("NTE voice is not a supported original WEM")
    return data


def extract_voices(install: Path, audios: list[dict], executable: Path, destination: Path) -> list[bytes]:
    depots = [audio.get('depot', '') for audio in audios]
    languages = {_voice_language(audio) for audio in audios}
    if not 1 <= len(depots) <= 8 or len(languages) != 1:
        raise ValueError('NTE batches require one selected original voice language')
    if install is None:
        from . import nte_publisher
        return [nte_publisher.extract(executable.parent, audio) for audio in audios]
    from .nte_toolchain import voice_executable
    executable = voice_executable(executable)
    options = {'voice_language': next(iter(languages))} if any(audio.get('locale') for audio in audios) else {}
    run_reader(install, executable, destination, 'voices', depots=depots, **options)
    result = [(destination / f'{i}.wem').read_bytes() for i in range(len(depots))]
    if any(data[:4] != b'RIFF' for data in result):
        raise ValueError('NTE voice is not a supported original WEM')
    return result
