"""Save a Lexirise API key for this Windows user without command-line exposure."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from backend.lexirise import save_api_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", action="store_true", help="Add a verified named account without replacing the legacy key")
    args = parser.parse_args()
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise SystemExit("LOCALAPPDATA is unavailable on this computer.")
    key = getpass.getpass("Lexirise API key (hidden): ").strip()
    if not key.startswith("lx_") or len(key) < 20:
        raise SystemExit("That does not look like a Lexirise API key.")
    if args.account:
        from backend.accounts import AccountStore
        name = input("Account label (blank uses Lexirise name): ").strip()
        profile = AccountStore().add(key, name)
        print("Verified account added and selected: " + profile["name"])
        return
    save_api_key(Path(local) / "Programs" / "Proxy Transcript", key)
    print("Lexirise key saved for this Windows user.")


if __name__ == "__main__":
    main()
