"""The model's pool of commits, and the wording rules that pick from it.

The last production release told the chat about a security decision and two
fixes and dropped the one new capability it shipped (a tool that names
itself), so these tests pin both halves: paperwork never reaches the model,
a technically titled capability does.
"""

from datetime import UTC, datetime, timedelta, timezone

from services.worker.announce.content import WATCH_DIR, WatchSpec, load_watch
from services.worker.announce.models import Announcement, Item
from services.worker.announce.prompt import build_prompt, is_noise, item_lines
from vanessa.config.content import resolve_content_source

TZ = timezone(timedelta(hours=4))
SPEC = WatchSpec(
    id="deploy",
    kind="deploy",
    state_key="vanessa:deploy_last_job",
    path="/deploy/latest",
    header="Релиз [{release}]({url})",
    task="TASK",
    fallback_bullet="• {title}",
    fallback_more="…и ещё {count} коммитов",
)

#: The shape of a real 21-commit release: three merges, eight documents, ten
#: changes — one of them a capability that names the tool it ships.
IN_RELEASE = (
    "Merge branch 'hotfix/abc-101-skills-materializer-prod' into 'production'",
    "Перенести фикс навыков прод-коробок в production",
    "Материализатор навыков пишет в каталог состояния с правом записи",
    "Навыки: отдельный таймер frontdoor снова импортирует модуль сверки",
    "Merge branch 'hotfix/abc-102-agent-service-key' into 'production'",
    "[ABC-103] Слить в целевую ветку",
    "[ABC-103-prod] Перезапустить проверки MR с обновлённым описанием",
    "Поднять бюджет правил чата под новую строку замера",
    "Назвать в спеке предшествующие работы и открытые вопросы",
    "Уточнить в спеке и ADR, чем подтверждается выпуск ключа",
    "Добавить инструмент коробки, который выпускает ключ на странице сервиса",
    "Провести право на выпуск сервисного ключа от комнаты до коробки",
    "Повторять вызов роутера один раз после таймаута",
    "Спека ABC-103: панель теряется на холодном роутере",
    "Разрешить агенту выпускать сервисный ключ только по согласию владельца",
    "Передавать право на выпуск сервисного ключа закреплённым заголовком",
    "Зафиксировать решение по сервисным ключам для ABC-102",
    "Merge branch 'hotfix/abc-104-sheet-tool-v2' into 'production'",
    "ABC-104: запись о прогоне в спеке",
    "ABC-104: в переносе — версия инструмента из main",
    "ABC-104: инструмент acme_sheet в production",
)
PAPERWORK = (
    IN_RELEASE[0],
    IN_RELEASE[4],
    IN_RELEASE[5],
    IN_RELEASE[6],
    IN_RELEASE[8],
    IN_RELEASE[9],
    IN_RELEASE[13],
    IN_RELEASE[16],
    IN_RELEASE[17],
    IN_RELEASE[18],
    IN_RELEASE[19],
)
CAPABILITY = IN_RELEASE[20]
AUTHOR = "Разработчик"


def announcement(titles: tuple[str, ...] = IN_RELEASE) -> Announcement:
    return Announcement(
        key=1035759,
        when=datetime(2026, 11, 12, 14, 29, tzinfo=UTC),
        url="https://git.example/app/-/pipelines/84361",
        items=tuple(Item(title=title, author=AUTHOR) for title in titles),
        total=len(titles),
        release="v1.2.3 (84361)",
    )


def test_merges_and_paperwork_are_noise_and_code_is_not() -> None:
    assert all(is_noise(title) for title in PAPERWORK)
    assert not is_noise(CAPABILITY)


def test_the_pool_keeps_the_capability_and_drops_the_paperwork() -> None:
    lines = item_lines(announcement())

    assert f"- {CAPABILITY} ({AUTHOR})" in lines
    assert len(lines) == len(IN_RELEASE) - len(PAPERWORK)
    assert not any(is_noise(line) for line in lines)


def test_a_release_of_paperwork_alone_still_reaches_the_model() -> None:
    lines = item_lines(announcement(PAPERWORK))

    assert len(lines) == len(PAPERWORK)
    assert lines[0] == f"- {PAPERWORK[0]} ({AUTHOR})"


def test_the_prompt_carries_the_real_count_and_no_paperwork() -> None:
    user = build_prompt(SPEC, announcement(), stand_ready=True, zone=TZ)

    assert "изменений в выпуске: 21" in user
    assert f"- {CAPABILITY}" in user
    assert "Спека ABC-103" not in user


def test_the_shipped_task_ranks_a_capability_above_an_internal_decision() -> None:
    """A prompt edit that loses the ranking rule must fail here, not in chat."""
    path = resolve_content_source() / WATCH_DIR / "deploy.yaml"
    task = load_watch(path).task

    assert "order of preference" in task
    assert "new capability" in task
    assert "never drop it because" in task
    assert "its title is technical" in task
    assert "not a change for people: skip it" in task
