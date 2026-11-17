"""Read-only diagnostics for explicitly authored recovery fixture databases."""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys


def sqlite_profiles(root):
    result = {}
    for path in sorted((root / 'profiles').rglob('*.db')):
        wal = path.with_name(path.name + '-wal')
        if wal.exists() and wal.stat().st_size:
            raise AssertionError('Authored SQLite evidence requires checkpointed fixture databases')
        # Immutable mode avoids creating WAL/shared-memory sidecars while
        # inspecting these already closed, checkpointed authored fixtures.
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as connection:
            schema = connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
            tables = {}
            for kind, name, _, _ in schema:
                if kind != 'table':
                    continue
                quoted = '"' + name.replace('"', '""') + '"'
                try:
                    rows = connection.execute('SELECT rowid,* FROM ' + quoted).fetchall()
                except sqlite3.OperationalError:
                    rows = connection.execute('SELECT * FROM ' + quoted).fetchall()
                raw = json.dumps(sorted(rows, key=repr), ensure_ascii=True, separators=(',', ':'),
                    default=lambda value: {'bytes_sha256': hashlib.sha256(value).hexdigest()}).encode()
                tables[name] = {'rows': len(rows), 'complete_rows_sha256': hashlib.sha256(raw).hexdigest()}
            result[path.relative_to(root).as_posix()] = {'schema': schema, 'tables': tables,
                'integrity': connection.execute('PRAGMA integrity_check').fetchall(),
                'header': path.read_bytes()[:100].hex(), 'database_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def application_profiles(value):
    """Preserve every app schema entry and row; only proven stat1 is metadata."""
    result = {}
    for path, database in value.items():
        if [list(row) for row in database['integrity']] != [['ok']]:
            raise AssertionError('Authored profile database integrity changed')
        schema = []
        for row in database['schema']:
            if row[1] == 'sqlite_stat1':
                if list(row) != ['table', 'sqlite_stat1', 'sqlite_stat1', 'CREATE TABLE sqlite_stat1(tbl,idx,stat)']:
                    raise AssertionError('Unexpected SQLite statistics schema')
            else:
                schema.append(list(row))
        result[path] = {'schema': schema,
            'tables': {name: rows for name, rows in database['tables'].items() if name != 'sqlite_stat1'}}
    return result


def write_evidence(root, before, damage):
    import _sqlite3
    metadata = {'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version,
        'sqlite_extension_sha256': hashlib.sha256(Path(_sqlite3.__file__).read_bytes()).hexdigest()}
    dll = Path(sys.base_prefix) / 'DLLs/sqlite3.dll'
    if dll.is_file():
        metadata['sqlite_dll_sha256'] = hashlib.sha256(dll.read_bytes()).hexdigest()
    with closing(sqlite3.connect(':memory:')) as connection:
        metadata['sqlite_source_id'] = connection.execute('SELECT sqlite_source_id()').fetchone()[0]
    after = sqlite_profiles(root)
    report = {'schema': 'authored-recovery-sqlite-evidence-v1', 'fixture': 'two-authored-profiles',
        'versions': metadata, 'damage': damage, 'before': before, 'after': after}
    output = Path('output/checks');output.mkdir(parents=True, exist_ok=True)
    (output / ('android-recovery-sqlite-' + damage + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    return {'versions': metadata, 'changed_databases': [name for name in before if before[name] != after[name]],
        'evidence': 'authored recovery SQLite metadata report'}
