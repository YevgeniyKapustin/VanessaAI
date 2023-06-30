from vkbottle.bot import Bot

from src.handlers import labelers
from src.config import settings


bot: Bot = Bot(settings.COMMUNITY_TOKEN)
[bot.labeler.load(labeler) for labeler in labelers]
bot.run_forever()
