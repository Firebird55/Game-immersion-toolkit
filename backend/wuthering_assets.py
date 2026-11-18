"""Read selected Wuthering Waves text and authored original voice sources.

The PlotAudio FlatBuffer fields and filename rules follow the game's shipped
Core/Define/Config/PlotAudio.js and Game/Module/Plot/PlotAudioModel.js. No event
hashes, filename guesses, audio recordings, or game modifications are used.
"""
from __future__ import annotations

import hashlib
import os
from bisect import bisect_left
import json
import re
import struct
import subprocess
import tempfile
import urllib.request
from functools import lru_cache
from pathlib import Path

from .text_display import display_text
from .preparation_errors import PreparationFailure
from .wuthering_locales import SUPPORTED_LOCALES, VOICE_LOCALES, TEXT_LOCALES
from .wuthering_tables import (
    EXTERNAL_ROOT, FLOATING_SUBTITLES, NARRATIVE_TABLES,
    _field, _string, _boolean, _rows, _text_table, _narrative_refs,
    build_records, build_language_records,
)

PUBLIC_METADATA_URL = "https://yarik0chka.github.io/wuwa-keys/keys.json"
LANGUAGE_INDEX_VERSION = 13
FILM_CONTEXT_SECONDS = 360
COVERAGE_WARNINGS = [
    'Story-flow text, choices, messages, movie captions and readable records are indexed; presentation-specific OCR coverage is incomplete.',
    'Some film audio replays the complete scene, labeled as context. Other films still need verified audio bindings.',
    'Shared-song audio uses its original sung language. Translated lyrics remain text with unavailable audio when that study language has no matching vocal.',
    'Combat and ambient audio events, embedded movie audio and dynamic voice filenames still lack complete per-line bindings.',
    'Floating 2D/3D caption text is indexed. Entity-only bubbles, legacy numeric subtitles, songs and event-specific text still have gaps.',
]


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def ensure_extractor(directory: Path, decoder: Path | None) -> Path:
    # Both games use the same owned, bounded CUE4Parse helper. The packaged
    # path resolves app-local runtime resources without an SDK or downloader.
    from .nte_assets import ensure_extractor as ensure_unreal_reader
    return ensure_unreal_reader(directory)


