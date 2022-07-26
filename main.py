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
        return text

    def __send_stick(self, chat_id, stick_id):
        self.api_session.messages.send(chat_id=chat_id, sticker_id=stick_id, random_id=0)
        return stick_id

    def __send_file(self, chat_id, url):
        self.api_session.messages.send(chat_id=chat_id, attachment=url, random_id=0)
        return url

    def _remove_msg(self, peer_id, msg_id):
        self.api_session.messages.delete(peer_id=peer_id, conversation_message_ids=msg_id, delete_for_all=True, random_id=0)
        return msg_id

    def __send_random_fraction(self, chat_id):
        rnd_fraction = f'🎲 {herofractions[randint(0, 7)]}'
        self.__send_text(chat_id, rnd_fraction)
        return rnd_fraction

    def __send_roll_dice(self, chat_id, msg):
        if msg.replace(dice, '').isdigit() and msg.replace(dice, '') != '0':
            roll_dice = f'🎲 {randint(1, int(msg.replace(dice, "")))}'
            self.__send_text(chat_id, roll_dice)
            return roll_dice

    def __send_wiki_article(self, chat_id, msg):
        try:
            article = summary(msg.replace('что такое', ''), sentences=4)
            self.__send_text(chat_id, article)
            return article
        except PageError:
            self.__send_text(chat_id, PageError_response)
            return PageError
        except DisambiguationError:
            self.__send_text(chat_id, DisambiguationError_response)
            return DisambiguationError

    def __shut_up(self, chat_id, msg, peer_id, event):
        members = self.__members_search(peer_id, chat_id)
        if self.__from_check(event, members):
            victim_id = self.__victim_id_search(msg, event)
            if victim_id == 'ub2121387' or victim_id == '-212138773':
                return self.__send_text(chat_id, 'я бы сказала, что это несколько возмутительно')
            found = False
            for member in members['items']:
                try:
                    if str(member['member_id']) == victim_id:
                        found = True
                        if member['is_admin']:
                            return self.__send_file(chat_id, img_no_power)
                        break
                except KeyError:
                    pass
            if not found:
                return self.__send_text(chat_id, 'жертвы нету в этой беседе')
            elif victim_id in self._shut_up_people:
                self.__send_text(chat_id, f'наш [id{victim_id}|друг] уже отдыхает')
                return f'наш [id{victim_id}|друг] уже отдыхает'
            else:
                self._shut_up_people.append(victim_id)
                self.__send_text(chat_id, f'наш [id{victim_id}|друг] пока что отдохнет')
                return f'наш [id{victim_id}|друг] пока что отдохнет'
        else:
            return self.__send_file(chat_id, img_no_power)

    def __redemption(self, chat_id, msg, event, peer_id):
        members = self.__members_search(peer_id, chat_id)
        if self.__from_check(event, members):
            victim_id = self.__victim_id_search(msg, event)
            if victim_id in self._shut_up_people:
                self._shut_up_people.remove(victim_id)
                self.__send_text(chat_id, f'[id{victim_id}|друг], ты свободен, наслаждайся жизнью и хорошего тебе дня')
                return f'[id{victim_id}|друг], ты свободен, наслаждайся жизнью и хорошего тебе дня'
            else:
                self.__send_text(chat_id, 'да не то чтобы он сильно замучен')
                return 'да не то чтобы он сильно замучен'
        else:
            self.__send_file(chat_id, img_no_power)

    @staticmethod
    def __from_check(event, members):
        from_admin = False
        member_id = event.object.message['from_id']
        for member in members['items']:
            try:
                if member['member_id'] == member_id and member['is_admin']:
                    from_admin = True
                    return from_admin
            except KeyError:
                pass
        return from_admin

    def __members_search(self, peer_id, chat_id):
        try:
            members = self.api_session.messages.getConversationMembers(peer_id=peer_id)
            return members
        except ApiError:
            self.__send_text(chat_id, 'ну знаете, могли бы админку чтоле дать для начала')
            return

    def __victim_id_search(self, msg, event):
        if 'раз' in msg:
            msg = msg.replace('раз', '')
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
            return self.__send_text(chat_id, text_commands[msg])

        elif msg in gifs_commands:
            return self.__send_file(chat_id, gifs_commands[msg])

        elif msg in img_commands:
            return self.__send_file(chat_id, img_commands[msg])

        elif msg in stick_commands:
            return self.__send_stick(chat_id, stick_commands[msg])

        elif msg == heroes_helper[0]:
            return self.__send_random_fraction(chat_id)

        elif msg == heroes_helper[1]:
            return self.__send_text(chat_id, position[randint(0, 3)])

        elif msg[:1] == dice:
            return self.__send_roll_dice(chat_id, msg)

        elif msg == aboba:
            return self.__send_text(chat_id, zmiysphrases[randint(0, 14)])

        elif msg[:9] in wiki:
            return self.__send_wiki_article(chat_id, msg)

        elif msg[:3] == mute[0]:
            return self.__shut_up(chat_id, msg, peer_id, event)

        elif msg[:6] == mute[1]:
            return self.__redemption(chat_id, msg, event, peer_id)

        for i in indirect_gifs_command:
            if i in msg:
                return self.__send_file(chat_id, indirect_gifs_command[i])

        for i in indirect_img_commands:
            if i in msg:
                return self.__send_file(chat_id, indirect_img_commands[i])


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
