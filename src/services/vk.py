"""Модуль для класса Connection."""
from vk_api.bot_longpoll import VkBotLongPoll
from vk_api.vk_api import VkApiGroup, VkApiMethod
from vk_api import VkApi, VkUpload

from src import config


class Connection(object):
    """Класс для работы с непосредственно VK.

    Методы:
    get_bot_api -- возвращает объект для работы с API с правами бота
    get_admin_api -- возвращает объект для работы с API с права юзера
    get_upload -- возвращает объект для загрузки файлов в ВК
    get_longpoll -- возвращает объект для прослушивания ивентов
    """
    __slots__ = ('__bot_api', '__admin_api', '__uploader', '__longpoll')

    def __init__(self):
        vk_session = VkApiGroup(token=config.COMMUNITY_TOKEN)
        vk_admin_session = VkApi(token=config.ADMIN_TOKEN)
        self.__bot_api: VkApiMethod = vk_session.get_api()
        self.__admin_api: VkApiMethod = vk_admin_session.get_api()
        self.__uploader = VkUpload(vk_admin_session)
        self.__longpoll = VkBotLongPoll(vk_session, config.GROUP_ID)

    def get_bot_api(self) -> VkApiMethod:
        """Возвращает объект для работы с API с правами бота."""
        return self.__bot_api

    def get_admin_api(self) -> VkApiMethod:
        """Возвращает объект для работы с API с права юзера."""
        return self.__admin_api

    def get_upload(self) -> VkUpload:
        """Возвращает объект для загрузки файлов в ВК."""
        return self.__uploader

    def get_longpoll(self) -> VkBotLongPoll:
        """Возвращает объект для прослушивания ивентов."""
        return self.__longpoll
