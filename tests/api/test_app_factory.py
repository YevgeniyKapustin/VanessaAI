from unittest.mock import MagicMock

from services.agent.app_spec import AppSpec, LoggingConfig, OpenApiConfig
from services.agent.main import AppFactory


def test_factory_configures_logging_on_build() -> None:
    setup = MagicMock()
    AppFactory(
        AppSpec(
            logging=LoggingConfig(service_name="api-test", configure=setup),
            middleware=(),
        )
    ).build()
    setup.assert_called_once_with("api-test")


def test_factory_skips_logging_when_unset() -> None:
    application = AppFactory(
        AppSpec(logging=LoggingConfig(configure=None), middleware=())
    ).build()
    assert application.title == "Vanessa API"
    assert application.user_middleware == []


def test_factory_uses_injected_openapi_identity() -> None:
    application = AppFactory(
        AppSpec(
            logging=LoggingConfig(configure=None),
            middleware=(),
            openapi=OpenApiConfig(
                title="Custom",
                description="Demo",
                version="9.9.9",
            ),
        )
    ).build()
    assert application.title == "Custom"
    assert application.description == "Demo"
    assert application.version == "9.9.9"
    assert hasattr(application.state, "container")
