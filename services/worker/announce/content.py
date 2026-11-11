"""One YAML per watch: where the facts come from and how to word them.

The env *names* live in the file, the values live in settings, so a new
watch is a YAML plus env keys — no code change unless the payload shape is
new too (then it also needs a parser in ``registry``).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

WATCH_DIR = Path("announce")


class WatchSpec(BaseModel):
    """A watch: source wiring, schedule, and the wording prompts."""

    id: str = Field(min_length=1)
    #: Which payload parser to use (``registry.PARSERS``).
    kind: str = "deploy"
    #: Env names, resolved against settings by the registry.
    enabled_env: str = ""
    chat_id_env: str = ""
    url_env: str = ""
    token_env: str = ""
    probe_url_env: str = ""
    #: Env name holding a card-page URL template with ``{card}``: every card
    #: in the разбор becomes a link. Unset → plain card ids.
    card_url_env: str = ""
    #: Extra link placeholders for the prompts, ``{links[name]}``.
    link_envs: dict[str, str] = Field(default_factory=dict)
    #: Dedupe marker: the id of the last announced event.
    state_key: str = Field(min_length=1)
    #: Source endpoint path on the base URL.
    path: str = "/"
    poll_seconds: float = 60.0
    max_late_hours: int = 12
    ready_timeout_seconds: int = 900
    ready_poll_seconds: float = 30.0
    #: Tag the actor with a Telegram mention when they are a chat member.
    mention: bool = True
    # Prompts. Placeholders: {when}, {url}, {started_by}, {links[name]},
    # {count}, {title}.
    #: One line of standing context for the model («контур: production»).
    context: str = ""
    header: str = Field(min_length=1)
    footer: str = ""
    task: str = Field(min_length=1)
    #: Post the announcement as a rich message (one folded card) instead of
    #: plain text. Any refusal falls back to the text, so this is safe to try.
    rich: bool = False
    fallback_bullet: str = "• {title}"
    fallback_more: str = ""
    stand_down_line: str = "Стенд пока не отвечает"
    max_tokens: int | None = Field(default=512, ge=0, le=4096)


def load_watch(path: Path) -> WatchSpec:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return WatchSpec.model_validate(raw)


__all__ = ["WATCH_DIR", "WatchSpec", "load_watch"]
