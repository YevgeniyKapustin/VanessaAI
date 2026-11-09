"""Plain text helpers any layer may use: no pipeline, no infrastructure.

``code_fences`` keeps fenced code untouched; ``dashes`` swaps typographic
dashes outside those fences. Both are pure stdlib and safe for adapters.
"""

from vanessa.core.text.code_fences import FENCED_CODE, map_outside_fences
from vanessa.core.text.dashes import DASHES, plain_dashes

__all__ = ["DASHES", "FENCED_CODE", "map_outside_fences", "plain_dashes"]
