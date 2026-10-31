"""Review-host-only R19 receipt consistency; never launches the candidate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.r19_acceptance import AcceptanceError, decode, review, template


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--manifest', type=Path)
    p.add_argument('--evidence-root', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--template', action='store_true')
    args = p.parse_args()
    try:
        if args.template:
            if args.manifest or args.evidence_root: raise AcceptanceError('Template mode does not consume receipts.')
            result = template(args.inventory.read_bytes())
        else:
            if args.manifest is None or args.evidence_root is None: raise AcceptanceError('Review needs a manifest and evidence root.')
            result = review(args.inventory.read_bytes(), decode(args.manifest.read_bytes()), args.evidence_root)
        for part in (args.output, *args.output.absolute().parents):
            if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
                raise AcceptanceError('Output cannot use links or reparse points.')
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
    except (AcceptanceError, OSError):
        print('R19 evidence is unavailable, inconsistent or output already exists; no acceptance was granted.', file=sys.stderr)
        return 2
    print('R19 evidence template written.' if args.template else 'R19 receipt consistency reviewed; no runtime promotion granted.')
    return 0 if args.template or result['ready_for_independent_acceptance_review'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
