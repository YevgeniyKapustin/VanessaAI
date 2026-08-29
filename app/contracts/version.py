"""Wire-protocol schema version.

Bump ``SCHEMA_VERSION`` when a breaking change lands in
``app/contracts/messages.py``. Producers stamp every message with the version
they were built against, so consumers can reject or migrate unknown payloads
instead of silently misparsing them.
"""

SCHEMA_VERSION = 1
