from vk_api.bot_longpoll import VkBotLongPoll
from vk_api.vk_api import VkApiGroup
from vk_api import VkApi, VkUpload

from prepare.config import Config


class Connection:
    """Establishes a connection with VK and serves to store variables for
    storing connection data
    variables:
        vk: vk api object using a community token
        vk_admin: vk api object using an admin token
        longpoll: object for working with community events
        upload: file upload object
    """
    def __init__(self):
        self.__config = Config().get_config()

        self.__vk_session = VkApiGroup(
            token=self.__config.get('connection', 'community_token')
        )
        self.__vk_admin_session = VkApi(
            token=self.__config.get('connection', 'admin_token'))

        self.vk = self.__vk_session.get_api()
        self.vk_admin = self.__vk_admin_session.get_api()
        self.upload = VkUpload(self.__vk_admin_session)

        self.longpoll = VkBotLongPoll(
            self.__vk_session,
            self.__config.get('connection', 'group_id')
        )
