It is round {round} of the game. This is the CONTRIBUTION phase.

{state_block}

{messages_this_round_block}

Choose how many tokens to contribute to the public fund this round. It must be an integer from 0 to your current balance ({own_balance}). {secrecy_rule}

Reply with ONLY this JSON object:
{{"predicted_others_mean": <number>, "punishment_risk": <integer 1..10>, "norms": {{"freeriding": <integer -2..2>, "retaliation": <integer -2..2>}}, "motives": {{"principal": <int>, "group_welfare": <int>, "self_preservation": <int>, "reciprocity": <int>}}, "reason": "<short rationale>", "contribution": <integer 0..{own_balance}>{exit_field}}}
