"""Wealth by persona per round, messages on vs off, both models (v2 run001). Writes an SVG to docs/figures/.

Wealth = tokens held at the end of the round (balances_after_punishment; reward is off in v2).
Round 0 is the 20-token start.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
SEAT = {"P1": "good_samaritan", "P2": "follower", "P3": "selfish", "P4": "socialist", "P5": "flaky"}
PERSONAS = ["good_samaritan", "socialist", "follower", "flaky", "selfish"]  # same order as fig2
COLOR = {"good_samaritan": "#2a78d6", "socialist": "#1f9d6b", "follower": "#8a5cc8", "flaky": "#8a8985", "selfish": "#eb6834"}
MODELS = ["chatgpt", "claude"]
CONDS = ["on", "off"]
LABEL = {"on": "Messages on", "off": "Messages off"}
INK, INK2, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
FONT = "-apple-system,Helvetica,Arial,sans-serif"


def wealth(cond, model):
    path = ROOT / "runs" / f"v2_comm_{cond}_run001_{model}" / "game_0000" / "rounds.jsonl"
    rounds = [json.loads(line) for line in path.open()]
    series = {SEAT[s]: [rounds[0]["balances_before_contribution"][s]] for s in SEAT}
    for r in rounds:
        for s in SEAT:
            series[SEAT[s]].append(r["balances_after_punishment"][s])
    return series


def text(x, y, s, size=12, fill=INK2, anchor="start", weight="normal"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" font-family="{FONT}">{s}</text>')


def main():
    data = {(c, m): wealth(c, m) for c in CONDS for m in MODELS}
    ymax = max(max(max(v) for v in s.values()) for s in data.values())
    ymax = -(-ymax // 10) * 10
    w, h = 900, 700
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Tokens held by each persona at the end of each round, messages on vs off, for each model"><rect width="{w}" height="{h}" fill="{BG}"/>',
        text(24, 28, "Selfish finishes last only when messages are off", 16, INK, weight="600"),
        text(24, 48, "Tokens each persona holds at the end of each round, after punishment. Everyone starts with 20."),
    ]
    for i, p in enumerate(PERSONAS):
        x = 24 + i * 140
        parts.append(f'<rect x="{x}" y="61" width="12" height="12" rx="2" fill="{COLOR[p]}"/>' + text(x + 18, 72, p.replace("_", " ")))
    pw, ph = 330, 220
    for ri, m in enumerate(MODELS):
        for ci, c in enumerate(CONDS):
            x0, top = 60 + ci * 440, 130 + ri * 290
            x1, bot = x0 + pw, top + ph
            parts.append(text(x0, top - 14, f"{m}, {LABEL[c].lower()}", 13, INK, weight="600"))
            for v in range(0, ymax + 1, 10):
                y = bot - ph * v / ymax
                parts.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>' + text(x0 - 6, y + 4, v, 11, anchor="end"))
            xs = lambda k: x0 + pw * k / 10
            for k in (0, 5, 10):
                parts.append(text(f"{xs(k):.1f}", bot + 18, f"R{k}" if k else "Start", 11, anchor="middle"))
            series = data[c, m]
            for p in PERSONAS:
                pts = [(xs(k), bot - ph * v / ymax) for k, v in enumerate(series[p])]
                sw = 3 if p == "selfish" else 1.75
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                parts.append(f'<polyline points="{d}" fill="none" stroke="{COLOR[p]}" stroke-width="{sw}" stroke-linejoin="round"/>')
                for (x, y), v in zip(pts, series[p]):
                    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{COLOR[p]}" stroke="{BG}" stroke-width="1.5"><title>{m}, {LABEL[c].lower()}, {p}: {v}</title></circle>')
            # end-of-game values, nudged apart so ties stay readable
            ends = sorted(PERSONAS, key=lambda p: series[p][-1])
            last_y = None
            for p in ends:
                y = bot - ph * series[p][-1] / ymax + 4
                if last_y is not None and last_y - y < 12:
                    y = last_y - 12
                last_y = y
                parts.append(text(f"{x1 + 8:.1f}", f"{y:.1f}", series[p][-1], 11, COLOR[p] if p != "flaky" else INK2, weight="600"))
            parts.append(text((x0 + x1) / 2, bot + 36, "Round", 11, anchor="middle"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fig10_wealth_by_persona_by_round.svg").write_text("\n".join(parts + ["</svg>"]) + "\n")
    print("wrote", OUT / "fig10_wealth_by_persona_by_round.svg")


if __name__ == "__main__":
    main()
