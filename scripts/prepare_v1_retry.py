#!/usr/bin/env python3
"""Copy only completed, zero-fallback V1 games into a fresh retry attempt.

Failed/incomplete attempts stay untouched for audit. No API requests are made.
The new attempt records origins so copied games are not counted twice.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pgg.health import load_game,run_health


def main():
    p=argparse.ArgumentParser()
    p.add_argument('source',type=Path)
    p.add_argument('destination',type=Path)
    args=p.parse_args()
    if not (args.source/'manifest.json').exists():
        p.error('source must have a V1 manifest')
    if args.destination.exists():
        p.error('destination must be new')
    args.destination.mkdir(parents=True)
    retained=[]
    omitted=[]
    for cfg in sorted(args.source.glob('*/game_*/config.json')):
        health=run_health(load_game(str(cfg.parent)))
        relative=cfg.parent.relative_to(args.source)
        valid=health['finished'] and health['calls']>0 and health['fallback_rate']==0
        if valid:
            shutil.copytree(cfg.parent,args.destination/relative)
            retained.append(str(relative))
        else:
            omitted.append(str(relative))
    record={'source':str(args.source.resolve()),'retained':retained,'omitted':omitted,
            'reason':'Retain only completed games with real API calls and zero fallback actions; restart interrupted games from round 1 with their original seed.'}
    (args.destination/'recovery.json').write_text(json.dumps(record,indent=2))
    print(json.dumps({'retained':len(retained),'omitted':len(omitted),'destination':str(args.destination)}))


if __name__=='__main__':
    main()
