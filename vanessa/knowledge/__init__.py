"""Knowledge vault: the bot's own machine-only, git-tracked structured memory.

Written and read exclusively by the bot — no human browses it. The format is a
deterministic contract for the LLM: stable per-entity files, typed YAML
frontmatter, fixed section headings, and per-folder ``_index.yaml`` machine
manifests (no human MOC / wikilink layer).
"""

from vanessa.core.knowledge_dto import KnowledgeBlock
from vanessa.knowledge.schema import MemoryPlan, VaultNote

__all__ = [
    "KnowledgeBlock",
    "MemoryPlan",
    "VaultNote",
]
