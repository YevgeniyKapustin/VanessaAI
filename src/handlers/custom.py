from src.rules.rules import TextRule
from src.services.events import Event
from src.utils.custom_messages import answer_for_custom_msg
from src.utils.decorators import handle_message


@handle_message(TextRule('<any>'))
def handler_any_message(event: Event):
    answer_for_custom_msg(event, False)


@handle_message(TextRule('<any>'))
def handler_any_message_inline(event: Event):
    answer_for_custom_msg(event, True)
