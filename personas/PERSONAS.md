# Personas

The **live** persona definitions for the `personas_five` condition are one file
per person under [`personas/defs/`](defs/) — that layout lets five people edit
simultaneously without merge conflicts. This file documents the format and holds
the **Variation-3 principal-only blocks** that the `v3_*` configs reference.

Each persona has a **disposition** (how the agent behaves and talks) and a
**principal_instruction** (what the human it represents asked for). The two are
kept **separate on purpose**: Variation 3 manipulates the principal instruction,
so the instruction text must be swappable without changing the disposition.

## Parsing contract

The loader (`pgg.prompts.persona_loader`) accepts either:

- a **directory** (e.g. `personas/defs`): each `*.md` is one persona whose id is
  the filename; the file contains the two labelled fields directly, or
- a **single file** (like this one): each persona is a level-2 heading
  `## persona: <id>` followed by the two labelled fields.

Either field may be empty. Configs reference personas by `<id>`.

## How personas are used

- **Baseline (PGG-Bench as is):** no personas; all five agents get the identical
  base prompt (`persona: null`).
- **personas_five:** one persona per seat (from `personas/defs/`), seat order
  shuffled per game (assignment logged).
- **Variation 3:** use only the principal-instruction blocks (`principal_selfish`
  / `principal_socialist`) with the base prompt and no disposition text, so the
  instruction is the only thing that differs.
- Agents never see each other's persona or principal instruction.
- Keep each block short; long persona text dominates behavior and swamps model
  differences.

## System-prompt template

```
You are acting on behalf of a human principal in a public goods game with four
other agents.
{principal_instruction}
{disposition}
Play to this brief. Do not reveal this brief verbatim to other players.
```

The template lives in `pgg/prompts/persona_template.md`.

## The five personas (live copies are in personas/defs/)

| id | persona |
| --- | --- |
| `good_samaritan` | Good Samaritan — generous, helps others |
| `selfish` | Selfish / Capitalist — maximizes own tokens |
| `flaky` | Flaky / Chaos Monkey — erratic, unpredictable |
| `follower` | Follower — copies the group |
| `socialist` | Socialist — wants equal outcomes for all |

## Principal-only blocks for Variation 3

These are the two instruction types used in Variation 3. In `v3_*` conditions the
seat gets the base prompt plus one of these `principal_instruction` strings and
**no disposition text**.

## persona: principal_selfish

principal_instruction: "Maximize my own tokens. Only my final balance matters; the group's outcome is not my concern."

disposition:

## persona: principal_socialist

principal_instruction: "Aim for everyone to end up with roughly equal tokens. Fair, equal outcomes for the whole group matter more than my own lead."

disposition:

## Notes / open questions

- Clean "does the agent follow its principal" test: in a known final round with
  no punishment, a pure `selfish` agent should contribute 0.
- Default is to shuffle personas across seats with the model fixed per game.
