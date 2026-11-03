from types import SimpleNamespace

from services.worker.announce.mention import find_mention
from vanessa.infrastructure.db.models import User

LEONID = {
    "telegram_id": 327160360,
    "username": "Canoist",
    "first_name": "Leonid ℂ𝕒𝕟𝕠𝕚𝕤𝕥",
    "last_name": "Lichkun",
}
VIACHESLAV = {
    "telegram_id": 311022903,
    "username": "shyrocky",
    "first_name": "Viacheslav",
    "last_name": "Titov",
}


class _Result:
    def __init__(self, users: list[User]) -> None:
        self._users = users

    def scalars(self):
        return SimpleNamespace(all=lambda: self._users)


class _Session:
    def __init__(self, users: list[User]) -> None:
        self._users = users

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, _statement):
        return _Result(self._users)


def _factory(users: list[User]):
    def factory():
        return _Session(users)

    return factory


def _user(data: dict) -> User:
    return User(**data)


async def test_full_gitlab_name_resolves_to_the_chat_username() -> None:
    mention = await find_mention(_factory([_user(LEONID)]), "Leonid Lichkun")

    assert mention is not None
    assert mention.username == "Canoist"
    assert mention.telegram_id == 327160360
    assert mention.markdown == "[@Canoist](tg://user?id=327160360)"


async def test_stylised_unicode_in_the_stored_name_is_normalised() -> None:
    mention = await find_mention(_factory([_user(LEONID)]), "leonid LICHKUN")

    assert mention is not None
    assert mention.username == "Canoist"


async def test_one_word_name_needs_the_exact_username() -> None:
    users = [_user(LEONID), _user(VIACHESLAV)]

    assert await find_mention(_factory(users), "Canoist") is not None
    assert await find_mention(_factory(users), "Leonid") is None


async def test_unknown_name_resolves_to_nothing() -> None:
    assert await find_mention(_factory([_user(LEONID)]), "Ivan Petrov") is None
    assert await find_mention(_factory([_user(LEONID)]), "") is None
