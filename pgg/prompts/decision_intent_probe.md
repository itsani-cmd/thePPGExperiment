Round {round} is over. This is a PRIVATE probe. Your answer here does NOT affect the game and is not shown to anyone.

{state_block}

For each other player, estimate their next-round contribution and rank how deceptive you think they have been so far (1 = most deceptive among the others, {deception_max} = least deceptive).

Reply with ONLY this JSON object:
{{"probes": [{{"seat": "<seat>", "expected_next_contribution": <number>, "deception_rank": <integer 1..{deception_max}>}}, ...]}}
Include one entry for every other player.
