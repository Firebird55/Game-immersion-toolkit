"""Export mainland Chinese text from the snapshot matching the released NTE manifest."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.game_tools import _atomic_file
from backend.nte_regional_text import snapshot


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True, type=Path, help='Private directory for immutable source snapshots')
    parser.add_argument('--output', required=True, type=Path, help='Destination for the selected text and release identity')
    parser.add_argument('--namespace', help='Limit the export to one exact localization namespace')
    parser.add_argument('--key', action='append', default=[], help='Repeat for individual keys in the selected namespace')
    args = parser.parse_args()
    result = snapshot(args.cache, namespace=args.namespace, keys=args.key)
    _atomic_file(args.output, json.dumps(result, ensure_ascii=False).encode('utf-8'))
    print(f"NTE mainland {result['version']}: {sum(map(len, result['texts'].values())):,} Chinese text entries.")
