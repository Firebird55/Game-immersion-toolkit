import json
from pathlib import Path
import zipfile

from backend.mobile_library import export_library
from backend.mobile_export_layout import latest_export, catalog_name, organize_completed_export, work_folder


def test_clean_transfer_names_keep_work_private_and_preserve_unvoiced_text(tmp_path):
    record = {'textId': 'fixture', 'english': 'A quiet sentence.', 'chinese': '安静的句子。',
              'sourceVoice': None, 'channels': ['dialogue']}
    cache = tmp_path / 'cache'; cache.mkdir(); (cache / 'resume-marker').write_text('keep')
    result = export_library('zzz', [record], tmp_path, include_audio=False)
    folder, catalog = latest_export(tmp_path, 'zzz')
    assert folder == Path(result['folder'])
    assert folder.name.startswith('Zenless Zone Zero - Mobile Library - ')
    assert catalog.name == 'Zenless Zone Zero - Catalog.zip'
    assert (work_folder(tmp_path) / 'cache/resume-marker').read_text() == 'keep'
    assert set(p.name for p in folder.iterdir()) == {catalog.name, 'READ ME.txt'}
    assert result['coverage']['dialogue'] == 1 and result['coverage']['mappedVoices'] == 0


def test_organize_existing_export_reuses_zip_bytes_and_updates_private_pointer(tmp_path):
    revision = 'a' * 64
    folder = tmp_path / revision; folder.mkdir()
    manifest = {'game': 'zzz', 'revision': revision, 'packs': [], 'coverage': {'dialogue': 0}}
    with zipfile.ZipFile(folder / 'zzz.catalog.zip', 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
    original = (folder / 'zzz.catalog.zip').read_bytes()
    (tmp_path / 'latest.json').write_text(json.dumps({'revision': revision, 'catalog': 'zzz.catalog.zip'}))
    organized = organize_completed_export(tmp_path, 'zzz')
    assert (organized / catalog_name('zzz')).read_bytes() == original
    assert latest_export(tmp_path, 'zzz')[0] == organized
    assert organize_completed_export(tmp_path, 'zzz') == organized


def test_copying_entire_selected_folder_excludes_cache_and_keeps_resume(tmp_path):
    selected = tmp_path / 'transfer'
    output = selected / 'zzz'
    source = tmp_path / 'fixture.mp3'
    source.write_bytes(b'ID3' + bytes(512))
    record = {'textId': 'voiced', 'english': 'A quiet sentence.', 'chinese': '安静的句子。',
              'sourceVoice': 'b' * 64, 'channels': ['dialogue']}
    calls = []
    def decode(*_):
        calls.append(1)
        return source
    first = export_library('zzz', [record], output, voice=decode)
    workspace = work_folder(output)
    assert not workspace.is_relative_to(selected)
    assert workspace.anchor == output.anchor
    assert len(list((workspace / 'cache').glob('*.mp3'))) == 1
    assert not list(selected.rglob('*.mp3'))
    assert len(list(selected.rglob('*.zip'))) == 2
    instructions = (output / 'START HERE.txt').read_text(encoding='utf8')
    assert Path(first['folder']).name in instructions and '.pending' not in instructions
    assert export_library('zzz', [record], output, voice=decode)['folder'] == first['folder']
    assert len(calls) == 1


def test_legacy_workspace_moves_outside_transfer_root_without_changing_library(tmp_path):
    output = tmp_path / 'transfer/zzz'
    old = output / '.toolkit-work/cache'
    old.mkdir(parents=True)
    (old / 'clip.mp3').write_bytes(b'private resumable fixture')
    completed = output / 'completed-library'
    completed.mkdir()
    (completed / 'catalog.zip').write_bytes(b'completed fixture')
    workspace = work_folder(output)
    assert (workspace / 'cache/clip.mp3').read_bytes() == b'private resumable fixture'
    assert (completed / 'catalog.zip').read_bytes() == b'completed fixture'
    assert not (output / '.toolkit-work').exists()
    assert work_folder(output) == workspace
    assert work_folder(tmp_path / 'other-transfer/zzz') != workspace
