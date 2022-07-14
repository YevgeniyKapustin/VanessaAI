from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api import VkApi
from random import randint
import wikipedia
from wikipedia import PageError, DisambiguationError

from confidential_info import *
from vanessas_comands import *

wikipedia.set_lang("ru")


class VanessasCore:
    vk_session = VkApi(token=token)
    longpoll = VkBotLongPoll(vk_session, group_id)
    api_session = vk_session.get_api()


class Conference(VanessasCore):

    def __send_text(self, chat_id, text):
        self.api_session.messages.send(chat_id=chat_id, message=text, random_id=0)

    def __send_stick(self, chat_id, number):
        self.api_session.messages.send(chat_id=chat_id, sticker_id=number, random_id=0)

    def __send_file(self, chat_id, url):
        self.api_session.messages.send(chat_id=chat_id, attachment=url, random_id=0)

    def __send_random_fraction(self, chat_id):
        text = '🎲 ' + herofractions[randint(0, 7)]
        self.api_session.messages.send(chat_id=chat_id, message=text, random_id=0)

    def __send_roll_dice(self, chat_id, msg):
        msg = list(msg)
        msg.remove('д')
        msg = ''.join(msg)
        if msg.isdigit():
            msg = '🎲 {}'.format(randint(1, int(msg)))
            self.api_session.messages.send(chat_id=chat_id, message=msg, random_id=0)

    def __send_wiki_article(self, chat_id, msg):
        msg = msg.replace('что', '')
        msg = msg.replace('такое', '')
        if '?' in msg:
            msg = msg.replace('?', '')
        try:
            self.api_session.messages.send(chat_id=chat_id, message=wikipedia.summary(msg, sentences=3), random_id=0)
        except PageError:
            self.api_session.messages.send(chat_id=chat_id, message='чота нету ничего', random_id=0)
        except DisambiguationError:
            self.api_session.messages.send(chat_id=chat_id,
                                           message='ну, было много вариантов конечно, но я решила, что ничего не скажу',
                                           random_id=0)

    def message_definition(self, chat_id, msg):
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

        elif helpful_commands[1] in msg:
            self.__send_roll_dice(chat_id, msg)

        elif msg == helpful_commands[2]:
            self.__send_text(chat_id, position[randint(0, 3)])

        elif msg == helpful_commands[3]:
            self.__send_text(chat_id, zmiysphrases[randint(0, 14)])

        elif helpful_commands[4] in msg:
            self.__send_wiki_article(chat_id, msg)


class Private(VanessasCore):
    pass


class Launcher(Conference, Private):

    def run(self):
        print("Server started")
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                if event.from_chat:
                    chat_id = event.chat_id
                    msg = event.object.message['text'].lower()
                    msg = self.__message_filtering(msg)
                    self.message_definition(chat_id, msg)

                elif event.to_me:
                    user_id = event.user_id
                    msg = event.object.message['text'].lower()
                    print(user_id, msg)
                    # msg = self.__message_filtering(msg)
                    # self.message_definition(user_id, msg)

    @staticmethod
    def __message_filtering(msg):
        msg = msg.split(' ')
        for i in msg:
            if ',' in i:
                msg.append(i[:-1])
                msg.remove(i)
            elif 'ванесса' in i:
                msg.remove(i)
            elif '[club212138773|@vanessakapustovna]' in i:
                msg.remove(i)
        msg = ' '.join(msg)
        return msg


if __name__ == '__main__':
    Vanessa = Launcher()
    Vanessa.run()
