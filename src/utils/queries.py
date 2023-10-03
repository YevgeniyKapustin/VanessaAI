from requests import Session, Response

from src import config

session: Session = Session()


def get_commands(request: str, is_inline: bool = True) -> Response:
    return session.get(
        url=f'{config.SERVER_URI}/api/v1/commands',
        params={
            'request': request,
            'is_inline': is_inline,
        }
    )
