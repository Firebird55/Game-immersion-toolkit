"""Synthetic host ordering/lease regressions, not native lifecycle acceptance.

The source handoff tests do not exercise continuous cross-root exclusion,
coordinator ownership, copy barriers or durable pointer recovery.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from backend.bundle_host import (ExclusiveFileLease, HostProbeError, SyntheticHandoff,
                                 SyntheticHostCoordinator, SyntheticReadiness, WriterStopProof,
                                 create_synthetic_root, inspect_synthetic_recovery)


STOPPED = WriterStopProof(True, True, True, True, True)


class FixtureRuntime:
    def __init__(self, installation_id, name, events, *, running=False):
        self.installation_id, self.runtime_id, self.events = installation_id, name, events
        self.running, self.generation = running, 0
        self.readiness = SyntheticReadiness(True, True, True, True)
        self.stop_proof = STOPPED
        self.prepare_hook = lambda: None
        self.activate_hook = lambda: None

    def prepare(self):
        self.events.append((self.runtime_id, 'prepare'))
        self.prepare_hook()

    def ready(self):
        return self.readiness

    def capture_running(self):
        return self.running

    def write_generation(self):
        return self.generation

    def quiesce(self):
        handoff = SyntheticHandoff(self.running)
        self.events.append((self.runtime_id, 'quiesce'))
        if self.stop_proof.complete:
            self.running = False
        return self.stop_proof, handoff

    def activate(self, handoff):
        self.events.append((self.runtime_id, 'activate'))
        self.running = handoff.running
        self.activate_hook()

    def stop(self):
        self.events.append((self.runtime_id, 'stop'))
        if self.stop_proof.complete:
            self.running = False
        return self.stop_proof


class BundleHostTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='r19-host-')
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.legacy = create_synthetic_root(root / 'old ZIP 中文')
        self.state = create_synthetic_root(root / 'target host', installation_id=self.legacy.installation_id)
        self.events = []
        self.old = FixtureRuntime(self.legacy.installation_id, 'old', self.events, running=True)

    def candidate(self, name='candidate'):
        return FixtureRuntime(self.legacy.installation_id, name, self.events)

    def assert_busy(self):
        lease = ExclusiveFileLease(self.legacy.path / 'data/companion-operation.lock')
        with self.assertRaises(HostProbeError) as caught:
            lease.acquire()
        self.assertEqual(caught.exception.code, 'operation-busy')

    def test_update_and_rollback_hold_legacy_exclusion_without_nested_source_updater(self):
        host = SyntheticHostCoordinator(self.legacy, self.state, self.old)
        with host:
            self.assert_busy()
            with self.assertRaises(HostProbeError) as denied:
                host.require_guarded_source_update(host.owner)
            self.assertEqual(denied.exception.code, 'guarded-source-update-unavailable')
            self.assert_busy()
            candidate = self.candidate()
            candidate.prepare_hook = self.assert_busy
            candidate.activate_hook = lambda: (self.assertFalse(self.old.running), self.assert_busy())
            host.update(host.owner, candidate)
            self.assertFalse(self.old.running)
            self.assertTrue(candidate.running)
            self.assert_busy()
            host.rollback(host.owner)
            self.assertFalse(candidate.running)
            self.assertTrue(self.old.running)
            self.assert_busy()
            recovery = inspect_synthetic_recovery(self.state)
            self.assertEqual(recovery['journal']['stage'], 'rolled-back')
            self.assertEqual(recovery['pointer']['runtime_id'], 'old')
            self.assertEqual(recovery['installed_launcher'], 'unchanged-unverified-R20')
            self.assertFalse(recovery['production_activation_allowed'])
        self.assertFalse(self.old.running)
        lease = ExclusiveFileLease(self.legacy.path / 'data/companion-operation.lock')
        lease.acquire()
        lease.close()
        self.assertLess(self.events.index(('old', 'quiesce')), self.events.index(('candidate', 'activate')))
        self.assertLess(self.events.index(('candidate', 'stop')), self.events.index(('old', 'activate')))

    def test_failure_and_unconfirmed_cleanup_cannot_resume_competing_capture_or_release_lock(self):
        host = SyntheticHostCoordinator(self.legacy, self.state, self.old).__enter__()
        candidate = self.candidate()
        def crash():
            candidate.stop_proof = WriterStopProof(False, True, True, True, False)
            raise RuntimeError('synthetic activation crash')
        candidate.activate_hook = crash
        with self.assertRaises(HostProbeError) as caught:
            host.update(host.owner, candidate)
        self.assertEqual(caught.exception.code, 'cleanup-unconfirmed')
        self.assertFalse(self.old.running)
        self.assertTrue(candidate.running)
        self.assert_busy()
        with self.assertRaises(HostProbeError):
            host.close(host.owner)
        self.assert_busy()
        candidate.stop_proof = STOPPED
        host.close(host.owner)
        self.assertFalse(candidate.running)

    def test_readiness_and_partial_quiesce_do_not_authorize_takeover(self):
        with SyntheticHostCoordinator(self.legacy, self.state, self.old) as host:
            self.old.stop_proof = WriterStopProof(True, True, False, True, True)
            candidate = self.candidate()
            with self.assertRaises(HostProbeError) as caught:
                host.update(host.owner, candidate)
            self.assertEqual(caught.exception.code, 'quiesce-incomplete')
            self.assertNotIn(('candidate', 'activate'), self.events)
            self.assertTrue(self.old.running)
            self.assertEqual(inspect_synthetic_recovery(self.state)['journal']['stage'], 'recovery-required')
            with self.assertRaises(HostProbeError) as blocked:
                host.update(host.owner, self.candidate('next'))
            self.assertEqual(blocked.exception.code, 'recovery-required')
            self.old.stop_proof = STOPPED

    def test_failed_preparation_retains_old_capture_and_owner_capability_is_not_a_flag(self):
        with SyntheticHostCoordinator(self.legacy, self.state, self.old) as host:
            candidate = self.candidate()
            candidate.readiness = SyntheticReadiness(True, False, True, True)
            with self.assertRaises(HostProbeError) as owner:
                host.update(True, candidate)
            self.assertEqual(owner.exception.code, 'ownership-required')
            with self.assertRaises(HostProbeError) as failure:
                host.update(host.owner, candidate)
            self.assertEqual(failure.exception.code, 'candidate-not-ready')
            self.assertTrue(self.old.running)
            self.assertFalse(candidate.running)
            self.assert_busy()

    def test_nested_owned_operation_fails_promptly_and_other_operations_serialize(self):
        with SyntheticHostCoordinator(self.legacy, self.state, self.old) as host:
            candidate = self.candidate()
            observed = []
            def nested():
                try:
                    host.update(host.owner, self.candidate('nested'))
                except HostProbeError as error:
                    observed.append(error.code)
            candidate.prepare_hook = nested
            host.update(host.owner, candidate)
            self.assertEqual(observed, ['nested-operation'])
            entered, done = threading.Event(), threading.Event()
            def update():
                entered.set()
                host.update(host.owner, self.candidate('later'))
                done.set()
            with host.stopped_writers(host.owner) as barrier:
                thread = threading.Thread(target=update)
                thread.start()
                self.assertTrue(entered.wait(1))
                self.assertFalse(done.wait(.03))
                barrier.check(self.legacy)
            thread.join(2)
            self.assertTrue(done.is_set())
            with self.assertRaises(HostProbeError):
                barrier.check(self.legacy)

    def test_post_activation_writes_require_reconciliation_and_checkpoints_are_not_process_authority(self):
        with SyntheticHostCoordinator(self.legacy, self.state, self.old) as host:
            candidate = self.candidate()
            host.update(host.owner, candidate)
            candidate.generation += 1
            with self.assertRaises(HostProbeError) as caught:
                host.rollback(host.owner)
            self.assertEqual(caught.exception.code, 'post-activation-writes')
            self.assertTrue(candidate.running)
            self.assertFalse(self.old.running)
            self.assertEqual(inspect_synthetic_recovery(self.state)['process_ownership'], 'must-reverify')
        with self.assertRaises(HostProbeError) as caught:
            SyntheticHostCoordinator(self.legacy, self.state, self.old).__enter__()
        self.assertEqual(caught.exception.code, 'recovery-required')

    def test_guard_process_exit_releases_os_lease_but_does_not_claim_worker_crash_containment(self):
        path = self.legacy.path / 'data/companion-operation.lock'
        ready = Path(self.temporary.name) / 'guard-ready'
        # A Windows venv executable is a redirector, not the lease owner.
        # This stdlib-only fixture must retain the real interpreter handle.
        child = subprocess.Popen([getattr(sys, '_base_executable', sys.executable), '-c',
                                  'import sys; from pathlib import Path; from backend.bundle_host import ExclusiveFileLease; '
                                  'lease=ExclusiveFileLease(Path(sys.argv[1])); lease.acquire(); '
                                  'Path(sys.argv[2]).write_text("held"); sys.stdin.read()', str(path), str(ready)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 3
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(ready.exists(), 'Owned fixture guard did not become ready before its deadline.')
            self.assert_busy()
            child.terminate()
            child.wait(timeout=5)
            lease = ExclusiveFileLease(path)
            lease.acquire()
            lease.close()
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()
        # No runtime children were launched: Windows Job Object/lifetime proof
        # remains an acceptance blocker, not inferred from OS lock cleanup.

    def test_marker_cannot_label_existing_data_or_follow_links(self):
        with self.assertRaises(HostProbeError):
            create_synthetic_root(self.legacy.path)
        alias = Path(self.temporary.name) / 'linked'
        try:
            alias.symlink_to(self.legacy.path, target_is_directory=True)
        except OSError:
            self.skipTest('This host does not permit synthetic symbolic links.')
        with self.assertRaises(HostProbeError):
            create_synthetic_root(alias)
        with self.assertRaises(HostProbeError):
            create_synthetic_root(alias / 'new-child')
        self.assertFalse((self.legacy.path / 'new-child').exists())

    def test_failed_writer_barrier_keeps_source_stopped_and_exclusion_held(self):
        with SyntheticHostCoordinator(self.legacy, self.state, self.old) as host:
            with self.assertRaises(HostProbeError) as failed:
                with host.stopped_writers(host.owner):
                    self.old.generation += 1
            self.assertEqual(failed.exception.code, 'writer-barrier-required')
            self.assertFalse(self.old.running)
            self.assert_busy()
            self.assertEqual(inspect_synthetic_recovery(self.state)['journal']['stage'], 'recovery-required')

    def test_linked_recovery_checkpoint_is_not_adopted(self):
        with SyntheticHostCoordinator(self.legacy, self.state, self.old) as host:
            destination = self.state.path / 'injected.json'
            destination.write_text(host.pointer_path.read_text())
            host.pointer_path.unlink()
            try:
                host.pointer_path.symlink_to(destination)
            except OSError:
                self.skipTest('This host does not permit synthetic symbolic links.')
            try:
                with self.assertRaises(HostProbeError) as caught:
                    inspect_synthetic_recovery(self.state)
                self.assertEqual(caught.exception.code, 'unsafe-path')
            finally:
                host.pointer_path.unlink()
                host.pointer_path.write_text(destination.read_text())


if __name__ == '__main__':
    unittest.main()
