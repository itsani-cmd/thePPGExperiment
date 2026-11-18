"""Punishment and leaderboard figures, messages on vs off (v2 run001). Writes SVGs to docs/figures/.

Counts come straight from rounds.jsonl:
  damage = actual_damage (tokens taken from the target, after clamping at zero)
  cost   = tokens the punisher paid (spend minus refund)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
SEAT = {"P1": "good_samaritan", "P2": "follower", "P3": "selfish", "P4": "socialist", "P5": "flaky"}
PERSONAS = ["good_samaritan", "socialist", "follower", "flaky", "selfish"]  # same order as fig2
MODELS = ["chatgpt", "claude"]
CONDS = ["on", "off"]
COLOR = {"on": "#2a78d6", "off": "#eb6834"}
LABEL = {"on": "Messages on", "off": "Messages off"}
INK, INK2, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
FONT = "-apple-system,Helvetica,Arial,sans-serif"


def load(cond, model):
    path = ROOT / "runs" / f"v2_comm_{cond}_run001_{model}" / "game_0000" / "rounds.jsonl"
    return [json.loads(line) for line in path.open()]


def acts(rounds):
    return [p for r in rounds for p in r["punishments"] if p["target"]]


def text(x, y, s, size=12, fill=INK2, anchor="start", weight="normal"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" font-family="{FONT}">{s}</text>')


def header(w, h, aria, title, subtitle, legend=True):
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{aria}"><rect width="{w}" height="{h}" fill="{BG}"/>',
        text(24, 28, title, 16, INK, weight="600"),
        text(24, 48, subtitle),
        f'<rect x="24" y="61" width="12" height="12" rx="2" fill="{COLOR["on"]}"/>' + text(42, 72, LABEL["on"])
        + f'<rect x="144" y="61" width="12" height="12" rx="2" fill="{COLOR["off"]}"/>' + text(162, 72, LABEL["off"]),
    ]
    return parts if legend else parts[:3] + [""]


def save(name, parts):
    (OUT / name).write_text("\n".join(parts + ["</svg>"]) + "\n")
    print("wrote", OUT / name)


def fig_damage_by_round(data):
    w, h = 760, 380
    parts = header(w, h, "Tokens destroyed by punishment in each round, messages on vs off, for each model",
                   "Punishment damage drops off late in three games but not in claude with messages off",
                   "Tokens taken from punished players in each round. One game per line.")
    ymax, top, bot = 50, 116, 316
    for i, m in enumerate(MODELS):
        x0, x1 = 60 + i * 380, 360 + i * 380
        parts.append(text(x0, 106, m, 13, INK, weight="600"))
        for v in (0, 10, 20, 30, 40, 50):
            y = bot - (bot - top) * v / ymax
            parts.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>' + text(x0 - 6, y + 4, v, 11, anchor="end"))
        xs = lambda k: x0 + (x1 - x0) * (k - 1) / 9
        for k in (1, 5, 10):
            parts.append(text(f"{xs(k):.1f}", bot + 18, f"R{k}", 11, anchor="middle"))
        for c in CONDS:
            per = [sum(p["actual_damage"] for p in r["punishments"] if p["target"]) for r in data[c, m]]
            pts = [(xs(k + 1), bot - (bot - top) * v / ymax) for k, v in enumerate(per)]
            d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            parts.append(f'<polyline points="{d}" fill="none" stroke="{COLOR[c]}" stroke-width="2" stroke-linejoin="round"/>')
            for (x, y), v in zip(pts, per):
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLOR[c]}" stroke="{BG}" stroke-width="2"><title>{m}, {LABEL[c].lower()}: {v}</title></circle>')
            lx, ly = pts[-1]
            parts.append(text(f"{lx + 8:.1f}", f"{ly + 4:.1f}", per[-1], 11, INK))
        parts.append(text((x0 + x1) / 2, bot + 36, "Round", 11, anchor="middle"))
    parts.append(text(24, 368, "Totals over 10 rounds: " + ", ".join(
        f"{m} {c} {sum(p['actual_damage'] for p in acts(data[c, m]))}" for m in MODELS for c in CONDS) + ".", 11))
    save("fig3_punishment_damage_by_round.svg", parts)


def bar_panels(name, aria, title, subtitle, value_fn, vmax, ticks, fmt=str, tag_fn=None):
    w, h = 760, 420
    parts = header(w, h, aria, title, subtitle)
    for i, m in enumerate(MODELS):
        x0, x1 = 170 + i * 330, 400 + i * 330
        parts.append(text(x0, 96, m, 13, INK, weight="600"))
        for t in ticks:
            x = x0 + (x1 - x0) * t / vmax
            parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="104" y2="376" stroke="{GRID}"/>' + text(f"{x:.1f}", 392, t, 11, anchor="middle"))
        for j, persona in enumerate(PERSONAS):
            y = 104 + j * 56
            if i == 0:
                parts.append(text(158, y + 27, persona, anchor="end"))
            for k, c in enumerate(CONDS):
                v = value_fn(c, m, persona)
                bw = (x1 - x0) * v / vmax
                by = y + k * 20
                if bw > 0:
                    parts.append(f'<rect x="{x0}" y="{by}" width="{bw:.1f}" height="16" rx="3" fill="{COLOR[c]}"><title>{persona}, {m}, {LABEL[c].lower()}: {fmt(v)}</title></rect>')
                label = fmt(v)
                tag = tag_fn(c, m, persona) if tag_fn else ""
                parts.append(text(f"{x0 + bw + 6:.1f}", by + 12, label + (f" · {tag}" if tag else ""), 11, INK,
                                  weight="600" if tag else "normal"))
    save(name, parts)


def damage_received(rounds, persona):
    return sum(p["actual_damage"] for p in acts(rounds) if SEAT[p["target"]] == persona)


def actions_issued(rounds, persona):
    return sum(1 for p in acts(rounds) if SEAT[p["punisher"]] == persona)


def final_tokens(cond, model):
    path = ROOT / "runs" / f"v2_comm_{cond}_run001_{model}" / "game_0000" / "summary.json"
    outcomes = json.loads(path.read_text())["metrics"]["final_outcomes"]
    return {SEAT[k]: v["final_tokens"] for k, v in outcomes.items()}



def finish_tag(cond, model, persona):
    """'1st' / 'last' (with '=' for ties) for the top and bottom finishers; blank otherwise."""
    ft = final_tokens(cond, model)
    v = ft[persona]
    tied = sum(1 for x in ft.values() if x == v) > 1
    if v == max(ft.values()):
        return ("tied " if tied else "") + "1st"
    if v == min(ft.values()):
        return ("tied " if tied else "") + "last"
    return ""


def fig_selfish_fall():
    """Selfish seat's finishing place, messages on vs off, one panel per model."""
    w, h = 760, 330
    parts = header(w, h, "Selfish persona finishing place, messages on vs off, for each model",
                   "The selfish seat drops from the top to last place when messages are off",
                   "Finishing place out of 5 players after round 10, by tokens held. One game per model.", legend=False)
    top, step = 116, 38
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
    for i, m in enumerate(MODELS):
        xa, xb = 180 + i * 360, 300 + i * 360
        parts.append(text(xa - 140, 84, m, 13, INK, weight="600"))
        for k in range(1, 6):
            y = top + (k - 1) * step
            parts.append(f'<line x1="{xa - 140}" x2="{xb + 70}" y1="{y}" y2="{y}" stroke="{GRID}"/>')
        pts = {}
        for c, x in (("on", xa), ("off", xb)):
            ft = final_tokens(c, m)
            v = ft["selfish"]
            place = 1 + sum(1 for q in ft.values() if q > v)
            tied = sum(1 for q in ft.values() if q == v) > 1
            label = ("tied " if tied else "") + ordinal[place]
            pts[c] = (x, top + (place - 1) * step, label, v)
            parts.append(text(x, top + 4 * step + 30, LABEL[c], 11, anchor="middle"))
        (x1, y1, _, _), (x2, y2, _, _) = pts["on"], pts["off"]
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK2}" stroke-width="2"/>')
        for c, (x, y, label, v) in pts.items():
            parts.append(f'<circle cx="{x}" cy="{y}" r="7" fill="{COLOR[c]}" stroke="{BG}" stroke-width="2"><title>{m}, {LABEL[c].lower()}: selfish finishes {label} with {v} tokens</title></circle>')
            anchor, dx = ("end", -14) if c == "on" else ("start", 14)
            parts.append(text(x + dx, y - 2, label, 13, INK, anchor=anchor, weight="600"))
            parts.append(text(x + dx, y + 13, f"{v} tokens", 11, INK2, anchor=anchor))
    save("fig7_selfish_finishing_place.svg", parts)


