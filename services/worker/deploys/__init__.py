"""Deploy-specific pieces: the payload model and its announcement adapter."""

from services.worker.deploys.adapter import deploy_announcement

__all__ = ["deploy_announcement"]
