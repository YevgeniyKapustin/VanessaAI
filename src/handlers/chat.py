from random import randint, choice


from vkbottle.bot import Message
from vkbottle.framework.labeler import BotLabeler

from src.rules import DiceRule, TextRule
from src.constants import civilizations, zmiys_phrases, hero_fractions

bl = BotLabeler()


@bl.message(TextRule('цивилизация'))
async def random_civ_from_civ6(message: Message):
    await message.answer(f'🎲 {choice(civilizations)}')


@bl.message(TextRule('абоба'))
async def random_zmiys_phrases(message: Message):
    await message.answer(f'{choice(zmiys_phrases)}')


@bl.message(TextRule('фракция'))
async def random_fraction(message: Message):
    await message.answer(f'🎲 {choice(hero_fractions)}')


@bl.message(DiceRule())
async def roll_dice(message: Message):
    await message.answer(f'🎲 {randint(1, int(message.text.replace("д", "")))}')


@bl.message(TextRule('сус'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_633778583')


@bl.message(TextRule('жидкость'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_639105924')


@bl.message(TextRule('рекрут сус'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_638241402')


@bl.message(TextRule('рекрут сус'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_638626230')


@bl.message(TextRule('холод'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_634335482')


@bl.message(TextRule('чопалах'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_635449078')


@bl.message(TextRule('балдёж'))
async def command(message: Message):
    await message.answer(attachment='doc2000012525_646920632')


@bl.message(TextRule('танцы'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_648571112')


@bl.message(TextRule('туса'))
async def command(message: Message):
    await message.answer(attachment='doc2000013324_643789938')


@bl.message(TextRule('сус танцы'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_649109900')


@bl.message(TextRule('сус'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_633778583')


@bl.message(TextRule('плавск'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_649982116')


@bl.message(TextRule('сус'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_633778583')


@bl.message(TextRule('сусик'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_650924992')


@bl.message(TextRule('май литтл сус)'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_652282669')


@bl.message(TextRule('мужики'))
async def command(message: Message):
    await message.answer(attachment='doc2000043489_654947303')


@bl.message(TextRule('браво'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_634380706')


@bl.message(TextRule('бесплатн'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_634380794')


@bl.message(TextRule('платн'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_634329506')


@bl.message(TextRule('зарплат'))
async def command(message: Message):
    await message.answer(attachment='doc465630601_634236546')


@bl.message(TextRule('кринж'))
async def command(message: Message):
    await message.answer(attachment='photo-212138773_457239023')


@bl.message(TextRule('резня'))
async def command(message: Message):
    await message.answer(attachment='photo-212138773_457239022')


@bl.message(TextRule('зомби в топе)'))
async def command(message: Message):
    await message.answer(attachment='photo-212138773_457239032')


@bl.message(TextRule('айко'))
async def command(message: Message):
    await message.answer('енотья сила')


@bl.message(TextRule('амогус'))
async def command(message: Message):
    await message.answer('тутуту')


@bl.message(TextRule('сууууус'))
async def command(message: Message):
    await message.answer('сус отменяется')


@bl.message(TextRule('сбылась мечта'))
async def command(message: Message):
    await message.answer('абоба')


@bl.message(TextRule('гриша сус'))
async def command(message: Message):
    await message.answer('есть пробитие')


@bl.message(TextRule('кейт сус'))
async def command(message: Message):
    await message.answer('очень сус')


@bl.message(TextRule('красавица'))
async def command(message: Message):
    await message.answer('и сусовище')


@bl.message(TextRule('уютненько'))
async def command(message: Message):
    await message.answer('обед')


@bl.message(TextRule('ванесса'))
async def command(message: Message):
    await message.answer('а я ниче такая да')


@bl.message(TextRule('влад'))
async def command(message: Message):
    await message.answer(' капустный стратег😎')


@bl.message(TextRule('рору'))
async def command(message: Message):
    await message.answer('станиславозавр')


@bl.message(TextRule('капуста сус'))
async def command(message: Message):
    await message.answer('невероятный русский')


@bl.message(TextRule('гриша не сус)'))
async def command(message: Message):
    await message.answer('рикошет')


@bl.message(TextRule('банан'))
async def command(message: Message):
    await message.answer('🍌')


@bl.message(TextRule('тулик'))
async def command(message: Message):
    await message.answer('молодец')


@bl.message(TextRule('гриша сус'))
async def command(message: Message):
    await message.answer('есть пробитие')


@bl.message(TextRule('правила'))
async def command(message: Message):
    await message.answer('1) капуста всегда прав <br>2) личь никого не бесит')


@bl.message(TextRule('гитхаб'))
async def command(message: Message):
    await message.answer('https://github.com/Kapusta-fairy')
