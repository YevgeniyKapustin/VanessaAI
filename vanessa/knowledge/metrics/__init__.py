"""Mood & relationship metrics subsystem for the knowledge vault.

Metrics give each participant a typed, machine-readable profile (valence,
toxicity, trust, distance, ...) stored as a snapshot in the person card
frontmatter — the single source of truth. Deterministic metrics (presence,
reactivity, activity) are computed from the DB, semantic ones (valence,
sarcasm, trust, ...) are judged by an LLM.
"""
