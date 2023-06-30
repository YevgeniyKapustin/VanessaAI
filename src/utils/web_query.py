from src.config import settings
from src.client import http_client


async def create_command(
        type_: str,
        request: str,
        response: str
) -> list[dict]:
    return await http_client.request_json(
        url=f'{settings.SERVER_URI}/api/v1/commands',
        method='POST',
        data={
            'type': type_.strip(),
            'request': request.strip(),
            'response': response.strip()
        }
    )


async def get_commands(
        request: str | None = None,
        type_: str | None = None
) -> list[dict]:
    if not request:
        return await http_client.request_json(
            url=f'{settings.SERVER_URI}/api/v1/commands',
            method='GET',
            params={
                'command_type': type_
            }
        )
    elif not type_:
        return await http_client.request_json(
            url=f'{settings.SERVER_URI}/api/v1/commands',
            method='GET',
            params={
                'request_': request,
            }
        )
