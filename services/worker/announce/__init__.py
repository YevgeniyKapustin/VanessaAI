"""Watch anything worth a chat post: one loop, one YAML per watch."""

from services.worker.announce.registry import build_announcers

__all__ = ["build_announcers"]
