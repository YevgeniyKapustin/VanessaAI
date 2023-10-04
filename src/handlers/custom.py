from requests import Response

from src.rules.rules import TextRule, InlineTextRule
from src.services.events import Event
from src.services.schemas import Command
from src.utils.custom_commands import (
    answer_for_custom_msg, create_command_obj
)
from src.utils.decorators import handle_message
from src.utils.queries import create_command
from src.utils.status_cods import OK_200, CREATE_201


@handle_message(TextRule())
def handler_any_message(event: Event):
    answer_for_custom_msg(event, False)


@handle_message(TextRule())
def handler_any_message_inline(event: Event):
    answer_for_custom_msg(event, True)


@handle_message(InlineTextRule('добавить команду'))
def handler_add_command(event: Event):
    command: Command = create_command_obj(event)
    query_response: Response = create_command(
        request=command.request,
        response=command.response,
        type_=command.type
    )
    if query_response.status_code == OK_200:
        event.text_answer(f'Команда "{command.request}" уже существует')
    elif query_response.status_code == CREATE_201:
        event.text_answer(f'Команда "{command.request}" создана')
