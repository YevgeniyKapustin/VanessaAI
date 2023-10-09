from requests import Response

from src.rules.rules import InlineText, Any
from src.services.events import Event
from src.services.schemas import Command
from src.services.custom_commands import answer_for_custom_msg, \
    create_command_obj, get_command_id
from src.utils.decorators import handle_message
from src.utils.queries import create_command, delete_command
from src.utils.status_cods import OK_200, CREATE_201, NOT_FOUND_404


@handle_message(Any())
def handler_any_message(event: Event):
    answer_for_custom_msg(event, False)


@handle_message(Any())
def handler_any_message_inline(event: Event):
    answer_for_custom_msg(event, True)


@handle_message(InlineText('добавить команду'))
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


@handle_message(InlineText('удалить команду'))
def handler_delete_command(event: Event):
    request: str = event.message.text.replace('удалить команду', '').strip()
    query_response: Response = delete_command(id_=get_command_id(request))
    if query_response.status_code == OK_200:
        event.text_answer(f'Команда "{request}" удалена')
    elif query_response.status_code == NOT_FOUND_404:
        event.text_answer(f'Команда "{request}" не существует')
