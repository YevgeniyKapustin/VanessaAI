from vanessa.config.settings_hermes import HermesMixin
from vanessa.config.settings_sections import (
    BotMixin,
    CoreMixin,
    McpMixin,
    SharedSettings,
    WorkerMixin,
)


class Settings(
    BotMixin, CoreMixin, WorkerMixin, McpMixin, HermesMixin, SharedSettings
):
    """Aggregate settings for the current monolith deployment.

    All fields and their env names are identical to the historical single
    ``Settings`` class — this is a source-level reorganization only. As
    services are extracted they migrate to the per-service classes in
    ``vanessa.config.settings_sections`` (``BotSettings``, ``CoreSettings``,
    ``WorkerSettings``, ``McpSettings``), which share the same base and env
    semantics. Keeping this aggregate means every existing
    ``from vanessa.config import settings`` import keeps working unchanged.
    """


settings = Settings()
