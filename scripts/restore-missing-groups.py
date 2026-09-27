"""Restore only missing Node package files from the original ZIP.

Unlike tar extraction of whole package groups, this leaves already verified
files alone and reports a monotonic percentage of the missing file count.
"""

import json
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


root = Path(__file__).resolve().parent.parent
zip_path = Path(sys.argv[1])
missing = json.loads((root / "dependency-missing.json").read_text(encoding="utf-8"))["files"]
status_path = root / "dependency-restore-progress.json"
prefix = "gamesenteneminer/"
total = len(missing)
done = 0
bytes_done = 0
bytes_total = sum(item["expected"] for item in missing)
last_written = 0.0
last_reported = -1


def report(phase: str, error: str | None = None) -> None:
    global last_written, last_reported
    percent = round(100 * done / total, 1) if total else 100.0
    status = {
        "phase": phase,
        "percent": percent,
        "bytesDone": bytes_done,
        "bytesTotal": bytes_total,
        "entriesDone": done,
        "entriesTotal": total,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        status["error"] = error
    temporary = status_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(status), encoding="utf-8")
    temporary.replace(status_path)
    if int(percent) >= last_reported + 5 or phase != "restoring missing files":
        print(f"Dependency repair: {percent}% ({done}/{total} files) - {phase}", flush=True)
        last_reported = int(percent)
    last_written = time.monotonic()


report("restoring missing files")
try:
    with zipfile.ZipFile(zip_path) as archive:
        for item in missing:
            relative = Path(item["path"])
            target = (root / relative).resolve()
            if not target.is_relative_to(root.resolve()) or relative.parts[0] != "node_modules":
                raise ValueError(f"Unsafe dependency path: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(prefix + relative.as_posix()) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            if target.stat().st_size != item["expected"]:
                raise IOError(f"Restored size mismatch: {relative}")
            done += 1
            bytes_done += item["expected"]
            if done % 25 == 0 or time.monotonic() - last_written >= 2:
                report("restoring missing files")
except Exception as exc:
    report("failed", str(exc))
    raise

report("complete")
