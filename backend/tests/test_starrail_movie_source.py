"""Immutable, data-only movie descriptions with exact Git ownership and bounds."""
import hashlib
import json

import pytest

from backend import starrail_movie_metadata as metadata


def source_fixture(monkeypatch, documents, revision='1' * 40):
    bodies = {name: value.encode() if isinstance(value, str) else value for name, value in documents.items()}
    responses, trees = {}, []
    def tree(rows):
        raw = b''.join(row['mode'].lstrip('0').encode() + b' ' + row['path'].encode() + b'\0' + bytes.fromhex(row['sha'])
                       for row in sorted(rows, key=lambda row: row['path'] + ('/' if row['type'] == 'tree' else '')))
        digest = hashlib.sha1(f'tree {len(raw)}\0'.encode() + raw).hexdigest()
        payload = {'sha': digest, 'tree': rows, 'truncated': False}
        responses['git/trees/' + digest] = json.dumps(payload).encode()
        trees.append(payload)
        return digest
    leaf = tree([{'path': name, 'mode': '100644', 'type': 'blob', 'size': len(body),
                  'sha': hashlib.sha1(f'blob {len(body)}\0'.encode() + body).hexdigest()} for name, body in bodies.items()])
    folder = tree([{'path': 'usm', 'mode': '040000', 'type': 'tree', 'sha': leaf}])
    root = tree([{'path': 'pkg_version', 'mode': '040000', 'type': 'tree', 'sha': folder}])
    responses['commits/' + revision] = json.dumps({'sha': revision, 'commit': {'tree': {'sha': root}}}).encode()
    seen = []
    def download(url, *, limit):
        seen.append((url, limit))
        api = f'https://api.github.com/repos/{metadata.REPOSITORY}/'
        raw = f'https://raw.githubusercontent.com/{metadata.REPOSITORY}/{revision}/pkg_version/usm/'
        if url.startswith(api):
            body = responses[url.removeprefix(api)]
        else:
            assert url.startswith(raw)
            body = bodies[url.removeprefix(raw)]
        assert len(body) <= limit
        return body
    metadata._ROOTS.clear()
    monkeypatch.setattr(metadata, 'download', download)
    return bodies, responses, trees, seen


def test_new_descriptions_pin_commit_each_tree_blob_and_decoded_hash_then_replay_offline(tmp_path, monkeypatch):
    documents = {name: b'{}' for name in metadata.FILES}
    _, _, _, calls = source_fixture(monkeypatch, documents)
    catalog = metadata.load(tmp_path, '1' * 40)
    source = json.loads((tmp_path / 'starrail-movie-formats' / catalog.revision / 'source.json').read_bytes())
    assert source['repository'] == metadata.REPOSITORY and source['revision'] == catalog.revision
    assert len(source['trees']) == 3 and len(calls) == 7
    assert all(url.startswith(('https://api.github.com/repos/' + metadata.REPOSITORY + '/',
                              'https://raw.githubusercontent.com/' + metadata.REPOSITORY + '/')) for url, _ in calls)
    monkeypatch.setattr(metadata, 'download', lambda *_args, **_kwargs: pytest.fail('Pinned offline source requested network'))
    assert metadata.load(tmp_path, catalog.revision, catalog.digest).digest == catalog.digest
    assert metadata.load(tmp_path, catalog.revision).digest == catalog.digest


@pytest.mark.parametrize('changed', ['commit', 'tree', 'blob', 'truncated', 'size'])
def test_mismatched_source_cannot_publish_or_replace_a_previous_complete_generation(tmp_path, monkeypatch, changed):
    bodies, responses, trees, calls = source_fixture(monkeypatch, {name: b'{}' for name in metadata.FILES})
    old = tmp_path / '0' / 'retained'; old.parent.mkdir(); old.write_bytes(b'previous complete generation')
    if changed == 'commit':
        responses['commits/' + '1' * 40] = json.dumps({'sha': '2' * 40}).encode()
    elif changed == 'blob':
        bodies[metadata.FILES[0]] = b'[]'
    else:
        target = trees[-1] if changed == 'truncated' else trees[0]
        if changed == 'truncated':
            target['truncated'] = True
        elif changed == 'size':
            target['tree'][0]['size'] = metadata.SOURCE_LIMITS[metadata.FILES[0]] + 1
        else:
            target['tree'][0]['sha'] = 'e' * 40
        responses['git/trees/' + target['sha']] = json.dumps(target).encode()
    with pytest.raises(ValueError):
        metadata.load(tmp_path, '1' * 40)
    assert old.read_bytes() == b'previous complete generation'
    assert not (tmp_path / 'starrail-movie-formats' / ('1' * 40) / 'receipt.json').exists()
    if changed in {'commit', 'tree', 'truncated', 'size'}:
        assert not any('raw.githubusercontent' in url for url, _ in calls)


def test_tree_path_injection_and_duplicate_entries_fail_closed():
    row = {'path': '../outside', 'mode': '100644', 'type': 'blob', 'sha': 'a' * 40}
    with pytest.raises(ValueError):
        metadata._tree([row], 'b' * 40)
    row['path'] = 'safe'
    with pytest.raises(ValueError):
        metadata._tree([row, row], 'b' * 40)


def test_exact_legacy_record_digest_still_replays_without_new_provenance_requests(tmp_path, monkeypatch):
    revision = 'a' * 40
    root = tmp_path / 'starrail-movie-formats' / revision; root.mkdir(parents=True)
    receipt = {}
    for name in metadata.FILES:
        (root / name).write_bytes(b'{}')
        receipt[name] = hashlib.sha256(b'{}').hexdigest()
    (root / 'receipt.json').write_text(json.dumps(receipt))
    digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    monkeypatch.setattr(metadata, 'download', lambda *_args, **_kwargs: pytest.fail('Historical exact digest accessed network'))
    assert metadata.load(tmp_path, revision, digest).digest == digest
    with pytest.raises(ValueError):
        metadata.load(tmp_path, revision, 'b' * 64)
