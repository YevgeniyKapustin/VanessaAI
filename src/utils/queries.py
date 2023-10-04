from requests import Session, Response

from src import config

session: Session = Session()


def get_commands(request: str, is_inline: bool = True) -> Response:
    return session.get(
        url=f'{config.SERVER_URI}/api/v1/commands',
        params={
            'request': request,
            'is_inline': is_inline
        }
    )


def create_command(request: str, response: str, type_: str) -> Response:
    return session.post(
        url=f'{config.SERVER_URI}/api/v1/commands',
        json={
            'request': request.strip(),
            'response': response.strip(),
            'type': type_.strip()
        }
    )


def delete_command(id_: int) -> Response:
    return session.delete(
        url=f'{config.SERVER_URI}/api/v1/commands',
        params={
            'command_id': id_,
        }
    )
