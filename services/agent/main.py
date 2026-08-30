from fastapi import FastAPI

from services.agent.app_spec import AppSpec
from services.agent.container import AppContainer
from services.agent.lifespan import lifespan
from services.agent.middleware import register_middleware
from services.agent.routes import register_routes
from vanessa.core.package import package_info


class AppFactory:
    def __init__(
        self,
        spec: AppSpec | None = None,
        container: AppContainer | None = None,
    ) -> None:
        self._spec = spec or AppSpec()
        self._container = container

    def build(self) -> FastAPI:
        self._configure_logging()
        application = self._create_application()
        self._register_middleware(application)
        self._register_routes(application)
        return application

    def _configure_logging(self) -> None:
        logging = self._spec.logging
        if logging.configure is not None:
            logging.configure(logging.service_name)

    def _create_application(self) -> FastAPI:
        openapi = self._spec.openapi.resolve(package_info())
        application = FastAPI(
            title=openapi.title,
            description=openapi.description,
            version=openapi.version,
            lifespan=lifespan,
        )
        application.state.container = self._container or AppContainer()
        return application

    def _register_middleware(self, application: FastAPI) -> None:
        register_middleware(application, self._spec.middleware)

    def _register_routes(self, application: FastAPI) -> None:
        register_routes(application)


app = AppFactory().build()
