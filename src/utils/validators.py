from src.constants import commands_types


def check_mention(text: str):
    assert '[id' not in text and '|' not in text and ']' not in text, \
        f'Нельзя создавать команды с упоминаниями'


def check_type(type_: str):
    assert type_ in commands_types, \
        f'"{type_}" недопустимый тип команды'
