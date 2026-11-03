from datetime import UTC, datetime, timedelta, timezone

from services.worker.announce.compose import AnnounceComposer
from services.worker.announce.content import WatchSpec
from services.worker.announce.mention import Participant
from services.worker.announce.models import Actor, Announcement, Item
from tests.worker.hermes_fakes import FakeCompleter
from vanessa.llm.generation import LLMGenerationParams

TZ = timezone(timedelta(hours=4))
URL = "https://git.example/app/-/pipelines/70795"
ROLLOUT = (
    "https://grafana.example/d/app-prod-tenants/"
    "app-c2b7-tenanty-i-raskatka?orgId=1&var-stand=prod"
)
SPEC = WatchSpec(
    id="deploy",
    kind="deploy",
    state_key="vanessa:deploy_last_job",
    path="/deploy/latest",
    header="На прод [выкатили в {when}]({url}) — выкатывал {started_by}",
    footer="[Раскатка тенантов на проде]({links[rollout]})",
    task="TASK",
    fallback_bullet="• {title}",
    fallback_more="…и ещё {count} коммитов",
    stand_down_line="Стенд пока не отвечает",
)
FINISHED = datetime(2026, 11, 3, 8, 54, tzinfo=UTC)
HEADER = (
    f"На прод [выкатили в 12:54]({URL}) — выкатывал Viacheslav Titov (@v.titov)"
)
ROLLOUT_LINE = f"[Раскатка тенантов на проде]({ROLLOUT})"


def event(items: int = 7, *, url: str = URL) -> Announcement:
    return Announcement(
        key=839023,
        when=FINISHED,
        url=url,
        actor=Actor(name="Viacheslav Titov", username="v.titov"),
        items=tuple(Item(title=f"feat {index}", author="dev") for index in range(items)),
        total=items,
    )


def composer(
    completer: FakeCompleter | None, *, rollout: str = ROLLOUT
) -> AnnounceComposer:
    return AnnounceComposer(
        completer,
        model="test-model",
        system_prompt="PERSONA",
        spec=SPEC,
        generation=LLMGenerationParams(temperature=0.5, top_p=0.9, max_tokens=900),
        zone=TZ,
        links={"rollout": rollout},
    )


async def test_fallback_has_header_five_items_rest_count_and_footer() -> None:
    text = await composer(None).compose(event(), stand_ready=True)
    lines = text.splitlines()
    assert lines[0] == HEADER
    assert lines[1] == ""
    assert text.count("• ") == 5
    assert "…и ещё 2 коммитов" in text
    assert lines[-1] == ROLLOUT_LINE


async def test_llm_bullets_go_between_the_code_built_blocks() -> None:
    completer = FakeCompleter("[answer]\n• На входе теперь код, а не пароль")
    text = await composer(completer).compose(event(), stand_ready=True)
    assert text.splitlines() == [
        HEADER,
        "",
        "• На входе теперь код, а не пароль",
        "",
        ROLLOUT_LINE,
    ]
    assert completer.calls[0]["kind"] == "deploy_announcement"


async def test_filler_lines_from_the_model_are_dropped() -> None:
    completer = FakeCompleter(
        "[answer]\nВыкатили на прод\n• Реальный пункт\n"
        "• Остальное в выпуске техническое\n• Для продукта ничего не меняет"
    )
    text = await composer(completer).compose(event(), stand_ready=True)
    assert text.splitlines() == [HEADER, "", "• Реальный пункт", "", ROLLOUT_LINE]


async def test_no_product_changes_post_header_and_footer_only() -> None:
    completer = FakeCompleter("[answer]")
    text = await composer(completer).compose(event(), stand_ready=True)
    assert text.splitlines() == [HEADER, "", ROLLOUT_LINE]


async def test_a_single_change_is_named_even_when_it_is_technical() -> None:
    text = await composer(FakeCompleter("[answer]")).compose(
        event(items=1), stand_ready=True
    )

    assert "• feat 0" in text.splitlines()


async def test_several_technical_items_post_no_bullets() -> None:
    text = await composer(FakeCompleter("[answer]")).compose(
        event(items=3), stand_ready=True
    )

    assert "• " not in text


async def test_without_a_rollout_link_the_footer_disappears() -> None:
    text = await composer(None, rollout="").compose(event(), stand_ready=True)

    assert text.splitlines()[0] == HEADER
    assert "Раскатка тенантов" not in text


async def test_without_a_source_link_the_header_keeps_plain_words() -> None:
    text = await composer(None).compose(event(url=""), stand_ready=True)

    assert text.splitlines()[0] == (
        "На прод выкатили в 12:54 — выкатывал Viacheslav Titov (@v.titov)"
    )


async def test_stand_not_answering_is_added_by_the_app_and_in_the_prompt() -> None:
    completer = FakeCompleter("[answer]\n• Пункт")
    text = await composer(completer).compose(event(), stand_ready=False)
    assert "Стенд пока не отвечает" in text.splitlines()
    user_prompt = completer.calls[0]["messages"][-1]["content"]
    assert "стенд: пока не отвечает" in user_prompt
    assert "изменений в выпуске: 7" in user_prompt
    assert URL in user_prompt


async def test_resolved_participant_is_tagged_in_the_header() -> None:
    mention = Participant(telegram_id=327160360, username="Canoist", name="Leonid Lichkun")
    text = await composer(None).compose(event(), stand_ready=True, mention=mention)

    assert text.splitlines()[0] == (
        f"На прод [выкатили в 12:54]({URL}) — "
        "выкатывал [@Canoist](tg://user?id=327160360)"
    )


async def test_unresolved_actor_falls_back_to_the_source_label() -> None:
    text = await composer(None).compose(event(), stand_ready=True)

    assert text.splitlines()[0] == HEADER


async def test_llm_error_falls_back_to_raw_titles() -> None:
    text = await composer(FakeCompleter(error=RuntimeError("provider down"))).compose(
        event(), stand_ready=True
    )
    assert text.splitlines()[0] == HEADER
    assert text.count("• ") == 5


async def test_untagged_answer_falls_back_to_raw_titles() -> None:
    text = await composer(FakeCompleter("без тега")).compose(event(), stand_ready=None)
    assert text.splitlines()[0] == HEADER
    assert text.count("• ") == 5
