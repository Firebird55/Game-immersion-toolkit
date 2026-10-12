"""Readable transfer folders, with resumable work kept separately."""
import json
import re
import zipfile
from pathlib import Path

from .game_paths import GAME_NAMES


def work_folder(output):
    output = Path(output)
    work = output / '.toolkit-work'
    work.mkdir(parents=True, exist_ok=True)
    for name in ('cache',):
        old, target = output / name, work / name
        if old.is_dir() and not target.exists():
            old.rename(target)
    return work


def catalog_name(game):
    return f'{GAME_NAMES[game]} - Catalog.zip'


def voice_pack_name(game, number, total, identity):
    return f'{GAME_NAMES[game]} - Voices {number:02d} of {total:02d} - {identity[:8]}.zip'


def export_folder_name(game, revision):
    if not re.fullmatch('[a-f0-9]{64}', revision):
        raise ValueError('Invalid export revision')
    return f'{GAME_NAMES[game]} - Mobile Library - {revision[:12]}'


def latest_export(output, game):
    output = Path(output)
    pointer = json.loads((output / 'latest.json').read_text(encoding='utf8'))
    revision = pointer['revision']
    friendly = export_folder_name(game, revision)
    name = pointer.get('folder', friendly if (output / friendly).is_dir() else revision)
    folder = output / name
    if folder.resolve().parent != output.resolve():
        raise ValueError('Invalid export folder')
    catalog = folder / pointer.get('catalog', game + '.catalog.zip')
    if catalog.resolve().parent != folder.resolve():
        raise ValueError('Invalid catalog name')
    return folder, catalog


def organize_completed_export(output, game):
    """Move an old completed export without copying GBs or touching game files."""
    output = Path(output)
    work = work_folder(output)
    old_decoded = output / 'decoded'
    if old_decoded.is_dir() and not (work / 'decoded').exists():
        old_decoded.rename(work / 'decoded')
    folder, catalog = latest_export(output, game)
    with zipfile.ZipFile(catalog) as archive:
        manifest = json.loads(archive.read('manifest.json'))
    if manifest.get('game') != game:
        raise ValueError('Export belongs to another game')
    total = len(manifest['packs'])
    for number, pack in enumerate(manifest['packs'], 1):
        old = folder / pack['name']
        if old.resolve().parent != folder.resolve() or not re.fullmatch('[a-f0-9]{64}', pack['id']):
            raise ValueError('Invalid voice pack name')
        name = voice_pack_name(game, number, total, pack['id'])
        if old.is_file() and old.name != name:
            if old.resolve().parent != folder.resolve() or (folder / name).exists():
                raise ValueError('Conflicting export files')
            old.rename(folder / name)
    new_catalog = folder / catalog_name(game)
    if catalog != new_catalog:
        catalog.rename(new_catalog)
    destination = output / export_folder_name(game, manifest['revision'])
    if folder != destination:
        folder.rename(destination)
    pointer = output / 'latest.pending'
    pointer.write_text(json.dumps({'revision': manifest['revision'], 'folder': destination.name,
                                  'catalog': new_catalog.name, 'coverage': manifest['coverage']}), encoding='utf8')
    pointer.replace(output / 'latest.json')
    write_instructions(output, destination)
    return destination


def write_instructions(output, folder):
    (Path(output) / 'START HERE.txt').write_text(
        'Open the Mobile Library folder. Transfer only its ZIP files.\n'
        'Keep ZIPs zipped. On the phone, select the catalog and voice ZIPs together.\n'
        '.toolkit-work contains private resumable PC work; do not transfer it.\n'
        'latest.json is a private PC marker; it is not needed on the phone.\n', encoding='utf8')
    (Path(folder) / 'READ ME.txt').write_text(
        'Open https://firebird55.github.io/Game-immersion-toolkit/ on the receiving phone.\n'
        'Choose Receive screen and open the Catalog ZIP plus all matching Voices ZIPs.\n'
        'Keep ZIPs zipped. They may stay on a connected USB drive or in On My iPhone.\n'
        'After reopening, select the voice ZIPs again. No game files are uploaded.\n', encoding='utf8')
