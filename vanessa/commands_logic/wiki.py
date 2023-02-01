from wikipedia import summary, PageError, DisambiguationError, WikipediaException, set_lang

from vanessa.actions import send_text

set_lang('ru')


def send_wiki_article(chat_id, msg):
    """sends the article requested from wikipedia"""
    if 'что такое' in msg:
        msg = msg.replace('что такое', '')
    elif 'кто такой' in msg:
        msg = msg.replace('кто такой', '')
    elif 'кто такая' in msg:
        msg = msg.replace('кто такая', '')
    try:
        return send_text(chat_id, summary(msg, sentences=3))
    except PageError:
        return send_text(chat_id, 'чота нету ничего')
    except DisambiguationError:
        return send_text(chat_id, 'ну, было много вариантов конечно, но я решила, что ничего не скажу')
    except WikipediaException:
        return send_text(chat_id, 'сусня какая-то')
