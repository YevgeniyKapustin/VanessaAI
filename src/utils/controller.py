from src.utils.events import Event
from src import handlers


def controller(event: Event):
    handlers_dir: dict = vars(handlers)
    handlers_modules: list = [
        handlers_dir[handler_model]
        for handler_model in handlers_dir
        if handler_model[:2] != '__'
    ]

    for handler in handlers_modules:
        for module in handlers_modules:
            if module is handler:
                handler_args = vars(handler)
                for arg in handler_args:
                    if arg[:8] == 'handler_':
                        handler_args[arg](event)

#
# class Controller(object):
#     """The intermediary class between commands and responses.
#
#     :param event: object with information about the request
#     """
#
#     def __init__(self, event):
#         self.chat_id = event.chat_id
#         self.text = event.msg.text
#         self.peer_id = event.msg.peer_id
#         self.event = event
#         self.msg = event.msg
#         self.db = DataBase()
#
#     def definition(self):
#         """Causes questions to be checked for an answer."""
#         if not self._check_special_commands():
#             self._check_db_commands()
#
#     def _send_choice(self, response, _type):
#         if _type == 'текст':
#             return send_text(self.chat_id, response)
#         elif _type == 'гиф' or _type == 'изображение':
#             return send_file(self.chat_id, response)
#         elif _type == 'стикер':
#             return send_stick(self.chat_id, response)
#
#     def _check_db_commands(self):
#         data = self.db.get_response_and_type(self.text)
#         if data:
#             return self._send_choice(data[0], data[1])
#
#         for data in self.db.get_all_commands_for_strategy('contextual'):
#             if data[0] in self.text:
#                 return self._send_choice(data[2], data[1])
#
#     def _check_special_commands(self):
#         """Check hard code commands."""
#         if self.text == 'команды':
#             return send_text(self.chat_id, Commands().get_commands())
#
#         elif self.text == 'фракция':
#             return send_random_fraction(self.chat_id)
#
#         elif self.text == 'цивилизация':
#             return send_random_civ_from_civ6(self.chat_id)
#
#         elif self.text[:9] in ['что такое', 'кто такая', 'кто такой']:
#             return Wikipedia(self.event).send_wiki_article()
#
#         elif self.text[:3] == 'мут':
#             return Mute(self.event).shut_up()
#
#         elif self.text[:6] == 'размут':
#             return Mute.redemption(
#                 Mute(self.event))
#
#         elif self.text == 'добавить команду помощь':
#             return send_text(self.chat_id, '''добавить команду (тип ответа)(_)
#             (запрос): (ответ) например: добавить команду текст_ амогус: тутуту
#             нижнее подчеркивание нужно добавить если вы хотите, чтобы команда
#             писалась в случае если запрос содержится в сообщении, а не целиком
#             его составляла в случае ответадля гиф или изображения нужен его url
#             , для стикера id типы команд: текст, гиф, изображение, стикер''')
#
#         elif self.text[:16] == 'добавить команду':
#             return Commands.add_command(Commands(), self.event)
#
#         elif self.text[:15] == 'удалить команду':
#             return Commands.remove_command(Commands(), self.event)
#
#         elif self.text == 'абоба':
#             return send_random_zmiys_phrases(self.chat_id)
#
#         elif self.text == 'рарити':
#             return send_random_rarity(self.chat_id)
#
#         elif self.text == 'статистика игроков':
#             return send_text(self.chat_id, get_winrate('players'))
#
#         elif self.text == 'статистика фракций':
#             return send_text(self.chat_id, get_winrate('fractions'))
#
#         elif self.text[:1] == 'д':
#             return send_roll_dice(self.chat_id, self.text)
#
#         return None
