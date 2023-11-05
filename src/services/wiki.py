"""Модуль для класса Wikipedia."""
from random import choice

from wikipedia import summary, set_lang, DisambiguationError

from src.utils.constants import wiki_queries
from src.services.events import Event
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

    def __init__(self, event: Event):
        self.text = self._filtering(event.message.text)

    @wiki_exception_handler
    def get_wiki_article(self) -> str:
        """Возвращает начало статьи."""
        response: str = summary(self.text, chars=400)[::-1][:3:-1]
        return f'{response[:response.rfind(".")]}.'

    def _handling_disambiguation(self, error: DisambiguationError) -> str:
        self.text: str = choice(error.options)
        return self.get_wiki_article()

    @staticmethod
    def _handling_page_error() -> str:
        return 'чота нету ничего'

    @staticmethod
    def _handling_wiki_exception() -> str:
        return 'абоба какая-то'

    @staticmethod
    def _filtering(text: str) -> str:
        return [
            text.replace(wiki_query, '').strip()
            for wiki_query in wiki_queries
            if wiki_query in text
        ][0]
