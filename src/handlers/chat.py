from random import randint, choice


from vkbottle.bot import Message
from vkbottle.framework.labeler import BotLabeler

from src.rules import DiceRule
from src.constants import civilizations, zmiys_phrases, hero_fractions

bl = BotLabeler()


@bl.message(text='цивилизация')
async def random_civ_from_civ6(message: Message):
    await message.answer(f'🎲 {choice(civilizations)}')


@bl.message(text='абоба')
async def random_zmiys_phrases(message: Message):
    await message.answer(f'{choice(zmiys_phrases)}')


@bl.message(text='фракция')
async def random_fraction(message: Message):
    await message.answer(f'🎲 {choice(hero_fractions)}')


@bl.message(DiceRule())
async def roll_dice(message: Message):
    await message.answer(f'🎲 {randint(1, int(message.text.replace("д", "")))}')


@bl.message(text='сус')
async def command(message: Message):
    await message.answer(attachment='doc465630601_633778583')


@bl.message(text='жидкость')
async def command(message: Message):
    await message.answer(attachment='doc465630601_639105924')


@bl.message(text='рекрут сус')
async def command(message: Message):
    await message.answer(attachment='doc465630601_638241402')


@bl.message(text='рекрут сус')
async def command(message: Message):
    await message.answer(attachment='doc465630601_638626230')


@bl.message(text='холод')
async def command(message: Message):
    await message.answer(attachment='doc465630601_634335482')


@bl.message(text='чопалах')
async def command(message: Message):
    await message.answer(attachment='doc465630601_635449078')


@bl.message(text='балдёж')
async def command(message: Message):
    await message.answer(attachment='doc2000012525_646920632')


@bl.message(text='танцы')
async def command(message: Message):
    await message.answer(attachment='doc465630601_648571112')


@bl.message(text='туса')
async def command(message: Message):
    await message.answer(attachment='doc2000013324_643789938')


@bl.message(text='сус танцы')
async def command(message: Message):
    await message.answer(attachment='doc465630601_649109900')


@bl.message(text='сус')
async def command(message: Message):
    await message.answer(attachment='doc465630601_633778583')


@bl.message(text='плавск')
async def command(message: Message):
    await message.answer(attachment='doc465630601_649982116')


@bl.message(text='сус')
async def command(message: Message):
    await message.answer(attachment='doc465630601_633778583')


@bl.message(text='сусик')
async def command(message: Message):
    await message.answer(attachment='doc465630601_650924992')


@bl.message(text='май литтл сус')
async def command(message: Message):
    await message.answer(attachment='doc465630601_652282669')


@bl.message(text='мужики')
async def command(message: Message):
    await message.answer(attachment='doc2000043489_654947303')


@bl.message(text='браво')
async def command(message: Message):
    await message.answer(attachment='doc465630601_634380706')


@bl.message(text='бесплатн')
async def command(message: Message):
    await message.answer(attachment='doc465630601_634380794')


@bl.message(text='платн')
async def command(message: Message):
    await message.answer(attachment='doc465630601_634329506')


@bl.message(text='зарплат')
async def command(message: Message):
    await message.answer(attachment='doc465630601_634236546')


@bl.message(text='кринж')
async def command(message: Message):
    await message.answer(attachment='photo-212138773_457239023')


@bl.message(text='резня')
async def command(message: Message):
    await message.answer(attachment='photo-212138773_457239022')


@bl.message(text='зомби в топе')
async def command(message: Message):
    await message.answer(attachment='photo-212138773_457239032')


@bl.message(text='айко')
async def command(message: Message):
    await message.answer('енотья сила')


@bl.message(text='амогус')
async def command(message: Message):
    await message.answer('тутуту')


@bl.message(text='сууууус')
async def command(message: Message):
    await message.answer('сус отменяется')


@bl.message(text='сбылась мечта')
async def command(message: Message):
    await message.answer('абоба')


@bl.message(text='гриша сус')
async def command(message: Message):
    await message.answer('есть пробитие')


@bl.message(text='кейт сус')
async def command(message: Message):
    await message.answer('очень сус')


@bl.message(text='красавица')
async def command(message: Message):
    await message.answer('и сусовище')


@bl.message(text='уютненько')
async def command(message: Message):
    await message.answer('обед')


@bl.message(text='ванесса')
async def command(message: Message):
    await message.answer('а я ниче такая да')


@bl.message(text='влад')
async def command(message: Message):
    await message.answer(' капустный стратег😎')


@bl.message(text='рору')
async def command(message: Message):
    await message.answer('станиславозавр')


@bl.message(text='капуста сус')
async def command(message: Message):
    await message.answer('невероятный русский')


@bl.message(text='гриша не сус')
async def command(message: Message):
    await message.answer('рикошет')


@bl.message(text='банан')
async def command(message: Message):
    await message.answer(' 🍌')


@bl.message(text='тулик')
async def command(message: Message):
    await message.answer('молодец')


@bl.message(text='гриша сус')
async def command(message: Message):
    await message.answer('есть пробитие')


@bl.message(text='правила')
async def command(message: Message):
    await message.answer('1) капуста всегда прав <br>2) личь никого не бесит')


@bl.message(text='гитхаб')
async def command(message: Message):
    await message.answer('https://github.com/Kapusta-fairy')
