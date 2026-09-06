def _semantic_query(turn_plan, message: str) -> str:
    """Prefer the composed archive query, then the embedding query, then raw."""
    for candidate in (turn_plan.knowledge_query, turn_plan.text):
        if candidate and candidate.strip():
            return candidate.strip()
    return message.strip()
