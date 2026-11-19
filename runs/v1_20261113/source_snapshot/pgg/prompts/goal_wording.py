"""Goal wording constants (see PGG_REFERENCE.md §7 and build spec §5.1).

PGG-Bench's baseline goal is *relative* token standing. Keep both available and
select via config so the wording is easy to change without touching the engine.
"""

# Baseline PGG-Bench wording: maximize tokens relative to the others.
GOAL_RELATIVE = (
    "Your objective is to finish the game with more tokens than the other "
    "players. Your success is measured by your final token count relative to "
    "theirs, not by the group's total."
)

# Open-decision alternative: absolute own-token maximization.
GOAL_ABSOLUTE = (
    "Your objective is to maximize your own final token count. Only the number "
    "of tokens you personally hold at the end of the game matters."
)

GOAL_WORDINGS = {
    "relative": GOAL_RELATIVE,
    "absolute": GOAL_ABSOLUTE,
}
