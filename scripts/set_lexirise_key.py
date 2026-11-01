"""Save a Lexirise API key locally without command-line or browser exposure."""

from __future__ import annotations

import argparse
import getpass

from backend.lexirise import save_api_key
from backend.protected_storage import credential_directory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", action="store_true", help="Add a verified named account without replacing the legacy key")
    parser.add_argument('--gui', action='store_true', help='Use the native account dialog')
    args = parser.parse_args()
    if args.gui:
        from backend.native_setup import main as native_main
        raise SystemExit(native_main(['lexirise']))
    key = getpass.getpass("Lexirise API key (hidden): ").strip()
    if not key.startswith("lx_") or len(key) < 20:
        raise SystemExit("That does not look like a Lexirise API key.")
    if args.account:
        from backend.accounts import AccountStore
        name = input("Account label (blank uses Lexirise name): ").strip()
        profile = AccountStore().add(key, name)
        print("Verified account added and selected: " + profile["name"])
        return
    save_api_key(credential_directory(), key)
    print("Lexirise key saved for this desktop user.")


if __name__ == "__main__":
    main()
