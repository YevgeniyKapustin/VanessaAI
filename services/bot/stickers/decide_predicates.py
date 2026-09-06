import random


def delivery_disabled(*, enabled: bool, has_resolved_files: bool) -> bool:
    return not enabled or not has_resolved_files


def cooldown_blocks(
    *,
    force: bool,
    messages_since: int,
    min_messages_between: int,
) -> bool:
    return not force and messages_since < min_messages_between


def probability_blocks(
    rng: random.Random,
    probability: float,
    *,
    force: bool,
) -> bool:
    if force:
        return False
    return rng.random() >= probability
