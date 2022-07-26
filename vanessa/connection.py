from vk_api.bot_longpoll import VkBotLongPoll
from vk_api import VkApi
from vanessa.confidential_info import token, group_id

vk_session = VkApi(token=token)
longpoll = VkBotLongPoll(vk_session, group_id)
api_session = vk_session.get_api()
