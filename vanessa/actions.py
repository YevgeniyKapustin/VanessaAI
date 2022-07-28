from vanessa.connection_to_vk.connection import vk


def send_text(chat_id, text: str):
    vk.messages.send(chat_id=chat_id, message=text, random_id=0)
    return text


def send_stick(chat_id, stick_id: int):
    vk.messages.send(chat_id=chat_id, sticker_id=stick_id, random_id=0)
    return stick_id


def send_file(chat_id, url: str):
    vk.messages.send(chat_id=chat_id, attachment=url, random_id=0)
    return url


def remove_msg(peer_id, msg_id: int):
    vk.messages.delete(peer_id=peer_id, conversation_message_ids=msg_id, delete_for_all=True, random_id=0)
    return msg_id
