"""Explicit legacy import is bounded, atomic, account-scoped and replay safe."""
from contextlib import closing
import json
import shutil
import sqlite3

import pytest

from backend.browser_history_migration import FORMAT, parse_backup, summary
from backend.storage import TranscriptStore
from backend.tests.test_android_account_http import account_host, headers, register
from backend.tests.test_android_host import request


def row(**changes):
    return {'source': 'mobile-ocr', 'id': 'authored_history_id', 'game': 'endfield',
        'createdAt': 1794783739000, 'favorite': False, 'textId': 'endfield:authored:one',
        'english': 'The original saved translation.', 'chinese': '保存された元の文章。',
        'sourceLocale': 'ja', 'sourceLanguage': 'ja', 'sourceText': '保存された元の文章。',
        'translationLocale': 'en', 'translationText': 'The original saved translation.',
        'audioLocale': 'ja', 'audioScope': 'context', 'voiceStatus': 'voiced',
        'textCaptureVerified': True, 'hadAudio': True, **changes}


def backup(*rows):
    return json.dumps({'format': FORMAT, 'rows': list(rows or [row()])}, ensure_ascii=False).encode()


def test_preserves_original_text_languages_scope_dates_and_favorites_without_inventing_audio(tmp_path):
    entries = parse_backup(backup(row(favorite=True), row(id='second', createdAt=1794783739001,
        voiceStatus='unknown', hadAudio=False, textTruncated=True)))
    store = TranscriptStore(tmp_path / 'history.sqlite')
    assert store.import_browser_history(entries) == {'imported': 2, 'favorites_promoted': 0, 'already_imported': 0}
    lines = store.list()
    assert len(lines) == 2
    first = next(line for line in lines if line.favorite)
    assert first.source_text == row()['sourceText'] and first.translation_text == row()['translationText']
    assert first.source_locale == 'ja' and first.audio_locale == 'ja' and first.audio_scope == 'context'
    assert first.voice_status == 'unavailable' and not first.has_audio
    assert int(first.created_at.timestamp() * 1000) == row()['createdAt']
    excerpt = next(line for line in lines if not line.favorite)
    assert excerpt.dialogue_kind == 'browser_history_excerpt' and not excerpt.text_capture_verified
    store.prune(0);store.purge_unvoiced()
    assert store.count() == 2  # Archive rows are not live-capture retention candidates.


def test_replay_promotes_favorites_never_clears_or_resurrects_deleted_rows(tmp_path):
    store = TranscriptStore(tmp_path / 'history.sqlite')
    assert store.import_browser_history(parse_backup(backup()))['imported'] == 1
    assert store.import_browser_history(parse_backup(backup(row(favorite=True))))['favorites_promoted'] == 1
    assert store.import_browser_history(parse_backup(backup()))['already_imported'] == 1
    line, = store.list();assert line.favorite
    store.delete(line.id)
    assert store.import_browser_history(parse_backup(backup()))['already_imported'] == 1
    assert store.count() == 0


def test_failed_publication_rolls_back_all_rows_and_replay_ledger(tmp_path):
    store = TranscriptStore(tmp_path / 'history.sqlite')
    entries = parse_backup(backup(row(), row(id='second')))
    def cancelled(): raise InterruptedError('Authored account retirement before commit')
    with pytest.raises(InterruptedError): store.import_browser_history(entries, before_commit=cancelled)
    assert store.count() == 0
    assert store.import_browser_history(entries)['imported'] == 2


@pytest.mark.parametrize('changes', [
    {'favorite': 1}, {'createdAt': True}, {'createdAt': -1}, {'game': 'not-a-game'},
    {'source': 'https://private-stream.test'}, {'id': True}, {'sourceText': ''},
    {'sourceText': 'x' * 8001}, {'audioSha256': 'bad'}, {'sourceLocale': '../../bad'},
    {'score': 101}, {'voiceStatus': 'guessed'}, {'audioScope': 'guess'}, {'voiceStatus': {}}, {'audioScope': []},
    {'rememberedKey': 'authored-secret-not-importable'}, {'textCaptureVerified': 'true'},
])
def test_malformed_or_private_fields_are_rejected_before_any_store_write(changes):
    with pytest.raises(ValueError): parse_backup(backup(row(**changes)))


def test_duplicate_json_fields_and_duplicate_rows_are_rejected():
    with pytest.raises(ValueError): parse_backup(b'{"format":"x","format":"toolkit-browser-history-v1","rows":[]}')
    with pytest.raises(ValueError): parse_backup(backup(row(), row(favorite=True)))


