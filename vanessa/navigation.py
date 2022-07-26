from vanessa.commands_list import *
from vanessa.actions import *
from vanessa.commands_logic import randomize as rnd, mute
from vanessa.commands_logic.wiki import send_wiki_article


def response_definition(chat_id, msg, peer_id, event):
    if msg in text_commands:
        return send_text(chat_id, text_commands[msg])

    elif msg in gifs_commands:
        return send_file(chat_id, gifs_commands[msg])

    elif msg in img_commands:
        return send_file(chat_id, img_commands[msg])

    elif msg in stick_commands:
        return send_stick(chat_id, stick_commands[msg])

    elif msg == heroes_helper[0]:
        return rnd.send_random_fraction(chat_id)

    elif msg == heroes_helper[1]:
        return send_text(chat_id, rnd.send_random_position(chat_id))

    elif msg[:1] == dice_command:
        return rnd.send_roll_dice(chat_id, msg)

    elif msg == aboba_command:
        return send_text(chat_id, rnd.send_random_zmiysphrases(chat_id))

    elif msg[:9] in wiki_command:
        return send_wiki_article(chat_id, msg)

    elif msg[:3] == mute_command[0]:
        return mute.Mute.shut_up(mute.Mute(), chat_id, msg, peer_id, event)

    elif msg[:6] == mute_command[1]:
        return mute.Mute.redemption(mute.Mute(), chat_id, msg, event, peer_id)

    for i in indirect_gifs_command:
        if i in msg:
            return send_file(chat_id, indirect_gifs_command[i])

    for i in indirect_img_commands:
        if i in msg:
            return send_file(chat_id, indirect_img_commands[i])
