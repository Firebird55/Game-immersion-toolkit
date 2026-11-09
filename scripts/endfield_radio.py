"""List released Endfield radio sentence bindings or fetch one original WEM."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import endfield_assets as assets, endfield_release as publisher
from backend.dialogue_catalog import selected_tables
from backend.game_tools import _atomic_file


def run(cache, locale, groups, line, output, targets, reaction=None):
    catalog = publisher.prepare(cache)
    dialogs = assets.radio_dialogues(catalog)
    unknown = set(groups) - {r['radio_group'] for r in dialogs.values()}
    if unknown:
        raise ValueError('Unknown radio group: ' + ', '.join(sorted(unknown)))
    if groups:
        dialogs = {key: row for key, row in dialogs.items() if row['radio_group'] in groups}
    paths = assets.audio_paths(catalog.file('TableCfg/AudioDialog.json'))
    tables = selected_tables(catalog, assets.TEXT_LOCALES, locale, targets, prefix='TableCfg/I18nTextTable_')
    dub = assets.VOICE_LOCALES[locale]
    entries = publisher.voice_entries(cache, catalog.stamp, dub)
    report = []
    chosen = None
    for key, dialog in dialogs.items():
        rows = assets.dialogue_records({key: dialog}, paths, tables, locale, entries)
        if not rows and line is None:
            report.append({'group': dialog['radio_group'], 'id': 'endfield:' + key, 'status': 'missing_study_text'})
        for row in rows:
            if line is not None and row['text_id'] != line:
                continue
            entry = {'group': row['radio_group'], 'id': row['text_id'], 'status': row['radio_sentence']}
            if 'radio_reaction_configured' in row:
                entry.update(emotion=row['radio_emotion_type'], reaction_configured=row['radio_reaction_configured'])
            if row.get('radio_reaction_candidates'):
                entry['voice_actor'] = row['radio_voice_actor']
                entry['reaction_candidates'] = list(row['radio_reaction_candidates'])
            if row['audio']:
                entry['file_id'] = row['audio']['file_id']
            if line is not None:
                entry['texts'] = row['texts']
                chosen = row
            report.append(entry)
    if line is not None and chosen is None:
        raise ValueError('Unknown or untranslated radio performance for this selection.')
    data = None
    if output:
        if reaction:
            source = chosen.get('radio_reaction_candidates', {}).get(reaction) if chosen else None
            if not source:
                raise ValueError('This reaction is absent from the selected row and dub.')
            data = publisher.media(cache, catalog.stamp, dub, assets.voice_hash(source))
            report[0]['exported_reaction'] = reaction
        elif chosen and chosen['audio']:
            data = publisher.extract(cache, chosen['audio'], dub)
        else:
            raise ValueError('The selected line has no verified sentence recording in this dub.')
    if publisher.discover()[0] != catalog.stamp:
        raise ValueError('The released resources changed during the request. Retry.')
    if output:
        _atomic_file(output, data)
    return {'version': catalog.revision_title, 'revision': catalog.stamp, 'locale': locale, 'rows': report}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True, help='Private directory for publisher files')
    parser.add_argument('--locale', choices=assets.SUPPORTED_LOCALES, required=True)
    parser.add_argument('--target', choices=assets.TEXT_LOCALES, action='append', default=[])
    parser.add_argument('--group', action='append', default=[], help='Repeat to limit the inventory to selected groups')
    parser.add_argument('--line', help='Exact performance ID from the inventory, including any gender suffix')
    parser.add_argument('--wem', type=Path, help='Save the selected performance as original Wwise audio')
    parser.add_argument('--reaction', help='Export this listed reaction candidate separately from sentence audio')
    args = parser.parse_args()
    if args.wem and not args.line:
        parser.error('--wem requires --line')
    if args.reaction and not args.wem:
        parser.error('--reaction requires --line and --wem')
    print(json.dumps(run(args.cache.resolve(), args.locale, args.group, args.line, args.wem, args.target, args.reaction),
                     ensure_ascii=True, indent=2))
