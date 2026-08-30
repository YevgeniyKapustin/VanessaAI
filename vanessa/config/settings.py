import os

from vanessa.config.settings_sections import (
    BotMixin,
    CoreMixin,
    McpMixin,
    SharedSettings,
    WorkerMixin,
)


class Settings(BotMixin, CoreMixin, WorkerMixin, McpMixin, SharedSettings):
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

# huggingface_hub (used by sentence-transformers to download
# EMBEDDING_MODEL_NAME) reads the token from os.environ, not from pydantic
# settings. Propagate the .env HF_TOKEN into the process environment so local
# (non-Docker) runs are authenticated too; a real environment variable always
# wins over the .env value.
if settings.hf_token:
    os.environ.setdefault("HF_TOKEN", settings.hf_token)
