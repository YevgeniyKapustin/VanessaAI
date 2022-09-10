from configparser import ConfigParser
from os import path


def get_vanessas_config():
    config_patch = "config.ini"
    if not path.exists(config_patch):
        raise Exception("ini file not found")
    config = ConfigParser()
    config.read(config_patch)
    return config
