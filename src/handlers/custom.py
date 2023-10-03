from requests import Response

from src.rules.rules import TextRule, InlineTextRule
from src.services.events import Event
from src.utils.custom_messages import answer_for_custom_msg
from src.utils.decorators import handle_message
from src.utils.queries import create_command


@handle_message(TextRule())
def handler_any_message(event: Event):
    answer_for_custom_msg(event, False)


@handle_message(TextRule())
def handler_any_message_inline(event: Event):
    answer_for_custom_msg(event, True)


@handle_message(InlineTextRule('добавить команду'))
def handler_add_command(event: Event):
    text = event.message.text.lower()
    text_list = text.split(' ')
    text_list.remove('добавить')
    text_list.remove('команду')
    type_ = text_list[0] if len(text_list) >= 1 else ''
    text_list.remove(type_)
    command_text = ' '.join(text_list)
    text_list = command_text.split(':')

    data: Response = create_command(
        request=text_list[0].strip(),
        response=text_list[1].strip(),
        type_=type_
    )
    data
