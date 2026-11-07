# Persona definitions — one file per person

Each `.md` file in this folder is **one persona**, owned by **one person**. The
persona's id is the filename without `.md` (e.g. `maximizer.md` -> `maximizer`).

Because each person edits their own file, all five can edit at the same time
with no merge conflicts.

## How to edit your persona

Open your file and fill in exactly two fields:

```
principal_instruction: "What the agent's human boss told it to do."

disposition: How the agent behaves and talks.
```

Rules:
- Keep each field short (a few sentences). Long text swamps model differences.
- Do **not** add a `## persona:` heading — the filename is the id.
- Lines starting with `#` are ignored, so the title line at the top is just a
  comment for you.
- `README.md` and any file starting with `_` are ignored by the loader.

## Current owners

| file | id | persona | owner |
| --- | --- | --- | --- |
| `good_samaritan.md` | good_samaritan | Good Samaritan | person 1 |
| `selfish.md` | selfish | Selfish / Capitalist | person 2 |
| `flaky.md` | flaky | Flaky / Chaos Monkey | person 3 |
| `follower.md` | follower | Follower | person 4 |
| `socialist.md` | socialist | Socialist | person 5 |
| `defector.md` | defector | Planted free-rider (V6 only, not in the five) | shared |

To add a new persona, create a new `<id>.md` file here and reference `<id>` in a
config under `configs/`.
