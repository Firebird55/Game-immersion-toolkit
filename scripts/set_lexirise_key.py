"""Save a Lexirise API key for this Windows user without command-line exposure."""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from backend.lexirise import save_api_key


def main() -> None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise SystemExit("LOCALAPPDATA is unavailable on this computer.")
    key = getpass.getpass("Lexirise API key (hidden): ").strip()
    if not key.startswith("lx_") or len(key) < 20:
        raise SystemExit("That does not look like a Lexirise API key.")
    save_api_key(Path(local) / "Programs" / "Proxy Transcript", key)
    print("Lexirise key saved for this Windows user.")


if __name__ == "__main__":
    main()
