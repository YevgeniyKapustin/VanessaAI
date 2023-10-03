from src.rules.rules import TextRule
from src.services.events import Event
from src.utils.decorators import handle_message
from src.utils.queries import get_commands


@handle_message(TextRule('<any>'))
def handler_any_message(event: Event):
    data: list = get_commands(event.message.text, False).json()
    if isinstance(data, list) and len(data) >= 1:
        type_ = data[0].get('type')
        command = data[0]
        if type_ == 'text':
            event.text_answer(command.get('response'))
        elif type_ == 'gif':
            event.gif_answer(command.get('response'))


@handle_message(TextRule('<any>'))
def handler_any_message_inline(event: Event):
    data: list = get_commands(event.message.text, True).json()
    if len(data) >= 1 and (type_ := data[0].get('type')):
        command = data[0]
        if type_ == 'inline_text':
            event.text_answer(command.get('response'))
        elif type_ == 'inline_gif':
            event.gif_answer(command.get('response'))
