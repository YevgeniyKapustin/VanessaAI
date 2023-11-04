from src.rules.rules import Wiki
from src.services.wiki import Wikipedia
from src.services.events import Event
from src.utils.decorators import handle_message


@handle_message(Wiki())
def handler_wikipedia(event: Event):
    event.text_answer(Wikipedia(event).get_wiki_article())