def start_tokens(cond, model):
    path = ROOT / "runs" / f"v2_comm_{cond}_run001_{model}" / "game_0000" / "rounds.jsonl"
    first = json.loads(path.open().readline())
    return first["balances_before_contribution"][next(k for k, v in SEAT.items() if v == "selfish")]



def fig_selfish_start_to_final():
    """Selfish seat's final tokens next to the other four players' average, against the 20-token start."""
    w, h = 760, 400
    parts = header(w, h, "Selfish persona final tokens vs the other players' average, messages on vs off, for each model",
                   "The selfish seat ends above the others with messages on and far below them with messages off",
                   "Tokens held after round 10. Everyone starts with 20 (dashed line). One game per pair of bars.", legend=False)
    x0, x1, vmax = 170, 690, 20
    sx = lambda v: x0 + (x1 - x0) * v / vmax
    OTHERS = "#b9b8b3"
    top, axis_bot = 86, 354
    for t in (0, 5, 10, 15):
        parts.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{top}" y2="{axis_bot}" stroke="{GRID}"/>'
                     + text(f"{sx(t):.1f}", axis_bot + 16, t, 11, anchor="middle"))
    s20 = sx(start_tokens("on", "chatgpt"))
    parts.append(f'<line x1="{s20:.1f}" x2="{s20:.1f}" y1="{top}" y2="{axis_bot}" stroke="{INK2}" stroke-width="1.5" stroke-dasharray="4 4"/>'
                 + text(f"{s20:.1f}", axis_bot + 16, "20 (start)", 11, INK, anchor="middle"))
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
    y = top + 18
    for m in MODELS:
        parts.append(text(24, y, m, 13, INK, weight="600"))
        y += 12
        for c in CONDS:
            ft = final_tokens(c, m)
            v = ft["selfish"]
            others = [q for p_, q in ft.items() if p_ != "selfish"]
            avg = sum(others) / len(others)
            place = 1 + sum(1 for q in ft.values() if q > v)
            tied = sum(1 for q in ft.values() if q == v) > 1
            parts.append(text(x0 - 16, y + 23, LABEL[c], 12, anchor="end"))
            for k, (val, fill, lab, bold) in enumerate((
                    (v, COLOR[c], f"Selfish: {v} · {'tied ' if tied else ''}{ordinal[place]}", True),
                    (avg, OTHERS, f"Others' average: {avg:g}", False))):
                by = y + k * 20
                bw = sx(val) - x0
                if bw > 0:
                    parts.append(f'<rect x="{x0}" y="{by}" width="{bw:.1f}" height="16" rx="3" fill="{fill}"><title>{m}, {LABEL[c].lower()}: {lab}</title></rect>')
                parts.append(text(f"{x0 + bw + 6:.1f}", by + 12, lab, 11, INK if bold else INK2, weight="600" if bold else "normal"))
            y += 56
        y += 10
    save("fig8_selfish_start_to_final.svg", parts)

