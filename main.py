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
        if msg.replace('д', '').isdigit():
            self.__send_text(chat_id, f'🎲 {randint(1, int(msg))}')

    def __send_wiki_article(self, chat_id, msg):
        try:
            self.__send_text(chat_id, summary(msg.replace('что такое', ''), sentences=2))
        except PageError:
            self.__send_text(chat_id, PageError_response)
        except DisambiguationError:
            self.__send_text(chat_id, DisambiguationError_response)

    def __shut_up(self, chat_id, msg, peer_id):
        try:
            victim_id = self.__id_definition_by_reference(msg.replace('мут', ''))
            members = self.api_session.messages.getConversationMembers(peer_id=peer_id)
            found = False
            for member in members['items']:
                try:
                    if member['member_id'] == int(victim_id):
                        found = True
                        if member['is_admin']:
                            self.__send_file(chat_id, img_no_power)
                        return
                except KeyError:
                    pass
            if not found:
                self.__send_text(chat_id, f'жертвы нету в этой беседе')
            elif victim_id in self._shut_up_people:
                self.__send_text(chat_id, f'наш [id{victim_id}|друг] уже отдыхает')
                return
            else:
                self._shut_up_people.append(victim_id)
                self.__send_text(chat_id, f'наш [id{victim_id}|друг] пока что отдохнет')
                return
        except ApiError:
            self.__send_text(chat_id, f'ну знаете, могли бы админку чтоле дать для начала')

    def __redemption(self, chat_id, msg):
        victim_id = self.__id_definition_by_reference(msg.replace('размут', ''))
        if victim_id in self._shut_up_people:
            self._shut_up_people.remove(victim_id)
            self.__send_text(chat_id, f'наш [id{victim_id}|друг], ты свободен, наслаждайся жизнью и хорошего тебе дня')
        else:
            self.__send_text(chat_id, f'да не то чтобы он сильно замучен')

    @staticmethod
    def __id_definition_by_reference(reference):
        return reference.strip()[3:12]

    def response_definition(self, chat_id, msg, peer_id):
        for i in indirect_gifs_command:
            if i in msg:
                self.__send_file(chat_id, indirect_gifs_command[i])
                return

        for i in indirect_img_commands:
            if i in msg:
                self.__send_file(chat_id, indirect_img_commands[i])
                return

        if msg in text_commands:
            self.__send_text(chat_id, text_commands[msg])

        elif msg in gifs_commands:
            self.__send_file(chat_id, gifs_commands[msg])

        elif msg in img_commands:
            self.__send_file(chat_id, img_commands[msg])

        elif msg in stick_commands:
            self.__send_stick(chat_id, stick_commands[msg])

        elif msg == helpful_commands[0]:
            self.__send_random_fraction(chat_id)

        elif helpful_commands[1] in msg[:1]:
            self.__send_roll_dice(chat_id, msg)

        elif msg == helpful_commands[2]:
            self.__send_text(chat_id, position[randint(0, 3)])

        elif msg == helpful_commands[3]:
            self.__send_text(chat_id, zmiysphrases[randint(0, 14)])

        elif helpful_commands[4] in msg[:9]:
            self.__send_wiki_article(chat_id, msg)

        elif helpful_commands[5] in msg[:3]:
            self.__shut_up(chat_id, msg, peer_id)

        elif helpful_commands[6] in msg[:6]:
            self.__redemption(chat_id, msg)


class Launcher(Conversation):

    def run(self):
        print("Server started")
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_chat:
                chat_id = event.chat_id
                peer_id = event.object.message['peer_id']
                if str(event.object.message['from_id']) in self._shut_up_people:
                    self._remove_msg(peer_id, event.object.message['conversation_message_id'])
                else:
                    msg = self.__message_filtering(event.object.message['text'])
                    self.response_definition(chat_id, msg, peer_id)

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
