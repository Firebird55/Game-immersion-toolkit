import hashlib
import io
import json
import tarfile
from urllib.error import HTTPError

import pytest

from backend import dialogue_catalog, genshin_archive_mirror as mirror, genshin_publisher as publisher
from backend.preparation_errors import PreparationFailure


def limited(url):
    return HTTPError(url, 429, 'Primary rate limit', {}, None)


def test_primary_outage_uses_matching_mirror_title_and_still_checks_independent_regions(tmp_path, monkeypatch):
    build = {'version': '8.1.0', 'channel': 'genshin-global'}
    markers = ('10', '20', '30')
    def offline(*args):
        raise limited('primary')
    monkeypatch.setattr(publisher, 'matching_release_commit', offline)
    cn = {'version': '8.1.0', 'channel': 'genshin-cn', 'digest': 'a'}
    monkeypatch.setattr(publisher.sophon, 'release', lambda channel: cn)
    monkeypatch.setattr(publisher, '_narrative_payload', lambda _, selected: (markers, selected.get('digest', 'a')))
    titles = {'CNRELWin8.1.0_R10_S20_D30': 'c' * 40, 'CNRELWin8.1.0_R10_S20_D99': 'e' * 40}
    monkeypatch.setattr(mirror, 'release_titles', lambda: titles)
    assert publisher._catalog(tmp_path, build, 'global') == 'c' * 40
    cn['digest'] = 'b'
    with pytest.raises(PreparationFailure, match='Global'):
        publisher._catalog(tmp_path, build, 'global')
    titles['OSRELWin8.1.0_R10_S20_D30'] = 'a' * 40
    assert publisher._catalog(tmp_path, build, 'global') == 'a' * 40
    titles.clear()
    with pytest.raises(PreparationFailure, match='unique'):
        publisher._catalog(tmp_path, cn, 'cn')


@pytest.mark.parametrize('directory,extension', [('BinOutput/Talk', '.json'), ('BinOutput/Voice', '.json'),
                         ('BinOutput/Avatar', '.json'), ('Readable/EN', '.txt'), ('Subtitle/CHS', '.srt')])
def test_current_release_fixed_files_and_directories_fall_back_once_and_reopen_offline(tmp_path, monkeypatch, directory, extension):
    cat = publisher.ReleaseCatalog('genshin', tmp_path, revision='b' * 40)
    paths = []
    def download(url, **kwargs):
        paths.append(url)
        if url.startswith('https://gitlab.com/'):
            raise limited(url)
        assert f'/{"b" * 40}/' in url
        return json.dumps({'1': 'A written message.'}).encode()
    monkeypatch.setattr(dialogue_catalog, 'download', download)
    relative = 'TextMap/TextMapEN.json'
    assert cat.file(relative) == {'1': 'A written message.'}
    assert len(paths) == 2
    def fetch(catalog, *, trees):
        assert catalog is cat and trees == (directory,)
        content = b'{"id": 1}' if extension == '.json' else b'Written'
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:gz') as archive:
            item = tarfile.TarInfo('Fixed/' + directory + '/sample' + extension)
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
        blob = output.getvalue()
        suffix = '.tar.gz' if extension == '.json' else '-text.tar.gz'
        path = cat.root / (directory.replace('/', '-') + suffix)
        path.write_bytes(blob)
        path.with_name(path.name + '.sha256').write_text(hashlib.sha256(blob).hexdigest())
    monkeypatch.setattr(mirror, 'fetch_trees', fetch)
    def read():
        if extension == '.json':
            return list(cat.directory_json(directory))
        return list(cat.directory_text(directory, suffix=extension))
    assert read() == ([{'id': 1}] if extension == '.json' else [('sample' + extension, 'Written')])
    monkeypatch.setattr(dialogue_catalog, 'download', lambda *a, **k: pytest.fail('Valid cached release went online'))
    assert cat.file(relative) and read()


def test_mirror_accepts_only_reviewed_data_directory_families(tmp_path):
    catalog = publisher.ReleaseCatalog('genshin', tmp_path, revision='c' * 40)
    for tree in ('BinOutput/Other', 'Readable/../EN', 'Subtitle/CUSTOM', 'BinOutput/Talk/file.json'):
        with pytest.raises(ValueError, match='directory'):
            mirror.fetch_trees(catalog, trees=(tree,))
