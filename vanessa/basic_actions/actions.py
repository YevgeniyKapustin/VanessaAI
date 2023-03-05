"""Contains the basic actions for VK api."""
from vk_api import ApiError

from vanessa.prepare.connection import Connection

_vk = Connection().vk


def send_text(chat_id: int, text: str) -> str:
    """Text is returned."""
    _vk.messages.send(chat_id=chat_id, message=text, random_id=0)
    return text


def send_stick(chat_id: int, stick_id: int) -> int:
    """Stick_id is returned."""
    try:
        _vk.messages.send(chat_id=chat_id, sticker_id=int(stick_id),
                          random_id=0)
        return stick_id
    except ApiError:
        send_text(chat_id, f'чота не дает мне вк кинуть {stick_id} '
                                f'стик')


def send_file(chat_id: int, url: str) -> str:
    """Url is returned or error string."""
    try:
        _vk.messages.send(chat_id=chat_id, attachment=url, random_id=0)
        return url
    except ApiError:
        return send_text(chat_id, 'чота сусня какая-то, вк ругаетя что '
                                  'сообщение пустое либо у меня нет к нему '
                                  'доступа, хотя я точно знаю, что сообщение '
                                  f'содержит {url}')


def remove_msg(peer_id: int, msg_id: int) -> int:
    """Deletes the message from the chat and returns the message id."""
    _vk.messages.delete(peer_id=peer_id, conversation_message_ids=msg_id,
                        delete_for_all=True, random_id=0)
    return msg_id
