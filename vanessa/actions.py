"""The module contains the actions class,
which contains the basic actions for VK api
"""
from vk_api import ApiError

from vanessa.connection import Connection


class Actions:
    """Class for working with basic VK api actions"""
    def __init__(self):
        self.vk = Connection().vk

    def send_text(self, chat_id: int, text: str) -> str:
        """Text is returned"""
        self.vk.messages.send(chat_id=chat_id, message=text, random_id=0)
        return text

    def send_stick(self, chat_id: int, stick_id: int) -> int:
        """Stick_id is returned"""
        try:
            self.vk.messages.send(chat_id=chat_id, sticker_id=int(stick_id),
                                  random_id=0)
            return stick_id
        except ApiError:
            self.send_text(chat_id, f'чота не дает мне вк кинуть {stick_id} '
                                    f'стик')

    def send_file(self, chat_id: int, url: str) -> str:
        """Url is returned or error string"""
        try:
            self.vk.messages.send(chat_id=chat_id, attachment=url, random_id=0)
            return url
        except ApiError:
            return self.send_text(chat_id, 'чота сусня какая-то, вк ругаетя '
                                           'что сообщение пустое либо у меня '
                                           'нет к нему доступа, хотя я точно '
                                           'знаю, что сообщение содержит '
                                           f'{url}')

    def remove_msg(self, peer_id: int, msg_id: int) -> int:
        """Deletes the message from the chat and returns the message id"""
        self.vk.messages.delete(peer_id=peer_id,
                                conversation_message_ids=msg_id,
                                delete_for_all=True, random_id=0)
        return msg_id
