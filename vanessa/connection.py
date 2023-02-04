"""Stores the class of the same name for working with the connection"""
from os import path
from configparser import ConfigParser

from vk_api.bot_longpoll import VkBotLongPoll
from vk_api.vk_api import VkApiGroup
from vk_api import VkApi, VkUpload


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
        self.__config = self.__get_vanessa_config()

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

    def __get_vanessa_config(self):
        """Returns the bot config"""
        config_patch = "config.ini"
        if not path.exists(config_patch):
            with open(config_patch, 'w') as write_f:
                write_f.write(self.__create_config_file())
        config = ConfigParser()
        config.read(config_patch)
        return config

    def __create_config_file(self):
        print('ini file not found, input community_token:')
        community_token = input()
        print('input admin_token:')
        admin_token = input()
        print('input group_id:')
        group_id = input()

        return self.__create_config_str(community_token, admin_token, group_id)

    @staticmethod
    def __create_config_str(community_token, admin_token, group_id):
        return f'[connection]\ncommunity_token = {community_token}\n' \
               f'admin_token = {admin_token}\ngroup_id = {group_id}'
