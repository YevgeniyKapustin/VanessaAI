from services.agent.container import AppContainer


def get_container(request) -> AppContainer:
    return request.app.state.container
