"""Read-only verification before reusing an already installed environment."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys

from packaging.requirements import Requirement


def compatible(path: Path) -> bool:
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            if version(requirement.name) not in requirement.specifier:
                return False
        except PackageNotFoundError:
            return False
    return True


if __name__ == '__main__':
    raise SystemExit(0 if compatible(Path(sys.argv[1])) else 1)
