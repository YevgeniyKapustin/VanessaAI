"""Модуль для класса Wikipedia."""
from random import choice

from wikipedia import summary, set_lang

from src.constants import wiki_queries
from src.utils.decorators import wiki_exception_handler


class Wikipedia(object):
    """Класс для работы с парсером википеидии.

    Поля:
    event -- ивент, из которого будет экстрактирован текст запроса

    Методы:
    get_wiki_article -- возвращает статью, или информацию об ошибке

    """
    __slots__ = ('text',)

    set_lang('ru')

    def __init__(self, event):
        self.text = self._filtering(event.message.text)

    @wiki_exception_handler
    def get_wiki_article(self) -> str:
        """Возвращает начало статьи."""
        response = summary(self.text, chars=400)[::-1][:3:-1]
        return f'{response[:response.rfind(".")]}.'

    def _handling_disambiguation(self, error):
        self.text = choice(error.options)
        return self.get_wiki_article()

    @staticmethod
    def _handling_page_error():
        return 'чота нету ничего'

    @staticmethod
    def _handling_wiki_exception():
        return 'абоба какая-то'

    @staticmethod
    def _filtering(text):
        return [
            text.replace(wiki_query, '').strip()
            for wiki_query in wiki_queries
            if wiki_query in text
        ][0]
