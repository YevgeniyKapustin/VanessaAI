from random import choice

from wikipedia import summary, set_lang

from src.constans import wiki_queries
from src.utils.decorators import wiki_exception_handler


class Wikipedia(object):
    __slots__ = ('text',)

    set_lang('ru')

    def __init__(self, event):
        self.text = self._filtering(event.message.text)

    @wiki_exception_handler
    def send_wiki_article(self) -> str:
        response = summary(self.text, chars=400)[::-1][:3:-1]
        return f'{response[:response.rfind(".")]}.'

    def _handling_disambiguation(self, error):
        self.text = choice(error.options)
        return self.send_wiki_article()

    @staticmethod
    def _handling_page_error():
        return 'чота нету ничего'

    @staticmethod
    def _handling_wiki_exception():
        return 'сусня какая-то'

    @staticmethod
    def _filtering(text):
        return [
            text.replace(wiki_query, '').strip()
            for wiki_query in wiki_queries
            if wiki_query in text
        ][0]
