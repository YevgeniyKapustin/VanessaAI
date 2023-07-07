import json

from vkbottle.bot import Message

from src.constants import attachment_types
from src.utils import web_query


async def create_response_json(message: Message, response: str) -> str:
    attachments = ''
    for obj_attch in message.attachments:
        for attch_type in attachment_types:
            if attch := getattr(obj_attch, attch_type):
                attachments += (
                    f'{attch_type}{attch.owner_id}_'
                    f'{attch.id}_{attch.access_key},'
                )

    return json.dumps(
        {
            'message': response.strip(),
            'attch': attachments.strip()[:-1]
        }
    )


async def get_data(request: str) -> str:
    commands = await web_query.get_commands(request=request)
    if type(commands) is dict and (error := commands.get('message')):
        return error
    for command in commands:
        if not command.get('type') == '_':
            return command.get('response')
    commands = await web_query.get_commands(type_='_')
    for command in commands:
        return command.get('response')
