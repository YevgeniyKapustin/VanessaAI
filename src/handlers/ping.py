from vkbottle.framework.labeler import BotLabeler

bl = BotLabeler()


@bl.message(text="ping")
async def ping_handler(message):
    await message.answer("pong")
