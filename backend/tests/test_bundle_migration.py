"""Synthetic copy/recovery cases missing from ordinary runtime handoff checks.

Byte verification cannot establish native DPAPI, browser or installed migration.
"""
import hashlib
from contextlib import closing
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.bundle_host import HostProbeError, SyntheticHostCoordinator, SyntheticReadiness, create_synthetic_root
from backend.bundle_migration import SyntheticMigrationPlan, copy_and_verify_synthetic
from backend.tests.test_bundle_host import FixtureRuntime


def put(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def database(root, name, version, sql):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(sql)
        connection.execute('PRAGMA user_version=' + str(version))
        connection.commit()
    finally:
        connection.close()
    return path


def hashes(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file() and path.name != 'companion-operation.lock'}


class BundleMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='r19-migration-')
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = create_synthetic_root(root / 'legacy 中文 ZIP')
        self.target = create_synthetic_root(root / 'candidate data', installation_id=self.source.installation_id)
        self.external = create_synthetic_root(root / 'external volume', installation_id=self.source.installation_id)
        self.old = FixtureRuntime(self.source.installation_id, 'source', [], running=True)
        database(self.source.path, 'data/transcript-v2.db', 2,
                 "CREATE TABLE lines(id INTEGER, text TEXT, favorite INTEGER, audio TEXT);"
                 "INSERT INTO lines VALUES(1,'保留中文',1,'alias-a.mp3');"
                 "INSERT INTO lines VALUES(2,'保留中文',0,'alias-b.mp3');")
        database(self.source.path, 'data/lexirise/reading-cache-v2.db', 2,
                 "CREATE TABLE grammar_choices(rule TEXT, choice TEXT); INSERT INTO grammar_choices VALUES('fixture','hide');")
        database(self.source.path, 'data/lexirise/exports-v2.db', 2,
                 "CREATE TABLE exports(account TEXT, locale TEXT, destination TEXT, completed INTEGER);"
                 "INSERT INTO exports VALUES('mock-account','ja','mock-deck',1);")
        database(self.source.path, 'data/transcript-old.db', 1, 'CREATE TABLE archived(id INTEGER); INSERT INTO archived VALUES(7);')
        audio = put(self.source.path, 'data/audio/alias-a.mp3', b'owned synthetic audio bytes')
        try:
            os.link(audio, audio.with_name('alias-b.mp3'))
        except OSError:
            shutil.copy2(audio, audio.with_name('alias-b.mp3'))
        put(self.source.path, 'data/lexirise/key.dpapi', b'encrypted synthetic fallback only')
        put(self.source.path, 'data/languages/game/ja/textmap.json', b'{"audio_locale":"ja","source_locale":"ja"}')
        put(self.source.path, 'data/settings.json', b'{"legacy":true,"hito":{"left":0.1}}')
        put(self.source.path, 'host-settings/settings.json', b'{"capture_unvoiced":true,"hito":{"left":0.2}}')
        put(self.source.path, 'host-settings/languages.requests.json', b'{"account":"mock","target":"en","state":"cancelled"}')
        put(self.source.path, 'host-credentials/accounts.dpapi', b'unreadable encrypted fixture account store')
        put(self.source.path, 'host-credentials/key.dpapi', b'encrypted fixture host key')
        put(self.source.path, 'work/voice-assets/reader.mjs', b'// synthetic acquired helper')
        put(self.source.path, 'unknown-legacy-file.bin', b'preserve in place')
        put(self.external.path, 'transfer/library.zip', b'completed owned fixture export')
        put(self.external.path, '.toolkit-mobile-work/destination/previous-libraries/old.zip', b'complete previous fixture library')
        put(self.external.path, 'transfer/.toolkit-work/previous-libraries/legacy.zip', b'complete legacy previous fixture library')
        put(self.external.path, '.toolkit-mobile-work/destination/resume.json', b'{"state":"cancelled"}')
        self.versions = {'data/transcript-v2.db': 2, 'data/transcript-old.db': 1,
                         'data/lexirise/reading-cache-v2.db': 2, 'data/lexirise/exports-v2.db': 2}

    def plan(self, **changes):
        return SyntheticMigrationPlan(self.source, self.target, external_destinations=(self.external,),
                                      database_versions=self.versions, **changes)

    def copy(self, host, plan, **options):
        with host.stopped_writers(host.owner) as barrier:
            return copy_and_verify_synthetic(plan, barrier, **options)

    def test_preserves_all_aliases_grammar_export_ledgers_settings_and_external_previous_libraries(self):
        before, external_before = hashes(self.source.path), hashes(self.external.path)
        plan = self.plan(named_account_store='unreadable')
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            manifest = self.copy(host, plan)
            self.assertTrue(self.old.running)
        snapshot = self.target.path / 'staging' / plan.migration_id
        self.assertEqual(manifest['state'], 'verified')
        self.assertEqual(manifest['migration_acceptance'], 'incomplete')
        self.assertFalse(manifest['activation_allowed'])
        self.assertEqual(hashes(self.source.path), before)
        self.assertEqual(hashes(self.external.path), external_before)
        self.assertFalse((snapshot / 'data/companion-operation.lock').exists())
        for name in ('alias-a.mp3', 'alias-b.mp3'):
            self.assertEqual((snapshot / 'data/audio' / name).read_bytes(), b'owned synthetic audio bytes')
        (snapshot / 'data/audio/alias-a.mp3').unlink()
        self.assertTrue((snapshot / 'data/audio/alias-b.mp3').exists())
        with closing(sqlite3.connect(snapshot / 'data/transcript-v2.db')) as connection:
            self.assertEqual(connection.execute('SELECT text,favorite,audio FROM lines ORDER BY id').fetchall(),
                             [('保留中文', 1, 'alias-a.mp3'), ('保留中文', 0, 'alias-b.mp3')])
        with closing(sqlite3.connect(snapshot / 'data/lexirise/reading-cache-v2.db')) as connection:
            self.assertEqual(connection.execute('SELECT choice FROM grammar_choices').fetchone(), ('hide',))
        with closing(sqlite3.connect(snapshot / 'data/lexirise/exports-v2.db')) as connection:
            self.assertEqual(connection.execute('SELECT account,locale,destination,completed FROM exports').fetchone(),
                             ('mock-account', 'ja', 'mock-deck', 1))
        self.assertEqual((snapshot / 'host-settings/settings.json').read_bytes(), (self.source.path / 'host-settings/settings.json').read_bytes())
        self.assertEqual((snapshot / 'data/lexirise/key.dpapi').read_bytes(), b'encrypted synthetic fallback only')
        self.assertFalse((snapshot / 'host-credentials').exists())
        self.assertEqual(manifest['credentials']['named_profiles'], 'unreadable-repair-required')
        self.assertTrue(all(item['present'] for item in manifest['credentials']['locators']))
        self.assertTrue(any('previous-libraries/old.zip' in item['name'] for item in manifest['external_destinations'][0]['files']))
        self.assertEqual(manifest['browser']['indexedDB'], 'unchanged-unverified')
        self.assertEqual(manifest['browser']['opfs'], 'unchanged-unverified')
        self.assertFalse(manifest['browser']['raw_profile_copy'])
        self.assertEqual(manifest['installed_launcher_checkpoint'], 'unchanged-unverified-R20')

    @unittest.skipUnless(os.name == 'nt', 'Windows current-user DPAPI unavailable on this host; native protected-byte proof not run.')
    def test_current_user_dpapi_test_fallback_survives_copy_without_plaintext_or_named_store_repair(self):
        # Byte-copy and mocked protection tests cannot prove current-user DPAPI
        # usability. Only synthetic values and marked temp locators are used;
        # no AccountStore, host credential locator or network client is opened.
        from backend.lexirise import LexiriseError, _protect

        marker = b'r19-synthetic-dpapi-test-' + os.urandom(32).hex().encode('ascii')
        fallback_value, host_value = marker + b'/fallback', marker + b'/host'
        named_value = json.dumps({'active': 'fixture', 'profiles': {
            'fixture': {'name': 'Synthetic DPAPI test', 'key': marker.decode('ascii')}}}).encode('utf-8')
        protected_named = _protect(named_value)
        self.assertTrue(_protect(protected_named, decrypt=True) == named_value,
                        'The synthetic named-store DPAPI round trip did not match.')
        # Preserve an actually unreadable named-store fixture rather than
        # implying that copying readable fallback bytes repairs other accounts.
        unreadable_named = protected_named[:len(protected_named) // 2]
        encrypted = {
            'data/lexirise/key.dpapi': _protect(fallback_value),
            'host-credentials/key.dpapi': _protect(host_value),
            'host-credentials/accounts.dpapi': unreadable_named,
        }
        for name, content in encrypted.items():
            self.assertFalse(marker in content, 'A protected fixture blob contains the synthetic plaintext marker.')
            put(self.source.path, name, content)
        with self.assertRaises(LexiriseError):
            _protect(unreadable_named, decrypt=True)

        before = hashes(self.source.path)
        plan = self.plan(named_account_store='unreadable')
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            manifest = self.copy(host, plan)
        snapshot = self.target.path / 'staging' / plan.migration_id
        self.assertEqual(hashes(self.source.path), before)
        for name, content in encrypted.items():
            self.assertTrue((self.source.path / name).read_bytes() == content,
                            'An original protected fixture blob changed.')
        copied_fallback = (snapshot / 'data/lexirise/key.dpapi').read_bytes()
        self.assertTrue(copied_fallback == encrypted['data/lexirise/key.dpapi'],
                        'The copied protected fallback bytes changed.')
        self.assertTrue(_protect(copied_fallback, decrypt=True) == fallback_value,
                        'The copied fallback could not reproduce the same-user test value.')
        self.assertTrue(_protect((self.source.path / 'host-credentials/key.dpapi').read_bytes(), decrypt=True) == host_value,
                        'The preserved host locator could not reproduce the same-user test value.')
        self.assertFalse((snapshot / 'host-credentials').exists())
        self.assertEqual(manifest['credentials']['named_profiles'], 'unreadable-repair-required')
        self.assertTrue(any('Preserving repair' in requirement for requirement in manifest['open_requirements']))
        self.assertFalse(manifest['activation_allowed'])
        self.assertEqual(manifest['migration_acceptance'], 'incomplete')
        self.assertFalse(marker in json.dumps(manifest).encode('utf-8'),
                         'The migration manifest contains the synthetic plaintext marker.')
        for path in snapshot.rglob('*'):
            if path.is_file():
                self.assertFalse(marker in path.read_bytes(), 'A snapshot file contains the synthetic plaintext marker.')

    def test_interrupted_copy_resumes_only_its_owned_manifest_and_preserves_source(self):
        plan = self.plan()
        before = hashes(self.source.path)
        calls = []
        def interrupt(stage, name):
            calls.append(name)
            raise RuntimeError('synthetic interruption')
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            with host.stopped_writers(host.owner) as barrier:
                with self.assertRaises(RuntimeError):
                    copy_and_verify_synthetic(plan, barrier, checkpoint=interrupt)
                manifest_path = self.target.path / 'migrations' / plan.migration_id / 'manifest.json'
                failed = json.loads(manifest_path.read_text())
                self.assertEqual(failed['state'], 'failed')
                self.assertEqual(len(failed['completed_files']), 1)
                self.assertEqual(hashes(self.source.path), before)
                changed_versions = {**self.versions, 'data/transcript-v2.db': 99}
                with self.assertRaises(HostProbeError) as changed_plan:
                    copy_and_verify_synthetic(replace(plan, database_versions=changed_versions), barrier)
                self.assertEqual(changed_plan.exception.code, 'source-or-plan-changed')
                self.assertFalse(self.old.running)
                resumed = copy_and_verify_synthetic(plan, barrier)
                self.assertEqual(resumed['state'], 'verified')
                self.assertEqual(len(resumed['completed_files']), len(resumed['inventory']))
                self.assertEqual(hashes(self.source.path), before)
            manifest_path.write_text('{malformed')
            with self.assertRaises(HostProbeError) as malformed:
                self.copy(host, plan)
            self.assertEqual(malformed.exception.code, 'invalid-manifest')

    def test_preparation_or_expired_barrier_cannot_copy_and_source_changes_fail_closed(self):
        plan = self.plan()
        with self.assertRaises(HostProbeError) as ready:
            copy_and_verify_synthetic(plan, SyntheticReadiness(True, True, True, True))
        self.assertEqual(ready.exception.code, 'writer-barrier-required')
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            with host.stopped_writers(host.owner) as barrier:
                barrier.check(self.source)
            with self.assertRaises(HostProbeError):
                copy_and_verify_synthetic(plan, barrier)
            changed = False
            def mutate(stage, name):
                nonlocal changed
                if not changed:
                    changed = True
                    put(self.source.path, 'data/late-writer.json', b'{"unexpected":true}')
            with self.assertRaises(HostProbeError) as changed_source:
                self.copy(host, plan, checkpoint=mutate)
            self.assertEqual(changed_source.exception.code, 'source-changed')
            self.assertFalse(self.old.running)
            with self.assertRaises(HostProbeError) as resumed:
                self.copy(host, plan)
            self.assertEqual(resumed.exception.code, 'recovery-required')
            self.assertTrue((self.source.path / 'data/late-writer.json').exists())

    def test_closed_writer_file_set_keeps_committed_wal_content_and_every_sidecar(self):
        # Author a coherent fixture file set with committed data still in WAL.
        # No connection owns the migrated copies; this is not a live DB strategy.
        authored = Path(self.temporary.name) / 'authored.db'
        with closing(sqlite3.connect(authored)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA wal_autocheckpoint=0')
            connection.execute('CREATE TABLE fixture(value TEXT)')
            connection.execute("INSERT INTO fixture VALUES('committed in WAL')")
            connection.execute('PRAGMA user_version=7')
            connection.commit()
            for suffix in ('', '-wal', '-shm'):
                shutil.copy2(authored.with_name(authored.name + suffix), self.source.path / ('data/wal.db' + suffix))
        self.versions['data/wal.db'] = 7
        plan = self.plan()
        before = hashes(self.source.path)
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            manifest = self.copy(host, plan)
        snapshot = self.target.path / 'staging' / plan.migration_id
        for suffix in ('', '-wal', '-shm'):
            name = 'data/wal.db' + suffix
            self.assertEqual(hashlib.sha256((snapshot / name).read_bytes()).hexdigest(), before[name])
        self.assertTrue(any(item['name'] == 'data/wal.db' and item['user_version'] == 7 for item in manifest['databases']))
        self.assertEqual(hashes(self.source.path), before)

    def test_unknown_or_incompatible_schema_and_no_space_never_mark_verified(self):
        plan = self.plan()
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            with host.stopped_writers(host.owner) as barrier:
                with patch('backend.bundle_migration.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
                    with self.assertRaises(HostProbeError) as space:
                        copy_and_verify_synthetic(plan, barrier)
                self.assertEqual(space.exception.code, 'insufficient-space')
                self.versions['data/transcript-v2.db'] = 99
                incompatible = self.plan()
                with self.assertRaises(HostProbeError) as schema:
                    copy_and_verify_synthetic(incompatible, barrier)
                self.assertEqual(schema.exception.code, 'incompatible-database-schema')
                del self.versions['data/transcript-v2.db']
                with self.assertRaises(HostProbeError) as unknown:
                    copy_and_verify_synthetic(self.plan(), barrier)
                self.assertEqual(unknown.exception.code, 'unknown-database-schema')
        self.assertTrue((self.source.path / 'data/transcript-v2.db').exists())

    def test_external_writer_changes_preserve_source_without_resuming_after_invalid_barrier(self):
        plan = self.plan()
        changed = False
        def mutate_external(stage, name):
            nonlocal changed
            if not changed:
                changed = True
                put(self.external.path, 'transfer/new.zip', b'new fixture library')
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            with self.assertRaises(HostProbeError) as external:
                self.copy(host, plan, checkpoint=mutate_external)
            self.assertEqual(external.exception.code, 'external-source-changed')
            self.assertFalse(self.old.running)
        self.assertTrue((self.external.path / 'transfer/new.zip').exists())

    def test_links_fail_without_adopting_external_roots(self):
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            alias = self.source.path / 'data/linked'
            try:
                alias.symlink_to(self.external.path, target_is_directory=True)
            except OSError:
                self.skipTest('This host does not permit synthetic symbolic links.')
            with self.assertRaises(HostProbeError) as linked:
                self.copy(host, self.plan())
            self.assertEqual(linked.exception.code, 'unsafe-path')
        self.assertTrue((self.external.path / 'transfer/library.zip').exists())

    def test_resumed_snapshot_rejects_unlisted_files_instead_of_verifying_them(self):
        plan = self.plan()
        with SyntheticHostCoordinator(self.source, self.target, self.old) as host:
            with host.stopped_writers(host.owner) as barrier:
                def interrupt(stage, name):
                    raise RuntimeError('synthetic interrupted copy')
                with self.assertRaises(RuntimeError):
                    copy_and_verify_synthetic(plan, barrier, checkpoint=interrupt)
                unlisted = put(self.target.path, 'staging/' + plan.migration_id + '/data/unlisted.db', b'unowned injected fixture')
                with self.assertRaises(HostProbeError) as unowned:
                    copy_and_verify_synthetic(plan, barrier)
                self.assertEqual(unowned.exception.code, 'target-inventory-mismatch')
                self.assertTrue(unlisted.exists())
                manifest = json.loads((self.target.path / 'migrations' / plan.migration_id / 'manifest.json').read_text())
                self.assertEqual(manifest['state'], 'failed')


if __name__ == '__main__':
    unittest.main()
