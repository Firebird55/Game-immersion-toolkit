"""Compare extracted dependency file sizes with the original ZIP."""

import collections
import json
import sys
import zipfile
from pathlib import Path


root = Path(__file__).resolve().parent.parent
zip_path = Path(sys.argv[1])
prefix = "gamesenteneminer/"
missing = []
checked = 0

with zipfile.ZipFile(zip_path) as archive:
    for info in archive.infolist():
        if not info.filename.startswith(prefix + "node_modules/") or info.is_dir():
            continue
        relative = info.filename[len(prefix):]
        target = root / Path(relative)
        checked += 1
        try:
            actual_size = target.stat().st_size
        except FileNotFoundError:
            actual_size = None
        if actual_size != info.file_size:
            missing.append({"path": relative, "expected": info.file_size, "actual": actual_size})

groups = collections.Counter()
for item in missing:
    parts = item["path"].split("/")
    group = "/".join(parts[:3]) if len(parts) > 2 and parts[1].startswith("@") else "/".join(parts[:2])
    groups[group] += 1

result = {"checked": checked, "missingCount": len(missing), "groups": groups, "files": missing}
(root / "dependency-missing.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(f"Checked {checked} dependency files; missing or wrong size: {len(missing)}")
for name, count in groups.most_common(20):
    print(f"  {name}: {count}")
