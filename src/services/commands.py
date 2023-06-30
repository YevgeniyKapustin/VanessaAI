from vkbottle.bot import Message

from src.utils import web_query


class Command(object):
    _request: str | None = None
    _response: str | None = None
    _type: str | None = None
    _message: Message

    def __init__(self, message: Message, request: str):
        self._request = request
        self._message = message

    async def definition(self):
        await self._definition_normal()
        await self._definition_contextual()

    async def _definition_normal(self):
        commands = await web_query.get_commands(request=self._request)
        if self._response_validation(commands):

            for command in commands:
                await self._answer(command)
                break

    async def _definition_contextual(self):
        for contextual_type in contextual_types:
            commands = await web_query.get_commands(type_=contextual_type)
            if self._response_validation(commands):

                for command in commands:
                    if command.get('request') in self._request:
                        await self._message.answer(command.get('response'))
                        break

    @staticmethod
    async def _response_validation(commands):
        return not hasattr(commands, 'request') or type(commands) is list
