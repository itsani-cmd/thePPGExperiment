#!/usr/bin/env python3
"""Game-level V1 estimates; bootstrap games, never agent-rounds."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pgg.health import load_game, run_health


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def estimate(xs, seed=20261113):
    xs = [x for x in xs if x is not None]
    if not xs:
        return {'n': 0, 'mean': None, 'ci95': None}
    if len(xs) < 2:
        return {'n': len(xs), 'mean': mean(xs), 'ci95': None}
    rng = random.Random(seed)
    boots = sorted(mean(rng.choices(xs, k=len(xs))) for _ in range(5000))
    return {'n': len(xs), 'mean': mean(xs), 'ci95': [boots[124], boots[4874]]}


def describe(path):
    path = path.resolve()
    g = load_game(str(path))
    health = run_health(g)
    if not health['finished']:
        return None
    rounds = g['rounds']
    cfg = g['config']
    expected = cfg['sampled_total_rounds']
    if [r['round'] for r in rounds] != list(range(1, expected+1)):
        raise ValueError(f'Missing or duplicate rounds: {path}')
    summary = json.loads((path/'summary.json').read_text())
    fracs = [mean([r['contributions'][s]/b for s,b in r['balances_before_contribution'].items() if b>0]) for r in rounds]
    absolute = [mean(list(r['contributions'].values())) for r in rounds]
    late = fracs[9]-mean(fracs[6:9]) if len(fracs)>=10 and fracs[9] is not None and mean(fracs[6:9]) is not None else None
    final = fracs[-1]-mean(fracs[1:-1]) if len(fracs)>=3 and fracs[-1] is not None and mean(fracs[1:-1]) is not None else None
    m = summary['metrics']
    return {'path': str(path.relative_to(ROOT)), 'seed': cfg['seed'], 'rounds': len(rounds),
            'model': next(iter(cfg['models'].values()))['model'],
            'arm': 'known' if cfg['game_config']['horizon']['mode']=='fixed' else 'unknown',
            'health': health, 'fraction_by_round': fracs, 'tokens_by_round': absolute,
            'mean_fraction': mean(fracs), 'round10_change': late, 'realized_end_change': final,
            'zero_contribution_rate': m['free_rider_rate']['zero'],
            'below_25pct_rate': m['free_rider_rate']['below_threshold'],
            'punishment_frequency': m['punishment']['punishment_freq'],
            'punishment_targets': m['punishment_targets'],
            'capped': cfg['game_config']['horizon']['mode']=='geometric' and len(rounds)==cfg['game_config']['horizon']['max_rounds']}


def fmt(x):
    if x['mean'] is None:
        return 'NA (n=0)'
    ci = x['ci95']
    return f"{x['mean']:.3f}" + (f" [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ' [CI unavailable]') + f" (n={x['n']})"


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run_dir', type=Path)
    p.add_argument('--output', type=Path, default=ROOT/'results/variation1')
    args = p.parse_args()
    manifest_path = args.run_dir/'manifest.json'
    planned = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        planned = len(manifest['models'])*2*manifest['games_per_condition']
    games = [describe(p.parent) for p in sorted(args.run_dir.glob('*/game_*/config.json'))]
    games = [g for g in games if g is not None]
    groups = defaultdict(list)
    for g in games:
        if g['health']['fallback_rate']==0 and g['health']['calls']>0:
            groups[g['model'],g['arm']].append(g)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    metrics = ['mean_fraction','round10_change','realized_end_change','zero_contribution_rate','below_25pct_rate','punishment_frequency']
    stats = {f'{m}/{a}': {k:estimate([g[k] for g in gs]) for k in metrics} for (m,a),gs in groups.items()}
    paired = {}
    for model in sorted({g['model'] for g in games}):
        known = {g['seed']: g for g in groups[model,'known']}
        unknown = {g['seed']: g for g in groups[model,'unknown']}
        deltas = [known[s]['round10_change']-unknown[s]['round10_change'] for s in known.keys() & unknown.keys()
                  if known[s]['round10_change'] is not None and unknown[s]['round10_change'] is not None]
        paired[model] = estimate(deltas)
    (output/'analysis.json').write_text(json.dumps({'games':games,'estimates':stats,'paired_round10_contrast_known_minus_unknown':paired},indent=2))
    status = 'FINAL BATCH' if planned is not None and len(games)==planned else 'INTERIM / INCOMPLETE BATCH'
    lines = ['# Variation 1 results', '', f'Status: {status}. Planned games: {planned if planned is not None else "unspecified"}.',
             f'Completed games: {len(games)}. Clean games: {sum(map(len,groups.values()))}.',
             f"Calls in completed games only (including excluded games): {sum(g['health']['calls'] for g in games)}. Reported API tokens for those games: {sum(g['health']['total_tokens'] for g in games)}. Incomplete attempts and smoke tests are not included in these usage counts.", '',
             'Values are game-level means with percentile bootstrap 95% intervals (5,000 resamples). Fraction measures run from 0 to 1.', '',
             '| Model / arm | Games | Mean contribution fraction | Round 10 minus rounds 7–9 | Punishment frequency |',
             '|---|---:|---|---|---|']
    for (m,a), gs in sorted(groups.items()):
        if not gs:
            continue
        st=stats[f'{m}/{a}']
        lines.append(f"| {m} / {a} | {len(gs)} | {fmt(st['mean_fraction'])} | {fmt(st['round10_change'])} | {fmt(st['punishment_frequency'])} |")
    lines += ['', '## Endgame contrast', '', 'Matched-seed difference in round-10 change, known minus unknown. Only pairs reaching round 10 with valid fraction measurements enter this contrast. Negative values indicate a larger endgame decline with a known endpoint.', '']
    lines += [f'- {m}: {fmt(e)}' for m,e in paired.items()]
    lines += ['', '## Free riding and punishment targets', '',
              '| Model / arm | Zero contributions | Below 25% | Low-contributor targets | High-contributor targets | All punishment actions |',
              '|---|---|---|---:|---:|---:|']
    for (m,a), gs in sorted(groups.items()):
        if not gs:
            continue
        st = stats[f'{m}/{a}']
        low = sum(g['punishment_targets']['counts']['low_contributor'] for g in gs)
        high = sum(g['punishment_targets']['counts']['high_contributor'] for g in gs)
        total = sum(g['punishment_targets']['total'] for g in gs)
        lines.append(f"| {m} / {a} | {fmt(st['zero_contribution_rate'])} | {fmt(st['below_25pct_rate'])} | {low} | {high} | {total} |")
    lines += ['', 'Target counts are descriptive pooled counts; targets are classified relative to the within-round median token contribution, following the repository metric. Frequency estimates above use games as the statistical unit.']
    lines += ['', '## Interpretation limits', '',
              '- Models share one provider and are identified by requested proxy model names; hidden routing or model revisions cannot be independently verified.',
              '- Unknown-end games have a hidden 30-round cap. Capped games: '+str(sum(g['capped'] for g in games))+'.',
              '- Unknown-end lengths vary; curves show only surviving games. Do not treat a random realized endpoint as an anticipated final round.',
              '- Balances compound from 20 starting tokens. Contribution fractions exclude seats with zero balance; a round with no solvent seats is missing, not zero.',
              '- Group means weight games equally. Known versus unknown full-game means also reflect differing duration; the round-10 contrast is more specific to the research question.',
              '- The below-25% free-rider rate follows the repository metric: its denominator includes zero-balance seats, although their fraction is undefined.',
              '- Fallback-contaminated games are listed in analysis.json and excluded from estimates. Retry counts and API errors remain visible in health records.',
              '- Bootstrap intervals with few eligible games are unstable. These are exploratory results; no causal claim about human values follows from token behavior.', '']
    (output/'REPORT.md').write_text('\n'.join(lines))
    # Auditable qualitative material, not automated claims about internal motives.
    excerpts = ['# V1 endgame excerpts', '',
                'All public messages and private contribution rationales at round 10 in completed clean games. These are model-produced statements, not verified explanations of internal reasoning. No keyword-based norm labels are assigned.', '']
    for g in games:
        if g['health']['fallback_rate'] or g['rounds'] < 10:
            continue
        loaded = load_game(str(ROOT/g['path']))
        excerpts += [f"## {g['model']} / {g['arm']} / seed {g['seed']}", '']
        for msg in loaded['rounds'][9]['messages']:
            excerpts.append(f"- Public {msg['seat']}: {msg['text']}")
        for call in loaded['calls']:
            if call['round'] == 10 and call['phase'] == 'contribute' and call.get('parsed_output') and not call.get('error'):
                parsed = call['parsed_output']
                excerpts.append(f"- Private {call['seat']}, contribution={parsed.get('contribution')}: {parsed.get('reason', '')}")
        excerpts.append('')
    (output/'ENDGAME_EXCERPTS.md').write_text('\n'.join(excerpts))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(2,2,figsize=(12,7),sharex='col',gridspec_kw={'height_ratios':[3,1]})
        for j,m in enumerate(sorted({g['model'] for g in games})):
            for a,color in [('known','#2563eb'),('unknown','#e67e22')]:
                gs=groups[m,a]
                n=max((g['rounds'] for g in gs),default=0)
                es=[estimate([g['fraction_by_round'][r] for g in gs if g['rounds']>r]) for r in range(n)]
                xs=list(range(1,n+1))
                ys=[e['mean'] if e['mean'] is not None else float('nan') for e in es]
                axs[0,j].plot(xs,ys,label=a,color=color,marker='.',lw=1.5)
                lo=[e['ci95'][0] if e['ci95'] else float('nan') for e in es]
                hi=[e['ci95'][1] if e['ci95'] else float('nan') for e in es]
                axs[0,j].fill_between(xs,lo,hi,color=color,alpha=.15)
                axs[1,j].step(xs,[e['n'] for e in es],where='mid',color=color,label=a)
            axs[0,j].set(title=m,ylim=(-.03,1.03),ylabel='Mean contribution / available balance')
            axs[0,j].legend()
            axs[1,j].set(xlabel='Round',ylabel='Valid games')
            for ax in axs[:,j]:
                ax.axvline(10,color='gray',ls=':',lw=1)
                ax.grid(alpha=.2)
        fig.suptitle('V1: known versus unknown endpoint | game-bootstrap 95% intervals')
        fig.tight_layout()
        fig.savefig(output/'contributions.png',dpi=180)
        plt.close(fig)
    except ImportError:
        print('Matplotlib unavailable; numerical outputs saved.')
    print(output/'REPORT.md')


if __name__=='__main__':
    main()
