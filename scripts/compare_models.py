#!/usr/bin/env python3
"""Compare models side by side for one run of a variation.

Examples::

    python scripts/compare_models.py v2_comm_on            # latest run
    python scripts/compare_models.py v2_comm_on --run 2    # run002

Reads runs/<variation>_run<NNN>_<model>/ folders written by run_batch.py.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgg.health import game_report  # noqa: E402
from summarize_runs import _f, _game_dirs, _mean  # noqa: E402


def _find(variation, root, run):
    pat = re.compile(rf"^{re.escape(variation)}_run(\d+)_(.+)$")
    found = {}
    for d in os.listdir(root) if os.path.isdir(root) else []:
        if m := pat.match(d):
            found.setdefault(int(m.group(1)), {})[m.group(2)] = os.path.join(root, d)
    if not found:
        sys.exit(f"No runs named {variation}_run<NNN>_<model> under {root}/")
    n = run or max(found)
    if n not in found:
        sys.exit(f"{variation}_run{n:03d} not found; have runs {sorted(found)}")
    return n, found[n]


def _overall(reports):
    h = [r["health"] for r in reports]
    dyn = [r["dynamics"] for r in reports if r["dynamics"]]
    return {
        "games": len(reports),
        "finished": sum(bool(x["finished"]) for x in h),
        "fallback rate": _mean([x["fallback_rate"] for x in h]),
        "call error rate": _mean([x["call_error_rate"] for x in h]),
        "tokens / game": _mean([x["total_tokens"] for x in h]),
        "mean contribution": _mean([_mean(d["mean_fraction_by_round"]) for d in dyn]),
        "cooperation slope": _mean([d["cooperation_slope"] for d in dyn]),
        "efficiency": _mean([d["efficiency"] for d in dyn]),
        "final Gini": _mean([d["gini_final"] for d in dyn]),
        "tokens destroyed": _mean([d["tokens_destroyed_by_punishment"] for d in dyn]),
        "settles at round": _mean([d["converged_round"] for d in dyn]),
    }


def _by_persona(reports):
    """Persona definition (personas/defs) -> mean contribution, pooled over games and seats.

    Seats configured with persona/principal null get no persona text; they are
    grouped under "baseline (no persona)".
    """
    vals = defaultdict(list)
    for r in reports:
        for p in r["personas"].values():
            name = "baseline (no persona)" if p["persona"] in (None, "none") else p["persona"]
            vals[name].append(p["mean_fraction"])
    return {k: _mean(v) for k, v in vals.items()}


def _fmt(v, key=""):
    if key == "tokens / game":
        return "-" if v is None else f"{v:.0f}"
    return str(v) if isinstance(v, int) else _f(v)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("variation", help="config name, e.g. v2_comm_on")
    ap.add_argument("--run", type=int, default=None, help="run number (default: latest)")
    ap.add_argument("--runs-root", default="runs")
    a = ap.parse_args(argv)

    n, paths = _find(a.variation, a.runs_root, a.run)
    reports = {m: [game_report(d) for d in _game_dirs([p])] for m, p in sorted(paths.items())}
    reports = {m: r for m, r in reports.items() if r}
    if not reports:
        sys.exit("Run folders found, but they contain no games.")
    models = list(reports)

    print(f"{a.variation} run{n:03d}\n")
    print(f"{'':<24}" + "".join(f"{m:<14}" for m in models))
    overall = {m: _overall(r) for m, r in reports.items()}
    for key in overall[models[0]]:
        print(f"{key:<24}" + "".join(f"{_fmt(overall[m][key], key):<14}" for m in models))

    personas = {m: _by_persona(r) for m, r in reports.items()}
    names = sorted({p for d in personas.values() for p in d})
    if names != ["baseline (no persona)"]:
        print("\nmean contribution by persona definition (personas/defs)")
        for p in names:
            print(f"{p:<24}" + "".join(f"{_f(personas[m].get(p)):<14}" for m in models))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
