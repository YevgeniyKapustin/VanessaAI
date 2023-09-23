from vkbottle import AiohttpClient, Bot

from src.config import settings

bot: Bot = Bot(settings.COMMUNITY_TOKEN)
http_client: AiohttpClient = AiohttpClient()
