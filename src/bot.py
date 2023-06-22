from vkbottle import BuiltinStateDispenser
from vkbottle.bot import Bot
from vkbottle.framework.labeler import BotLabeler

import config

labeler = BotLabeler()
state_dispenser = BuiltinStateDispenser()

bot = Bot(config.Settings.COMMUNITY_TOKEN)

bot.run_forever()
