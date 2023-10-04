from src.rules.rules import Wiki
from src.services.wiki import Wikipedia
from src.services.events import Event
from src.utils.decorators import handle_message


@handle_message(Wiki())
def handler_random_fraction(event: Event):
    event.text_answer(Wikipedia(event).send_wiki_article())
