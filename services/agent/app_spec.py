from collections.abc import Sequence
from dataclasses import dataclass, field

from services.agent.protocols import HttpMiddleware, LoggingSetup
from vanessa.core.logging_setup import ServiceName, configure_logging
from vanessa.core.package import PackageInfo


@dataclass(frozen=True)
class LoggingConfig:
    service_name: ServiceName = "agent"
    configure: LoggingSetup | None = configure_logging


@dataclass(frozen=True)
class ResolvedOpenApi:
    title: str
    description: str
    version: str


@dataclass(frozen=True)
class OpenApiConfig:
    title: str | None = None
    description: str | None = None
    version: str | None = None

    def resolve(self, identity: PackageInfo) -> ResolvedOpenApi:
        return ResolvedOpenApi(
            title=self.title or identity.api_title,
            description=self.description or identity.description,
            version=(
                self.version if self.version is not None else identity.version
            ),
        )


@dataclass(frozen=True)
class AppSpec:
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    middleware: Sequence[HttpMiddleware] | None = None
    openapi: OpenApiConfig = field(default_factory=OpenApiConfig)
