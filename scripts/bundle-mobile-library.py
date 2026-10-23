"""Wrap an existing private export without decoding voices again."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.mobile_bundle import write_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path, help='Existing Catalog ZIP; matching voice ZIPs must be alongside it')
    parser.add_argument('--output', type=Path, required=True, help='Private destination folder outside the repository')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.resolve().is_relative_to(root):
        parser.error('Choose a private destination outside the repository')
    print(write_bundle(args.catalog, args.output))


if __name__ == '__main__':
    main()
