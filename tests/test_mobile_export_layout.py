import json
from pathlib import Path
import zipfile

from backend.mobile_library import export_library
from backend.mobile_export_layout import latest_export, catalog_name, organize_completed_export


def test_clean_transfer_names_keep_work_private_and_preserve_unvoiced_text(tmp_path):
    record = {'textId': 'fixture', 'english': 'A quiet sentence.', 'chinese': '安静的句子。',
              'sourceVoice': None, 'channels': ['dialogue']}
    cache = tmp_path / 'cache'; cache.mkdir(); (cache / 'resume-marker').write_text('keep')
    result = export_library('zzz', [record], tmp_path, include_audio=False)
    folder, catalog = latest_export(tmp_path, 'zzz')
    assert folder == Path(result['folder'])
    assert folder.name.startswith('Zenless Zone Zero - Mobile Library - ')
    assert catalog.name == 'Zenless Zone Zero - Catalog.zip'
    assert (tmp_path / '.toolkit-work/cache/resume-marker').read_text() == 'keep'
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
