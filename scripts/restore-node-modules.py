"""Restore USB dependencies from the source ZIP with progress reporting."""

import json
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


root = Path(__file__).resolve().parent.parent
archive_path = Path(sys.argv[1])
status_path = root / "dependency-restore-progress.json"
prefix = "gamesenteneminer/"
selection = "gamesenteneminer/node_modules"

with zipfile.ZipFile(archive_path) as archive:
    entries = [info for info in archive.infolist() if info.filename.startswith(selection + "/")]
    lengths = {info.filename[len(prefix):]: info.file_size for info in entries}
    total_bytes = sum(lengths.values())

done_bytes = 0
done_entries = 0
last_update = 0.0
last_reported = -1
errors = []


def update(phase):
    global last_update, last_reported
    percent = round(100 * done_bytes / total_bytes, 1) if total_bytes else 100.0
    status = {
        "phase": phase,
        "percent": percent,
        "bytesDone": done_bytes,
        "bytesTotal": total_bytes,
        "entriesDone": done_entries,
        "entriesTotal": len(entries),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if errors:
        status["error"] = errors[-1]
    status_path.write_text(json.dumps(status), encoding="utf-8")
    if int(percent) >= last_reported + 5:
        print(f"Dependencies restored: {percent}% ({done_entries} / {len(entries)} entries)", flush=True)
        last_reported = int(percent)
    last_update = time.monotonic()


update("restoring")
process = subprocess.Popen(
    ["tar.exe", "-m", "-xvf", str(archive_path), "-C", str(root), "--strip-components=1", selection],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
    bufsize=1,
)
assert process.stdout is not None
for line in process.stdout:
    line = line.strip()
    if line.startswith("x "):
        name = line[2:].replace("\\", "/")
        if name in lengths:
            done_entries += 1
            done_bytes += lengths[name]
        elif name != "node_modules/" and len(errors) < 20:
            errors.append(f"Unmatched archive entry: {name}")
    elif line and len(errors) < 20:
        errors.append(line)
    if time.monotonic() - last_update >= 2:
        update("restoring")

exit_code = process.wait()
if exit_code or errors or done_bytes != total_bytes:
    if exit_code and not errors:
        errors.append(f"tar.exe exited with code {exit_code}")
    update("failed")
    raise SystemExit(errors[-1] if errors else "Dependency byte count did not match")

done_entries = len(entries)
update("complete")