def fig_selfish_drop_from_start():
    """Chart 7 with a token axis: each line drops from the 20-token start to the selfish seat's final balance."""
    w, h = 760, 330
    parts = header(w, h, "Selfish persona tokens from start to round 10, messages on vs off, for each model",
                   "The selfish seat ends at the top with messages on and last with messages off",
                   "Every player starts with 20 tokens. Labels give the selfish seat's final place out of 5 and tokens. One game per line.")
    top, bot, vmax = 112, 292, 20
    sy = lambda v: bot - (bot - top) * v / vmax
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
    for i, m in enumerate(MODELS):
        xa, xb = 110 + i * 370, 250 + i * 370
        parts.append(text(xa - 70, 100, m, 13, INK, weight="600"))
        for t in (0, 5, 10, 15, 20):
            parts.append(f'<line x1="{xa - 40}" x2="{xb + 120}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{GRID}"/>'
                         + text(xa - 46, f"{sy(t) + 4:.1f}", t, 11, anchor="end"))
        parts.append(text(xa, bot + 20, "Start", 11, anchor="middle"))
        parts.append(text(xb, bot + 20, "After round 10", 11, anchor="middle"))
        s0 = start_tokens("on", m)
        for c in CONDS:
            ft = final_tokens(c, m)
            v = ft["selfish"]
            place = 1 + sum(1 for q in ft.values() if q > v)
            tied = sum(1 for q in ft.values() if q == v) > 1
            label = f"{'tied ' if tied else ''}{ordinal[place]} · {v} tokens"
            parts.append(f'<line x1="{xa}" y1="{sy(s0):.1f}" x2="{xb}" y2="{sy(v):.1f}" stroke="{COLOR[c]}" stroke-width="2"/>')
            parts.append(f'<circle cx="{xb}" cy="{sy(v):.1f}" r="6" fill="{COLOR[c]}" stroke="{BG}" stroke-width="2"><title>{m}, {LABEL[c].lower()}: selfish ends {label}</title></circle>')
            parts.append(text(xb + 12, f"{sy(v) + 4:.1f}", label, 12, INK, weight="600"))
        parts.append(f'<circle cx="{xa}" cy="{sy(s0):.1f}" r="6" fill="{INK2}" stroke="{BG}" stroke-width="2"><title>{m}: every player starts with {s0} tokens</title></circle>')
        parts.append(text(xa + 10, f"{sy(s0) - 8:.1f}", f"{s0} tokens", 11, INK2))
    save("fig9_selfish_drop_from_start.svg", parts)


