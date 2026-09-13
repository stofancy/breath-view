"""Export local decoder results for an independent OSCAR comparison (private output)."""
import argparse
from collections import Counter
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage import DEFAULT_HOME, load


def export(home, dates):
    dataset = load(home)
    if dataset is None:
        raise ValueError('没有已导入的数据')
    rows = []
    for date in dates:
        detail = dataset.detail(date)
        origin = datetime.fromisoformat(date) + timedelta(hours=12)
        rows.append({
            'date': date,
            'current': detail['current'],
            'summary_minutes': detail['minutes'],
            'event_counts': dict(Counter(e['kind'] for e in detail['events'])),
            'events': detail['events'],
            'retained_wave_seconds': detail['wave_seconds'],
            'duplicate_timestamps': detail['duplicates'],
            'record_segments': [
                [(origin + timedelta(seconds=s)).isoformat() for s in segment]
                for segment in detail['segments']
            ],
            'stats': detail['stats'],
        })
    return {
        'snapshot': dataset.folder.name,
        'time_axis': 'device local clock; treatment day starts at noon; segment end exclusive',
        'event_time_precision': 'one minute; second is offset from treatment-day noon',
        'scope': 'Breath View output only; not an OSCAR validation result',
        'days': rows,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('dates', nargs='+')
    args = parser.parse_args()
    result = export(args.home, args.dates)
    # Do not include patient identifiers or raw data in the repository.
    with open(args.output, 'w', encoding='utf-8', opener=lambda path, flags: os.open(path, flags, 0o600)) as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write('\n')
    print(f'Exported {len(result["days"])} nights to {args.output}')
