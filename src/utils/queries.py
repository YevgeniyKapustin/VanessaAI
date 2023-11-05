"""Запросы на внешние сервисы."""
from loguru import logger
from requests import Session, Response

from src import config

session: Session = Session()


def get_commands(request: str = '', is_inline: bool = True) -> Response:
    """Возвращает Response объект с информацией о запрашиваемой команде.

    Аргументы:
    request -- текст запроса команды. По умолчанию возвращает все команды
    is_inline -- искать ли команду внутри request? По умолчанию True

    """
    logger.debug(f'GET {config.SERVER_URI}/api/v1/commands')
    return session.get(
        url=f'{config.SERVER_URI}/api/v1/commands',
        params={
            'request': request,
            'is_inline': is_inline
        }
    )


def create_command(request: str, response: str, type_: str) -> Response:
    """Создает команду и возвращает Response объект.

    Аргументы:
    request -- текст запроса команды
    response -- ответ команды
    type_ -- тип команды

    """
    logger.debug(f'CREATE {config.SERVER_URI}/api/v1/commands')
    return session.post(
        url=f'{config.SERVER_URI}/api/v1/commands',
        json={
            'request': request.strip(),
            'response': response.strip(),
            'type': type_.strip()
        }
    )


def delete_command(id_: int) -> Response:
    """Удаляет команду и возвращает Response объект.

    Аргументы:
    id_ -- идентификатор команды, которую нужно удалить

    """
    logger.debug(f'DELETE {config.SERVER_URI}/api/v1/commands')
    return session.delete(
        url=f'{config.SERVER_URI}/api/v1/commands',
        params={
            'command_id': id_,
        }
    )