def main():
    data = {(c, m): load(c, m) for c in CONDS for m in MODELS}
    fig_damage_by_round(data)
    fig_selfish_fall()
    fig_selfish_start_to_final()
    fig_selfish_drop_from_start()
    bar_panels("fig4_punishment_received_by_persona.svg",
               "Tokens lost to punishment by persona, messages on vs off, for each model",
               "Without messages, the selfish seat takes more of the punishment in both models",
               "Total tokens taken from each persona by punishment over 10 rounds. One game per bar.",
               lambda c, m, p: damage_received(data[c, m], p), 160, (0, 40, 80, 120, 160))
    bar_panels("fig5_punishment_issued_by_persona.svg",
               "Punishment actions issued by persona, messages on vs off, for each model",
               "The follower punishes more when messages are off",
               "Number of punishment actions each persona took over 10 rounds. One game per bar.",
               lambda c, m, p: actions_issued(data[c, m], p), 12, (0, 4, 8, 12))
    bar_panels("fig6_leaderboard_final_tokens.svg",
               "Final tokens by persona, messages on vs off, for each model",
               "The selfish seat finishes at the top with messages on and last with messages off",
               "Tokens each persona holds after round 10 (each starts with 20). One game per bar.",
               lambda c, m, p: final_tokens(c, m)[p], 15, (0, 5, 10, 15), tag_fn=finish_tag)


if __name__ == "__main__":
    main()
