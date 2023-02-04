"""Module for working with wikipedia"""
from wikipedia import summary, PageError, DisambiguationError, \
    WikipediaException, set_lang

from vanessa.actions import Actions


class Wikipedia:
    """Class for working with wikipedia articles"""
    def __init__(self):
        set_lang('ru')
        self.send_text = Actions.send_text

    def send_wiki_article(self, chat_id, msg):
        """Sends the article requested from wikipedia"""
        if 'что такое' in msg:
            msg = msg.replace('что такое', '')
        elif 'кто такой' in msg:
            msg = msg.replace('кто такой', '')
        elif 'кто такая' in msg:
            msg = msg.replace('кто такая', '')
        try:
            return self.send_text(chat_id, summary(msg, sentences=3))
        except PageError:
            return self.send_text(chat_id, 'чота нету ничего')
        except DisambiguationError:
            return self.send_text(chat_id, 'ну, было много вариантов конечно, '
                                           'но я решила, что ничего не скажу')
        except WikipediaException:
            return self.send_text(chat_id, 'сусня какая-то')
