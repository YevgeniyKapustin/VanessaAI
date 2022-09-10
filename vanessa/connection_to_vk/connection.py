from vk_api.bot_longpoll import VkBotLongPoll
from vk_api import VkApi, VkUpload
from vk_api.vk_api import VkApiGroup
from vanessas_config import get_vanessas_config
config = get_vanessas_config()

vk_session = VkApiGroup(token=config.get("connection", "community_token"))
vk = vk_session.get_api()

vk_admin_session = VkApi(token=config.get("connection", "admin_token"))
vk_admin = vk_admin_session.get_api()

longpoll = VkBotLongPoll(vk_session, config.get("connection", "group_id"))
upload = VkUpload(vk_admin_session)
