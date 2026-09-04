import argparse
import json
from pathlib import Path

from backend.agent_bank import bank_media, package_table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-data', type=Path, required=True)
    parser.add_argument('--avatars', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    en, zh = {}, {}
    for language, target in [('en', en), ('zh', zh)]:
        for suffix in ('base', 'overwrite'):
            target.update(json.loads((root / f'data/textmaps/{language}_{suffix}.json').read_text(encoding='utf-8')))
    banks, streams = {}, {}
    for layer in ('StreamingAssets', 'Persistent'):
        folder = args.game_data / layer / 'Audio/Windows/Full/Cn'
        for path in folder.glob('SoundBank*.pck'):
            banks.update(package_table(path, 2))
        for path in folder.glob('Streamed*.pck'):
            streams.update(package_table(path, 3))
    avatars = json.loads(args.avatars.read_text(encoding='utf-8'))
    agents = {}
    for rows in avatars.values():
        for row in rows:
            strings = [value for value in row.values() if isinstance(value, str)]
            names = [key for key in strings if key in en and key in zh and not key.endswith(('_En', '_FullName'))]
            voice_banks = [b for value in strings for b in value.split('|') if b.startswith('BK_') and b.endswith('_VO')]
            if not names or not voice_banks:
                continue
            name, chinese = en[names[0]], zh[names[0]]
            agents.setdefault(name, {'name': name, 'chinese_name': chinese, 'clips': {}})
    # Modern ZZZ uses auto-defined per-event banks, not one named bank per
    # character. Index their audio globally; the observed agent screen supplies
    # the selected character, never a guessed bank-name association.
    clips = {}
    media_entries = dict(streams)
    for bank in banks.values():
        for media_id, embedded in bank_media(bank).items():
            media_entries.setdefault(media_id, embedded)
    for media_id, media in media_entries.items():
        stat = media.package.stat()
        clips[str(media_id)] = {
            'package': str(media.package), 'offset': media.offset, 'size': media.size,
            'file_id': media_id, 'package_size': stat.st_size, 'package_mtime_ns': stat.st_mtime_ns,
        }
    output = root / 'data/agent-voices'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'library.json').write_text(json.dumps({'version': 1, 'agents': agents, 'clips': clips}, ensure_ascii=False), encoding='utf-8')
    print('Agents', len(agents), 'clips', len(clips))


if __name__ == '__main__':
    main()
