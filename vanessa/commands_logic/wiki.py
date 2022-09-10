from wikipedia import summary, PageError, DisambiguationError, WikipediaException, set_lang
from vanessa.actions import send_text
set_lang('ru')


def send_wiki_article(chat_id, msg):
    """sends the article requested from wikipedia"""
    try:
        return send_text(chat_id, summary(msg.replace('что такое', ''), sentences=3))
    except PageError:
        return send_text(chat_id, 'чота нету ничего')
    except DisambiguationError:
        return send_text(chat_id, 'ну, было много вариантов конечно, но я решила, что ничего не скажу')
    except WikipediaException:
        return send_text(chat_id, 'сусня какая-то')
