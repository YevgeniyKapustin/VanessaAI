from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api import VkApi, ApiError
from random import randint
from wikipedia import summary, set_lang, PageError, DisambiguationError
from confidential_info import *
from vanessas_comands import *

set_lang("ru")


class VanessasCore:
    vk_session = VkApi(token=token)
    longpoll = VkBotLongPoll(vk_session, group_id)
    api_session = vk_session.get_api()


class Conversation(VanessasCore):

    def __init__(self):
        self._shut_up_people = []

    def __send_text(self, chat_id, text):
        self.api_session.messages.send(chat_id=chat_id, message=text, random_id=0)

    def __send_stick(self, chat_id, stick_id):
        self.api_session.messages.send(chat_id=chat_id, sticker_id=stick_id, random_id=0)

    def __send_file(self, chat_id, url):
        self.api_session.messages.send(chat_id=chat_id, attachment=url, random_id=0)

    def _remove_msg(self, peer_id, msg_id):
        self.api_session.messages.delete(peer_id=peer_id, conversation_message_ids=msg_id, delete_for_all=True, random_id=0)

    def __send_random_fraction(self, chat_id):
        self.__send_text(chat_id, f'🎲 {herofractions[randint(0, 7)]}')

    def __send_roll_dice(self, chat_id, msg):
        if msg.replace(dice, '').isdigit():
            self.__send_text(chat_id, f'🎲 {randint(1, int(msg.replace(dice, "")))}')

    def __send_wiki_article(self, chat_id, msg):
        try:
            self.__send_text(chat_id, summary(msg.replace('что такое', ''), sentences=2))
        except PageError:
            self.__send_text(chat_id, PageError_response)
        except DisambiguationError:
            self.__send_text(chat_id, DisambiguationError_response)

    def __shut_up(self, chat_id, msg, peer_id, event):
        try:
            members = self.api_session.messages.getConversationMembers(peer_id=peer_id)
        except ApiError:
            self.__send_text(chat_id, 'ну знаете, могли бы админку чтоле дать для начала')
            return
        victim_id = self.__victim_id_search(msg, event)
        if victim_id == 'ub2121387' or victim_id == '-212138773':
            self.__send_text(chat_id, 'я бы сказала, что это несколько возмутительно')
            return
        found = False
        for member in members['items']:
            try:
                if str(member['member_id']) == victim_id:
                    found = True
                    if member['is_admin']:
                        self.__send_file(chat_id, img_no_power)
                    return
            except KeyError:
                pass
        if not found:
            self.__send_text(chat_id, 'жертвы нету в этой беседе')
        elif victim_id in self._shut_up_people:
            self.__send_text(chat_id, f'наш [id{victim_id}|друг] уже отдыхает')
            return
        else:
            self._shut_up_people.append(victim_id)
            self.__send_text(chat_id, f'[id{victim_id}|друг] пока что отдохнет')
            return

    def __redemption(self, chat_id, msg):
        victim_id = self.__id_definition_by_reference(msg.replace('размут', ''))
        if victim_id in self._shut_up_people:
            self._shut_up_people.remove(victim_id)
            self.__send_text(chat_id, f'наш [id{victim_id}|друг], ты свободен, наслаждайся жизнью и хорошего тебе дня')
        else:
            self.__send_text(chat_id, f'да не то чтобы он сильно замучен')

    def __victim_id_search(self, msg, event):
        msg = msg.replace('мут', '')
        if msg == '' and 'reply_message' in event.object.message:
            victim_id = str(event.object.message['reply_message']['from_id'])
        else:
            victim_id = self.__id_definition_by_reference(msg)
        return victim_id

    @staticmethod
    def __id_definition_by_reference(reference):
        return reference.strip()[3:12]

    def response_definition(self, chat_id, msg, peer_id, event):
        if msg in text_commands:
            self.__send_text(chat_id, text_commands[msg])

        elif msg in gifs_commands:
            self.__send_file(chat_id, gifs_commands[msg])

        elif msg in img_commands:
            self.__send_file(chat_id, img_commands[msg])

        elif msg in stick_commands:
            self.__send_stick(chat_id, stick_commands[msg])

        elif msg == heroes_helper[0]:
            self.__send_random_fraction(chat_id)

        elif msg == heroes_helper[1]:
            self.__send_text(chat_id, position[randint(0, 3)])

        elif msg[:1] == dice:
            self.__send_roll_dice(chat_id, msg)

        elif msg == aboba:
            self.__send_text(chat_id, zmiysphrases[randint(0, 14)])

        elif msg[:9] in wiki:
            self.__send_wiki_article(chat_id, msg)

        elif msg[:3] == mute[0]:
            self.__shut_up(chat_id, msg, peer_id, event)

        elif msg[:6] == mute[1]:
            self.__redemption(chat_id, msg)

        for i in indirect_gifs_command:
            if i in msg:
                self.__send_file(chat_id, indirect_gifs_command[i])

        for i in indirect_img_commands:
            if i in msg:
                self.__send_file(chat_id, indirect_img_commands[i])


class Launcher(Conversation):

    def run(self):
        print("Server started")
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                peer_id = event.object.message['peer_id']
                if str(event.object.message['from_id']) in self._shut_up_people:
                    self._remove_msg(peer_id, event.object.message['conversation_message_id'])
                else:
                    chat_id = event.chat_id
                    msg = self.__message_filtering(event.object.message['text'])
                    self.response_definition(chat_id, msg, peer_id, event)

    @staticmethod
    def __message_filtering(msg):
        msg = msg.lower().split(' ')
        for word in msg:
            if word in filterable_text:
                msg.remove(word)
        return ' '.join(msg)


if __name__ == '__main__':
    Vanessa = Launcher()
    Vanessa.run()
