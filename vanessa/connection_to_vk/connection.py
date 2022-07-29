from vk_api.bot_longpoll import VkBotLongPoll
from vk_api import VkApi, VkUpload
from vk_api.vk_api import VkApiGroup
from vanessa.connection_to_vk.confidential_info import community_token, group_id, admin_token

vk_session = VkApiGroup(token=community_token)
vk = vk_session.get_api()

vk_admin_session = VkApi(token=admin_token)
vk_admin = vk_admin_session.get_api()

longpoll = VkBotLongPoll(vk_session, group_id)
upload = VkUpload(vk_admin_session)