def _official_archive(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    if any(part.startswith("~") for part in relative.parts):
        return False
    if path.name.startswith("pakchunk"):
        return True
    # Optional in-game cinematic downloads use Video_* names rather than
    # pakchunk*. The CLI scans them too; permit only the observed official
    # location and a filename whose cinematic ID matches its parent folder.
    match = re.fullmatch(r"Video/(hd|sd|uhd)/Paks/(\d+_\d+)/Video_(\d+_\d+)-(HD|SD|UHD)-WindowsNoEditor\.pak", relative.as_posix())
    return bool(match and match[2] == match[3] and match[1].upper() == match[4])


def archive_sources(install: Path) -> list[Path]:
    roots = [install / "Client/Content/Paks", install / "Client/Saved/Resources"]
    return sorted({path for root in roots if root.is_dir() for path in root.rglob("*.pak")
                   if _official_archive(root, path)}, key=str)


def fingerprint(install: Path) -> str:
    values = [f"{p.relative_to(install).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in archive_sources(install)]
    return hashlib.sha256("|".join(values).encode()).hexdigest()


def publisher_fingerprint(tools: Path) -> str:
    from . import wuthering_release
    return wuthering_release.fingerprint(tools)


def publisher_snapshot_available(tools: Path, stamp: str) -> bool:
    from . import wuthering_release
    return wuthering_release.snapshot_available(tools, stamp)


@lru_cache(maxsize=2)
def _archive_metadata(install: Path, stamp: str) -> tuple[str, ...]:
    # Public archive metadata is held in memory, never written to source,
    # manifests, files, or logs. Select only installed-version entries to stay
    # below Windows' command-line length limit.
    from Crypto.Cipher import AES
    payload = json.loads(_download(PUBLIC_METADATA_URL))
    candidates = list(dict.fromkeys(re.findall(r"0x[0-9a-fA-F]{64}", json.dumps(payload))))
    selected = set()
    for pak in archive_sources(install):
        with pak.open("rb") as stream:
            size = pak.stat().st_size
            if size < 64:
                raise ValueError("Game archive is incomplete; wait for the download to finish")
            # Empty official patch archives can be smaller than our footer
            # probe. Read the available tail and validate its actual structure.
            stream.seek(-min(512, size), 2)
            footer = stream.read()
            magic = footer.rfind(struct.pack("<I", 0x5A6F12E1))
            if magic < 17:
                raise ValueError("Installed game archive format is unsupported or incomplete")
            if not footer[magic - 1]:
                continue
            offset, length = struct.unpack_from("<QQ", footer, magic + 8)
            if length < 16 or offset + length > pak.stat().st_size:
                raise ValueError("Game archive index is incomplete")
            stream.seek(offset)
            sample = stream.read(min(length, 256))
            sample = sample[:len(sample) // 16 * 16]
        found = False
        for value in candidates:
            plain = AES.new(bytes.fromhex(value[2:]), AES.MODE_ECB).decrypt(sample)
            size = struct.unpack_from("<i", plain)[0]
            if 1 < size < min(200, len(plain) - 4) and plain[4:4 + size].startswith(b"../") and plain[3 + size] == 0:
                selected.add(value)
                found = True
                break
        if not found:
            raise ValueError("Installed archive version needs updated public extraction metadata")
    if not selected:
        raise ValueError("No supported installed Wuthering Waves archives were found")
    return tuple(sorted(selected))


def _reader_command(install, executable, destination, mode, layout):
    if layout.mode == 'bundle':
        from .nte_toolchain import command
        invocation, environment, working = command(install, destination, mode, layout=layout)
        if str(executable) != invocation[0]:
            raise ValueError('The selected archive reader differs from the bundled executable')
        return invocation, environment, working
    from .nte_assets import dotnet_sdk
    sdk = dotnet_sdk()
    if sdk is None or not executable.is_file():
        raise ValueError('Prepare Unreal archive tools in Setup before indexing')
    working = executable.parent / 'upstream'
    return [str(sdk), str(executable), mode, str(install), str(working), str(destination)], None, working


def _validate_filter(value: str, listing: bool) -> str:
    if listing and value == 'WwiseExternalSource/':
        return EXTERNAL_ROOT
    if not isinstance(value, str) or len(value) > 512 or '..' in value or not re.fullmatch(r'[A-Za-z0-9_./-]+', value):
        raise ValueError('Unsupported Unreal archive selection')
    if value.startswith(EXTERNAL_ROOT):
        clip = value[len(EXTERNAL_ROOT):]
        if len(clip) > 3 and '/' not in clip and re.match(r'(en|zh|ja|ko)_', clip):
            return value
    if not listing:
        if value in {'ConfigDB/' + name for name in ('db_plot_audio.db', *NARRATIVE_TABLES)}:
            return 'Client/Content/Aki/' + value
        if value in {'ConfigDB/' + locale + '/lang_multi_text' for locale in TEXT_LOCALES.values()}:
            return 'Client/Content/Aki/' + value
    raise ValueError('Unsupported Unreal archive selection')


def run_extractor(install: Path, executable: Path, destination: Path | None, filter_text: str) -> list[str]:
    from .runtime_bundle import discover_layout
    from .prebuilt_readers import _no_links
    layout = discover_layout()
    listing = destination is None
    # Resolve the real bundled capability before creating output or obtaining
    # private metadata. An unrelated installed helper is not sufficient.
    if layout.mode == 'bundle':
        from .nte_toolchain import resolve
        resolve(layout=layout)
    prefix = _validate_filter(filter_text, listing)
    install, executable = Path(install).resolve(), Path(executable).resolve()
    for root in (install / "Client/Content/Paks", install / "Client/Saved/Resources"):
        if root.is_dir() and any(not _official_archive(root, path) for path in root.rglob("*.pak")):
            raise ValueError("Wuthering Waves indexing requires official archives; unsupported mod archives were found")
    layout.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='unreal-read-', dir=layout.work_root) as temporary:
        output = Path(temporary) if listing else Path(destination).resolve()
        _no_links(output)
        if output == install or output.is_relative_to(install) or install.is_relative_to(output):
            raise ValueError('Reader outputs must stay outside the game installation')
        invocation, environment, working = _reader_command(install, executable, output,
            'wuwa-list' if listing else 'wuwa-extract', layout)
        metadata = _archive_metadata(install, fingerprint(install))
        if not 1 <= len(metadata) <= 512 or any(not re.fullmatch(r'0x[0-9a-fA-F]{64}', key) for key in metadata):
            raise ValueError('Installed archive version needs updated public extraction metadata')
        try:
            result = subprocess.run(invocation, input=json.dumps({'archive_metadata': metadata, 'filter': filter_text}).encode(),
                capture_output=True, timeout=600, cwd=working, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError("Wuthering Waves extractor could not complete") from None
        if result.returncode:
            raise RuntimeError("Wuthering Waves extraction failed; check the installed archives")
        manifest = output / 'files.json'
        _no_links(manifest)
        if not manifest.is_file() or manifest.stat().st_size > 256 * 1024 * 1024:
            raise ValueError('Unreal archive reader output is incomplete')
        files = json.loads(manifest.read_text(encoding='utf-8-sig'))
        if not isinstance(files, list) or len(files) > (2_000_000 if listing else 256) or any(
            not isinstance(name, str) or not name.casefold().startswith(prefix.casefold()) or
            (prefix.lower().endswith(('.wem', '.db')) and name.casefold() != prefix.casefold()) or
            (prefix.startswith(EXTERNAL_ROOT) and '/' in name[len(EXTERNAL_ROOT):]) or
            '\\' in name or ':' in name or any(part in {'', '.', '..'} for part in name.split('/')) or
            not name.lower().endswith('.wem' if prefix.startswith(EXTERNAL_ROOT) else '.db') for name in files):
            raise ValueError('Unreal archive reader returned an unexpected selection')
        return files


def _prepare_text_tables(install, executable, cache, locales, progress):
    db_root = cache / 'Client/Content/Aki/ConfigDB'
    for locale in sorted(locales):
        directory = db_root / TEXT_LOCALES[locale]
        path = directory / 'lang_multi_text.db'
        needs_read = not path.is_file()
        if not needs_read:
            columns = {row[1] for row in _rows(path, 'PRAGMA table_info(MultiText)')}
            needs_read = ('RedirectDbIndex' in columns and not (directory / 'lang_multi_text_1sthalf.db').is_file()
                          and bool(_rows(path, 'SELECT 1 FROM MultiText WHERE RedirectDbIndex > 0 LIMIT 1')))
        if needs_read:
            progress('Reading selected Wuthering localization tables')
            # The bounded locale prefix selects the base and authored shard.
            run_extractor(install, executable, cache, 'ConfigDB/' + TEXT_LOCALES[locale] + '/lang_multi_text')
    for relative in ('db_plot_audio.db', *NARRATIVE_TABLES):
        if not (db_root / relative).is_file():
            progress('Reading installed Wuthering narrative metadata')
            run_extractor(install, executable, cache, 'ConfigDB/' + relative)
        if relative != FLOATING_SUBTITLES and not (db_root / relative).is_file():
            raise PreparationFailure('unsupported_format', 'Required Wuthering narrative tables were not found; update the toolkit or verify game files.')


def index_install(install: Path, data_dir: Path, progress=lambda _message: None) -> dict:
    from .media_tools import vgmstream_executable
    stamp = fingerprint(install)
    decoder = vgmstream_executable(data_dir.parent.parent)
    executable = ensure_extractor(data_dir / "tools", decoder)
    cache = data_dir / "index-cache" / stamp[:16]
    _prepare_text_tables(install, executable, cache, {'en', 'zh-Hans'}, progress)
    complete = cache / "complete.json"
    if not complete.is_file():
        progress("Checking exact Mandarin voice paths")
        files = run_extractor(install, executable, None, "WwiseExternalSource/")
        complete.parent.mkdir(parents=True, exist_ok=True)
        complete.write_text(json.dumps(files), encoding="utf-8")
    files = json.loads(complete.read_text(encoding="utf-8"))
    records = build_records(cache / "Client/Content/Aki/ConfigDB", files)
    if not records or fingerprint(install) != stamp:
        raise ValueError("Game files are incomplete or changed while indexing; retry after the download finishes")
    mapped = sum(bool(record["audio"]) for record in records)
    return {"format": 1, "install": str(install), "fingerprint": stamp, "records": records,
        'coverage_warnings': COVERAGE_WARNINGS,
        "message": f"{len(records):,} bilingual pairs; {mapped:,} Mandarin voices" if mapped else
                   f"{len(records):,} dialogue pairs indexed; download the Chinese voice pack in Wuthering Waves"}


def index_language(install: Path | None, data_dir: Path, source_locale: str, target_locales, progress=lambda _message: None) -> dict:
    from .languages import resolve_locale
    from .media_tools import vgmstream_executable
    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError('Unsupported Wuthering study/audio locale')
    if install is None:
        from . import wuthering_release
        return wuthering_release.build_language(data_dir / 'tools', source_locale, target_locales, progress,
                                                decoder=vgmstream_executable(data_dir.parent.parent))
    stamp = fingerprint(install)
    executable = ensure_extractor(data_dir / 'tools', vgmstream_executable(data_dir.parent.parent))
    cache = data_dir / 'index-cache' / stamp[:16]
    cache.mkdir(parents=True, exist_ok=True)
    targets = {value: resolve_locale(value, TEXT_LOCALES) for value in target_locales}
    requested = {source_locale, *(locale for locale in targets.values() if locale)}
    _prepare_text_tables(install, executable, cache, requested, progress)
    for target, locale in list(targets.items()):
        if locale and not (cache / 'Client/Content/Aki/ConfigDB' / TEXT_LOCALES[locale] / 'lang_multi_text.db').is_file():
            targets[target] = None
    inventory = cache / 'complete.json'
    if not inventory.is_file():
        progress('Checking installed original voice paths')
        files = run_extractor(install, executable, None, 'WwiseExternalSource/')
        pending = inventory.with_suffix('.pending'); pending.write_text(json.dumps(files), encoding='utf8'); pending.replace(inventory)
    files = json.loads(inventory.read_text(encoding='utf8'))
    records = build_language_records(cache / 'Client/Content/Aki/ConfigDB', files, source_locale,
                                    {locale for locale in targets.values() if locale})
    if not records or fingerprint(install) != stamp:
        raise ValueError('Wuthering files changed or dialogue is incomplete; previous table retained.')
    mapped = sum(bool(row['audio']) for row in records)
    available = {locale for row in records for locale in row['texts']}
    missing = [target for target, locale in targets.items() if locale not in available]
    return {'format': 2, 'game': 'wuwa', 'install': str(install), 'fingerprint': stamp,
        'source_locale': source_locale, 'records': records, 'missing_translation_locales': missing,
        'coverage_warnings': COVERAGE_WARNINGS,
        'message': f'{len(records):,} official {source_locale} lines; {mapped:,} original voices' +
        (f'; {len(records) - mapped:,} entries without a verified voice binding' if mapped < len(records) else '') +
        (f'; official translations unavailable: {", ".join(missing)}' if missing else '') +
        ('; check the selected voice pack through the game launcher' if not mapped else '')}


def _validate_voice(audio):
    depot = audio.get('depot', '')
    code = VOICE_LOCALES.get(audio.get('locale', 'zh-Hans'), (None,))[0]
    if code is None or not isinstance(depot, str):
        raise ValueError('Invalid original voice locale or reference')
    media = re.fullmatch(r'Client/Content/Aki/WwiseAudio_Generated/Media/' + code + r'/([1-9][0-9]{0,9})\.wem', depot)
    if audio.get('music_context') is True:
        media = re.fullmatch(r'Client/Content/Aki/WwiseAudio_Generated/Media/([1-9][0-9]{0,9})\.wem', depot)
        if audio.get('source_clock') != 'play_position' or audio.get('scene_context') is not True:
            raise ValueError('Invalid original song source clock')
    if audio.get('publisher') and media and int(media[1]) <= 0xffffffff:
        if audio.get('scene_context') is True:
            frames, channels = audio.get('source_frames'), audio.get('source_channels')
            from .wuthering_cinematics import STANDARD_SURROUND_MASK, standard_surround_mix
            standard_surround = (channels == 6 and audio.get('music_context') is not True
                and type(audio.get('source_channel_mask')) is int
                and audio['source_channel_mask'] == STANDARD_SURROUND_MASK
                and audio.get('channel_mix') == standard_surround_mix()
                and all(type(gain) in (int, float) for pair in audio['channel_mix'] for gain in pair))
            ordinary = (channels in (1, 2) and 'source_channel_mask' not in audio and 'channel_mix' not in audio)
            scene, event = audio.get('scene'), audio.get('event')
            valid_scene = (isinstance(scene, str) and (
                0 < len(scene) <= 512 and scene.isprintable() and bool(scene.strip())
                if audio.get('music_context') is True else
                bool(re.fullmatch(r'[A-Za-z0-9_]{1,128}', scene))))
            maximum_seconds = 300 if audio.get('music_context') is True else FILM_CONTEXT_SECONDS
            if (type(frames) is int and 0 < frames <= 48000 * maximum_seconds
                    and type(channels) is int and (ordinary or standard_surround)
                    and valid_scene
                    and isinstance(event, str) and re.fullmatch(r'[A-Za-z0-9_]{1,256}', event)
                    and 'start_ms' not in audio and 'end_ms' not in audio
                    and 'playback_scope' not in audio):
                return depot
            raise ValueError('Invalid original scene context reference')
        start, end = audio.get('start_ms'), audio.get('end_ms')
        if type(start) is int and type(end) is int and 0 <= start < end <= 300000:
            return depot
    if not depot.startswith(EXTERNAL_ROOT + code + '_') or not depot.endswith('.wem') or '..' in depot or ':' in depot:
        raise ValueError('Invalid original voice locale or reference')
    return depot


def decode_voice_source(data, audio, wav, decoder, directory):
    """Preserve exact scene PCM, or explicitly rebase a bounded source window."""
    import wave
    _validate_voice(audio)
    if decoder is None:
        raise ValueError('Prepare the original voice decoder in Setup')
    if 'start_ms' in audio or 'end_ms' in audio:
        from .wuthering_cinematics import decode_window
        result = decode_window(data, decoder, directory, audio.get('start_ms'), audio.get('end_ms'))
        if result is None:
            raise ValueError('The original voice window is incomplete or unsupported')
        with wave.open(str(wav), 'wb') as output:
            output.setparams((result.channels, 2, 48000, 0, 'NONE', 'not compressed'))
            output.writeframes(result.pcm)
        return result.start_ms
    source = directory / 'source.wem'
    if audio.get('scene_context') is True and audio['source_channels'] == 6:
        from .wuthering_cinematics import source_info
        shape = source_info(data, decoder, directory, film_context=True)
        if shape != (6, audio['source_frames'], audio['source_channel_mask']):
            raise ValueError('The original surround scene does not match its verified source')
    source.write_bytes(data)
    subprocess.run([str(decoder), '-i', '-o', str(wav), str(source)], check=True,
                   capture_output=True, timeout=90,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if audio.get('scene_context') is True:
        frames, channels = audio['source_frames'], audio['source_channels']
        with wave.open(str(wav)) as output:
            if (output.getframerate() != 48000 or output.getnchannels() != channels
                    or output.getsampwidth() != 2 or output.getcomptype() != 'NONE'
                    or output.getnframes() != frames or wav.stat().st_size != 44 + frames * channels * 2
                    or len(output.readframes(frames)) != frames * channels * 2):
                raise ValueError('The original scene context does not match its verified source')
    return None


def extract_voice(install: Path | None, audio: dict, executable: Path, destination: Path) -> bytes:
    depot = _validate_voice(audio)
    if install is None:
        from . import wuthering_release
        return wuthering_release.extract(executable.parent, audio, audio['locale'])
    from .nte_toolchain import voice_executable
    executable = voice_executable(executable)
    run_extractor(install, executable, destination, depot)
    path = (destination / depot).resolve()
    if not path.is_relative_to(destination.resolve()) or not path.is_file():
        raise FileNotFoundError("The selected original clip is missing from the installed voice pack")
    return path.read_bytes()


@lru_cache(maxsize=2)
def _voice_inventory(path: Path, size: int, modified: int) -> tuple[str, ...]:
    values = json.loads(path.read_text(encoding='utf8'))
    return tuple(sorted(p.casefold() for p in values if p.startswith(EXTERNAL_ROOT) and p.endswith('.wem')))


def extract_voices(install: Path | None, audios: list[dict], executable: Path, destination: Path) -> list[bytes]:
    if not audios:
        return []
    depots = [_validate_voice(audio) for audio in audios]
    if len({VOICE_LOCALES[audio.get('locale', 'zh-Hans')][0] for audio in audios}) != 1:
        raise ValueError('Original voice batch crosses study/audio locales')
    if install is None:
        from . import wuthering_release
        return [wuthering_release.extract(executable.parent, audio, audio['locale']) for audio in audios]
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    data = layout.data_root / 'wuwa' if layout.mode == 'bundle' else Path(executable).parent.parent
    from .nte_toolchain import voice_executable
    executable = voice_executable(executable)
    inventory_path = data / 'index-cache' / fingerprint(install)[:16] / 'complete.json'
    try:
        stat = inventory_path.stat()
        inventory = _voice_inventory(inventory_path, stat.st_size, stat.st_mtime_ns)
    except (OSError, ValueError, TypeError):
        inventory = ()
    locations = {}
    def extract(group, number):
        # The owned reader supports bounded prefixes. Use a shared prefix only
        # when the indexed inventory proves it selects exactly requested WEMs.
        prefix = os.path.commonprefix(group)
        low = bisect_left(inventory, prefix.casefold())
        high = bisect_left(inventory, prefix.casefold() + '\uffff')
        wanted = {p.casefold() for p in group}
        bounded = inventory and len(prefix) > len(EXTERNAL_ROOT + 'zh_') and set(inventory[low:high]) == wanted
        if len(group) > 256 or len(group) > 1 and not bounded:
            middle = len(group) // 2
            extract(group[:middle], number + 'a'); extract(group[middle:], number + 'b')
            return
        directory = destination / number; directory.mkdir(parents=True, exist_ok=True)
        run_extractor(install, executable, directory, prefix if bounded else group[0])
        for depot in group:
            path = (directory / depot).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file():
                raise FileNotFoundError('The selected original clip is missing from the installed voice pack')
            locations[depot] = path
    extract(sorted(set(depots)), 'sources')
    return [locations[depot].read_bytes() for depot in depots]
