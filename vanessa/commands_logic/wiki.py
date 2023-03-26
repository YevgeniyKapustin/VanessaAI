"""Module for working with wikipedia."""
from random import choice

from wikipedia import summary, set_lang, PageError, DisambiguationError, \
    WikipediaException

from basic_actions.actions import send_text


class Wikipedia(object):
    """Class for handling requests to work with wikipedia.

        :param event: object with information about the event

    Methods:
    send_wiki_article()
    """
    set_lang('ru')

    def __init__(self, event):
        self.text = self._filtring(event.msg.text)
        self.chat_id = event.chat_id

    @staticmethod
    def _wiki_exception_handler(func):
        """Calls exception handling in Wikipedia class.

        Highly specialized decorator for one specific function.
        :param func: send_wiki_article method from Wikipedia class
        """

        def wrapper(self):
            try:
                func(self)
            except PageError:
                return self._handling_page_error()
            except DisambiguationError as error:
                return self._handling_disambiguation(error)
            except WikipediaException:
                return self._handling_wiki_exception()

        return wrapper

    @_wiki_exception_handler
    def send_wiki_article(self) -> str:
        """Send the article requested from wikipedia."""
        response = summary(self.text, chars=400)[::-1][:3:-1]
        return send_text(self.chat_id, f'{response[:response.rfind(".")]}.')

    def _handling_disambiguation(self, error):
        self.text = choice(error.options)
        return self.send_wiki_article()

    def _handling_page_error(self):
        return send_text(self.chat_id, 'чота нету ничего')

    def _handling_wiki_exception(self):
        return send_text(self.chat_id, 'сусня какая-то')

    @staticmethod
    def _filtring(text):
        if 'что такое' in text:
            text = text.replace('что такое', '')
        elif 'кто такой' in text:
            text = text.replace('кто такой', '')
        elif 'кто такая' in text:
            text = text.replace('кто такая', '')
        return text