def test_preview_and_import_are_scoped_to_real_mocked_account_selection(account_host):
    host = account_host
    first = register(host, 'first');old = host.account_generation
    body = backup(row(favorite=True))
    request_headers = {**headers(host), 'X-Proxy-Transcript': 'setup', 'Content-Type': 'application/json'}
    status, preview = request(host, 'POST', '/api/history/migration/preview', body, headers=request_headers)
    assert status == 200 and preview['rows'] == preview['favorites'] == 1
    assert not preview['audio_included'] and host.session.history.count() == 0
    register(host, 'second')
    assert request(host, 'POST', '/api/history/migration/import', body, headers=request_headers)[0] == 409
    assert host.session.history.count() == 0
    current_headers = {**headers(host), 'X-Proxy-Transcript': 'setup'}
    status, result = request(host, 'POST', '/api/history/migration/import', body, headers=current_headers)
    assert status == 200 and result['imported'] == 1
    assert host.session.history.list()[0].favorite
    assert request(host, 'POST', '/api/lexirise/accounts/select', json.dumps({'id': first}).encode(), headers=headers(host))[0] == 200
    assert host.account_generation > old and host.session.history.count() == 0


def test_preview_reports_all_games_languages_and_excerpts():
    info = summary(parse_backup(backup(row(), row(id='two', game='genshin', textTruncated=True, favorite=True))))
    assert info['games'] == ['endfield', 'genshin'] and info['study_locales'] == ['ja']
    assert info['excerpts'] == 1 and info['favorites'] == 1


def test_paged_archive_retains_oldest_favorite_and_rejects_stale_owner_reads(account_host):
    host = account_host;register(host, 'first')
    host.session.history.import_browser_history(parse_backup(backup(*[
        row(id=str(n), createdAt=1794783739000+n, favorite=n==0) for n in range(301)])))
    old_headers = headers(host)
    route = '/api/history/migration/lines?game=endfield&page=0&favorites=false'
    status, value = request(host, 'GET', route, headers=old_headers)
    assert status == 200 and value['total'] == 301 and len(value['rows']) == 10
    assert all(line['id'] > 2**32 for line in value['rows'])
    last = request(host, 'GET', route.replace('page=0', 'page=30'), headers=old_headers)[1]
    assert len(last['rows']) == 1 and last['rows'][0]['favorite']
    favorites = request(host, 'GET', route.replace('favorites=false', 'favorites=true'), headers=old_headers)[1]
    assert favorites['total'] == len(favorites['rows']) == 1
    register(host, 'second')
    assert request(host, 'GET', route, headers=old_headers)[0] == 409
    assert request(host, 'GET', route, headers=headers(host))[1]['total'] == 0


def test_explicit_unvoiced_history_stays_distinct_from_unknown():
    entries = parse_backup(backup(row(voiceStatus='unvoiced', hadAudio=False),
        row(id='unknown', voiceStatus='unknown', hadAudio=False)))
    assert [line.voice_status for _, line in entries] == ['unvoiced', 'unknown']


def test_authored_copy_contract_preserves_nonempty_import_ledger_and_refuses_tampering(tmp_path):
    from backend import runtime_data_copy_probe as probe
    store = TranscriptStore(tmp_path / 'source.db')
    store.import_browser_history(parse_backup(backup(row(favorite=True), row(id='second'))))
    expected = [probe._row(line.model_dump(mode='json')) for line in sorted(store.list(), key=lambda line: line.id)]
    with closing(sqlite3.connect(store.path)) as connection:
        archive = connection.execute('SELECT source_key,line_id FROM browser_history_imports ORDER BY source_key').fetchall()
    copied = tmp_path / 'copied.db';shutil.copy2(store.path, copied)
    with closing(sqlite3.connect(copied)) as connection:
        connection.row_factory = sqlite3.Row
        probe._verify_store(connection, 'data/transcript-v2.db', expected, archive_expected=archive)
        connection.execute('UPDATE browser_history_imports SET line_id=line_id+100')
        with pytest.raises(probe.DataCopyFailure) as changed:
            probe._verify_store(connection, 'data/transcript-v2.db', expected, archive_expected=archive)
        assert changed.value.code == 'authored-rows-differ'
        connection.rollback()
        connection.execute('CREATE TABLE unrelated_owned_claim (value TEXT)')
        with pytest.raises(probe.DataCopyFailure) as unknown:
            probe._verify_store(connection, 'data/transcript-v2.db', expected, archive_expected=archive)
        assert unknown.value.code == 'schema-unconfirmed'
