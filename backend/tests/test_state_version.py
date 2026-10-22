from concurrent.futures import ThreadPoolExecutor

from backend.state_version import StateVersion


def test_snapshot_does_not_become_newer_when_response_arrives_late():
    clock = StateVersion()
    before = clock.snapshot(2)
    event = clock.publish(2)
    after = clock.snapshot(2)
    assert before["state_version"] < event["state_version"] == after["state_version"]
    assert before["runtime_id"] == event["runtime_id"]


def test_restart_and_account_roundtrip_have_distinct_contexts():
    first, second = StateVersion(), StateVersion()
    assert first.snapshot(0)["runtime_id"] != second.snapshot(0)["runtime_id"]
    assert first.snapshot(1) != first.snapshot(3)


def test_concurrent_publications_have_unique_ordered_versions():
    clock = StateVersion()
    with ThreadPoolExecutor(max_workers=8) as pool:
        versions = list(pool.map(lambda _: clock.publish(4)["state_version"], range(100)))
    assert sorted(versions) == list(range(1, 101))
    assert clock.snapshot(4)["state_version"] == 100
