"""Contains the basic actions for VK api."""
from vk_api import ApiError

from src.utils import vk

_vk = vk.get_bot_api()


def send_text(chat_id: int, text: str) -> str:
    """Text is returned.

    :param chat_id: id of the chat to which the message will be sent
    :param text: message sent by user
    """
    try:
        _vk.messages.send(chat_id=chat_id, message=text, random_id=0)
        return text
    except ApiError as error:
        return send_text(chat_id, f'{error}')


def send_stick(chat_id: int, stick_id: int) -> int:
    """Stick_id is returned.

    :param chat_id: id of the chat to which the message will be sent
    :param stick_id: VK sticker ID
    """
    try:
        _vk.messages.send(chat_id=chat_id, sticker_id=int(stick_id),
                          random_id=0)
        return stick_id
    except (ApiError, ValueError) as error:
        send_text(chat_id, f'{error}')


def send_file(chat_id: int, url: str) -> str:
    """Url is returned or error string.

    :param chat_id: id of the chat to which the message will be sent
    :param url: link to the file in the public domain
    (that is, the link should not be from the conversation)
    """
    try:
        _vk.messages.send(chat_id=chat_id, attachment=url, random_id=0)
        return url
    except ApiError as error:
        return send_text(chat_id, f'{error}')


def remove_msg(event) -> int:
    """Deletes the message from the chat and returns the message id."""
    try:
        return _vk.messages.delete(
            peer_id=event.msg.peer_id,
            conversation_message_ids=event.msg.conversation_message_id,
            delete_for_all=True, random_id=0
        )
    except ApiError as error:
        return send_text(event.chat_id, f'{error}')
