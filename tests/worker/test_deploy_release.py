"""The release label: a tag alone, or the newest tag plus the deploy number."""

from services.worker.deploys.models import DeployEvent, DeployPipeline
from services.worker.deploys.release import event_release, release_label


def test_a_tagged_deploy_is_the_tag_alone() -> None:
    assert release_label(tag="v0.1.7", latest_tag="v0.1.7", number="79545") == "v0.1.7"


def test_an_untagged_deploy_names_the_tag_and_its_number() -> None:
    assert release_label(tag="", latest_tag="v0.1.6", number="79545") == "v0.1.6 (79545)"


def test_without_a_number_the_tag_stands_alone() -> None:
    assert release_label(tag="", latest_tag="v0.1.6", number="") == "v0.1.6"


def test_without_any_tag_the_number_is_the_label() -> None:
    assert release_label(tag="", latest_tag="", number="79545") == "79545"


def test_nothing_known_gives_an_empty_label() -> None:
    assert release_label(tag="  ", latest_tag="", number="") == ""


def test_the_event_uses_the_pipeline_id_as_the_number() -> None:
    event = DeployEvent(job_id=960707, pipeline=DeployPipeline(id=79545))
    assert event_release(event) == "79545"


def test_the_bridge_tag_wins_over_the_number() -> None:
    event = DeployEvent(
        job_id=960707,
        pipeline=DeployPipeline(id=79545),
        tag="v0.1.7",
        latest_tag="v0.1.7",
    )
    assert event_release(event) == "v0.1.7"
