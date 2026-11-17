"""Frozen ORIGINAL launcher inputs for the exact retained native baseline.

This historical acquisition contract is independent of the current launcher.
No publisher code executes and no parameter literals are stored here. The
baseline loader must still authenticate its complete manifest and original PE.
"""
from . import nte_updater_source as source
from .nte_updater_native import check


DESCRIPTION = {
    "artifacts": [
        {
            "md5": "4a6d9ad19807955d0b8efeef6fe84f3a",
            "member": "PatcherConfig.json",
            "packed_md5": "f26c0b9eac82dc8c72cf1023644094c4",
            "packed_size": 307,
            "role": "configuration",
            "size": 428,
            "url": "https://ntecdn1.perfectworld.com/hd/publish_PC/launcher/1.0.8.1102_4/ResFilesM/3000001/PatcherConfig/PatcherConfig.json.zip"
        },
        {
            "md5": "137214f9f38f15e4c7c7aea0cf16e223",
            "member": "PatcherSDK_x64.dll",
            "packed_md5": "848572c1db4c8fde3bd27c4d8497c8dc",
            "packed_size": 2679603,
            "role": "sdk",
            "size": 7414632,
            "url": "https://ntecdn1.perfectworld.com/hd/publish_PC/launcher/1.0.8.1102_4/PatcherSDK_x64.dll.zip"
        }
    ],
    "manifest_sha256": "4c09e9bc00f7231a4ddf4a60e0e39ca8a0456c69b81722aaed999f293eee4a43",
    "manifest_url": "https://ntecdn1.perfectworld.com/hd/publish_PC/launcher/1.0.8.1102_4/AllFiles.xml",
    "region": "nte-global",
    "version": "1.0.8.1102_4",
    "version_sha256": "76ce24f2fbfacb870dc32ee345caff77dfdc01ccbfaa6a67c883df89a7d235d3"
}
MEMBER_SHA256 = {
    "configuration": "a355b9845cc6e438c6fb30c75c8636a490054fda512311bdc73ead503f18b837",
    "sdk": "7ff80b450902c29d26d42159fe81782646fe63e65c5fbda402918d4f34577949"
}


def inputs():
    return source._inputs(DESCRIPTION)


def costs(cache):
    return inputs().costs(cache)


def parameters(cache):
    """Retained-only lookup; current SDK rotation cannot replace these inputs."""
    plan = inputs()
    for artifact in plan.artifacts:
        raw = source.retained(cache, artifact)
        if raw is None:
            raise source.BootstrapRequired(plan, cache)
        check(source._sha(raw) == MEMBER_SHA256[artifact.role])
    parameters = source.resolve_retained(plan, cache)
    return parameters.key, parameters.iv


def acquire(cache, *, fetch):
    """Explicitly planned historical inputs, with no latest metadata request."""
    for artifact in inputs().artifacts:
        source.acquire(cache, artifact, fetch=fetch)
    return parameters(cache)
