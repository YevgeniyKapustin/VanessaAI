from loguru import logger

from src import config
from src.services import vk
from src.utils.queries import get_commands


def update_command_list() -> None:
    commands: list = [
        f'{i.get("type")} | {i.get("request")}: {i.get("response")}'
        for i in get_commands().json()
    ]
    vk.get_admin_api().board.editComment(
        group_id=config.GROUP_ID,
        topic_id=49520072,
        comment_id=5,
        message='\n'.join(sorted(commands))
    )

    logger.info(f'Команды обновлены')
