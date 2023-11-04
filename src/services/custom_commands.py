"""Модуль для работы с кастомными командами."""
from src.services.events import Event
from src.services.schemas import Command
from src.utils.queries import get_commands


def answer_for_custom_msg(event: Event, is_inline: bool) -> None:
    """Ответить кастомной командой на ивент

    Аргументы:
    event -- ивент, на которой нужно ответить
    is_inline -- является ли текст из ивента командой или нужно искать ее
    """
    data: list = get_commands(event.message.text, is_inline).json()

    if isinstance(data, list) and data is not None:
        prefix: str = 'внутристрочный_' if is_inline else ''
        response: str = data[0].get('response')
        type_: str = data[0].get('type')

        if type_ == f'{prefix}текст':
            event.text_answer(response)

        elif type_ == f'{prefix}гиф':
            event.gif_answer(response)


def create_command_obj(event: Event) -> Command:
    """Создает команду из ивента

    Аргументы:
    event -- ивент, из которого нужно достать информацию и ответить
    """
    text: str = event.message.text.lower()

    text_list: list = text.split(' ')
    text_list.remove('добавить')
    text_list.remove('команду')
    type_: str = text_list[0] if text_list is not None else ''
    text_list.remove(type_)

    command_text: str = ' '.join(text_list)
    text_list: list = command_text.split(':')
    request: str = text_list[0].strip()
    response: str = text_list[1].strip()

    return Command(type=type_, request=request, response=response)


def get_command_id(request: str) -> int:
    """Возвращает ID команды, если она существует, иначе 0."""
    commands: list = get_commands(request, False).json()
    return commands[0].get('id') if isinstance(commands, list) else 0
