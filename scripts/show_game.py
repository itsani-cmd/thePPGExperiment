#!/usr/bin/env python3
"""Print a readable transcript of a saved game.

Examples::

    python scripts/show_game.py runs/smoke/game_0000   # one game
    python scripts/show_game.py runs/smoke             # every game in a run
    python scripts/show_game.py                        # most recent game
"""

from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pgg.transcript import format_game  # noqa: E402


def _latest_game(root: str = "runs") -> str:
    games = glob.glob(os.path.join(root, "**", "rounds.jsonl"), recursive=True)
    if not games:
        sys.exit("No games found under runs/. Run a game first.")
    return os.path.dirname(max(games, key=os.path.getmtime))


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else _latest_game()
    if os.path.exists(os.path.join(target, "rounds.jsonl")):
        game_dirs = [target]
    else:
        game_dirs = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(target, "*", "rounds.jsonl")))
        if not game_dirs:
            sys.exit(f"No games found in {target}")
    for d in game_dirs:
        print(format_game(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
