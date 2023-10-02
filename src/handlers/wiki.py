from src.rules.decorator import handle_message
from src.rules.rules import WikiRule
from src.services.wiki import Wikipedia
from src.utils.events import Event


@handle_message(WikiRule())
def handler_random_fraction(event: Event):
    event.answer(Wikipedia(event).send_wiki_article())
