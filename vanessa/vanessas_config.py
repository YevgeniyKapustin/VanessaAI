from os import path
from configparser import ConfigParser


def get_vanessa_config():
    """Returns the bot config"""
    config_patch = "config.ini"
    if not path.exists(config_patch):
        raise Exception("ini file not found")
    config = ConfigParser()
    config.read(config_patch)
    return config
