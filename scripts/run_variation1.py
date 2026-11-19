#!/usr/bin/env python3
"""Run a balanced, interleaved V1 batch after clean smoke tests.

Uses PGG_BASE_URL / PGG_API_KEY, just like run_batch.py. Never resumes a
partially written game (the core runner would append duplicate rounds).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
import threading
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pgg.config import load_run_config
from pgg.engine import Game
from pgg.health import load_game, run_health
from pgg.llm.client import LLMClient
from pgg.runner import run_game


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-id', required=True)
    p.add_argument('--games', type=int, default=10)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--smoke-suffix', default='20261113_4096')
    args = p.parse_args()
    if args.games < 1 or args.workers < 1:
        p.error('games and workers must be positive')
    models = ['gpt-5.6-sol', 'gpt-6-luna']
    configs = {(m, a): load_run_config(str(ROOT / f'configs/v1_local/{a}_{m}.yaml'))
               for m in models for a in ('known', 'unknown')}
    tasks = [(m, a, i) for i in range(args.games) for m in models for a in ('known', 'unknown')]
    calls = sum(Game(configs[m, a].game, [f'P{i}' for i in range(1, 6)], configs[m, a].seed+k).total_rounds * 15
                for m, a, k in tasks)
    print(json.dumps({'games': len(tasks), 'action_calls_before_retries': calls}), flush=True)
    if args.dry_run:
        return
    for m in models:
        smoke = ROOT / f'runs/v1_smoke_{m}_{args.smoke_suffix}/game_0000'
        h = run_health(load_game(str(smoke)))
        if not h['finished'] or not h['calls'] or h['fallback_rate']:
            raise RuntimeError(f'Smoke test not clean: {m}')
    # Check all partial directories before any model calls.
    dest = ROOT / 'runs' / args.run_id
    for m, a, k in tasks:
        d = dest / f'{a}_{m}' / f'game_{k:04d}'
        if d.exists() and any(d.iterdir()) and not (d / 'summary.json').exists():
            raise RuntimeError(f'Partial game requires a new run-id: {d}')
    client = LLMClient(timeout_s=90, max_retries=1)
    served = set(client.list_models())
    if not set(models) <= served:
        raise RuntimeError('Required models not served')
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / 'manifest.json'
    sources = list((ROOT/'pgg').rglob('*.py')) + list((ROOT/'pgg/prompts').glob('*.md')) + list((ROOT/'configs/v1_local').glob('*.yaml')) + [Path(__file__)]
    hashes = {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}
    manifest = {'models': models, 'games_per_condition': args.games, 'action_calls_before_retries': calls,
                'source_sha256': hashes, 'configs': {f'{a}_{m}': c.model_dump() for (m,a),c in configs.items()}}
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise RuntimeError('Run manifest differs; use a new run-id')
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2))
        for f in sources:
            snapshot = dest / 'source_snapshot' / f.relative_to(ROOT)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(f.read_bytes())
    stopped = threading.Event()
    operational_lock = threading.Lock()
    original_chat = client.chat

    def guarded_chat(*pos, **kw):
        if stopped.is_set():
            raise RuntimeError('Batch stopped before next API request')
        result = original_chat(*pos, **kw)
        error = (result.error or '').lower()
        if any(code in error for code in ('usage_limit_reached', 'model_cooldown', 'insufficient_quota')):
            stopped.set()
            # Preserve the operational failure before aborting the incomplete
            # game. Never convert an exhausted account into game decisions.
            with operational_lock:
                with (dest/'operational_errors.jsonl').open('a') as f:
                    f.write(json.dumps({'time':datetime.now(timezone.utc).isoformat(),
                                        'model':result.model,'error':result.error})+'\n')
            raise RuntimeError('Provider usage limit reached; incomplete game retained for audit')
        return result

    client.chat = guarded_chat

    def one(task):
        m,a,k = task
        if stopped.is_set():
            return
        label = f'{a}_{m}/game_{k:04d}'
        def event(kind, data):
            if kind == 'progress' and stopped.is_set():
                raise RuntimeError('Stopped after a fallback in another game')
            if kind == 'round':
                r = data['round']
                fb = sum(r['contribution_fallbacks'].values()) + sum(x['fallback_used'] for x in r['messages'] + r['punishments'])
                print(f'{label}: round {r["round"]} fallbacks={fb}', flush=True)
                # Do not raise here: the runner must first flush the call logs.
                if fb:
                    stopped.set()
        c = configs[m,a]
        try:
            run_game(c, f'game_{k:04d}', c.seed+k, str(dest/f'{a}_{m}'),
                     agent_kind='llm', client=client, phase_workers=5, on_event=event)
            h = run_health(load_game(str(dest/label)))
            print(f'{label}: COMPLETE calls={h["calls"]} fallback_rate={h["fallback_rate"]}', flush=True)
            if h['fallback_rate']:
                stopped.set()
        except Exception:
            stopped.set()
            raise
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(one, t) for t in tasks]
        errors = []
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                errors.append(str(exc))
    if stopped.is_set():
        raise RuntimeError(f'Batch stopped for quality review: {errors}')
    print('All V1 games complete.', flush=True)


if __name__ == '__main__':
    main()
