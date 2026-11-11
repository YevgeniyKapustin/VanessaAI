"""A watch with ``rich: true`` carries both shapes: the text and the card."""

from datetime import UTC, datetime, timedelta, timezone

from services.worker.announce.card_html import links_to_html
from services.worker.announce.compose import AnnounceComposer
from services.worker.announce.content import WatchSpec
from services.worker.announce.models import Actor, Announcement, Item
from vanessa.llm.generation import LLMGenerationParams

TZ = timezone(timedelta(hours=4))
URL = "https://git.example/app/-/pipelines/79545"
ROLLOUT = "https://grafana.example/d/tenants?var-stand=prod"
CARD_URL = "https://board.example/ws/browse/{card}/"


def spec(*, rich: bool) -> WatchSpec:
    return WatchSpec(
        id="deploy",
        kind="deploy",
        state_key="vanessa:deploy_last_job",
        header="Релиз [{release}]({url})",
        footer="[Раскатка тенантов на проде]({links[rollout]})",
        task="TASK",
        rich=rich,
    )


def composer(*, rich: bool) -> AnnounceComposer:
    return AnnounceComposer(
        None,
        model="test-model",
        system_prompt="PERSONA",
        spec=spec(rich=rich),
        generation=LLMGenerationParams(temperature=0.5, top_p=0.9, max_tokens=900),
        zone=TZ,
        links={"rollout": ROLLOUT},
        card_url=CARD_URL,
    )


def event() -> Announcement:
    return Announcement(
        key=79545,
        when=datetime(2026, 11, 10, 9, 26, tzinfo=UTC),
        url=URL,
        actor=Actor(name="Анна Петрова", username="a.petrova"),
        items=(
            Item(title="[ABC-101] Карта интерфейса", author="Анна Петрова"),
            Item(title="[ABC-101] Пины навыков", author="Анна Петрова"),
            Item(title="Свести production в ветку", author="Игорь"),
            Item(title="[XYZ-202] Авто-MoA в личном чате", author="Анна Петрова"),
        ),
        total=143,
        release="v0.1.6 (79545)",
    )


async def test_plain_text_keeps_the_release_header() -> None:
    composed = await composer(rich=True).compose_all(event(), stand_ready=True)
    assert composed.text.splitlines()[0] == f"Релиз [v0.1.6 (79545)]({URL})"


async def test_rich_watch_adds_a_folded_card() -> None:
    composed = await composer(rich=True).compose_all(event(), stand_ready=True)
    html = composed.rich_html or ""
    visible, folded = html.split("<details>", 1)
    assert f'<a href="{URL}">v0.1.6 (79545)</a>' in visible
    assert "разбор: 143 коммита, 2 карточки" in folded
    assert '<a href="https://board.example/ws/browse/ABC-101/">ABC-101</a>' in folded
    assert f'<a href="{ROLLOUT}">Раскатка тенантов на проде</a>' in folded


async def test_plain_watch_posts_no_card() -> None:
    composed = await composer(rich=False).compose_all(event(), stand_ready=True)
    assert composed.rich_html is None
    assert composed.text


def test_links_to_html_keeps_anchors_and_escapes_the_rest() -> None:
    html = links_to_html("Релиз [v0.1.6](https://e/x?a=1&b=2) <b>")
    assert html == 'Релиз <a href="https://e/x?a=1&amp;b=2">v0.1.6</a> &lt;b&gt;'
