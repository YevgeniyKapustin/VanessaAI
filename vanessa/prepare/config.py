from os import path
from configparser import ConfigParser


class Config:
    """Class for working with the bot config."""
    def get_config(self):
        """Returns the bot config.
        if it does not exist, you will be prompted to create it
        by entering data in the console.


        """
        config_patch = "service_files/config.ini"

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
