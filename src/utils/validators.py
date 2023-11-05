def check_mention(text: str) -> str:
    assert '[id' not in text and '|' not in text and ']' not in text, \
        f'Нельзя создавать команды с упоминаниями'
    return text


def check_type(type_: str) -> str:
    assert type_ in {'текст', 'гиф', 'изображение'}, \
        f'"{type_}" недопустимый тип команды'
    return type_
