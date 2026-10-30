from vanessa.config import settings
from vanessa.config.content_sections import MetricsHandicapContent
from vanessa.knowledge.metrics.handicap import apply_handicap, apply_owner_handicap
from vanessa.knowledge.metrics.schema import Distance, PersonMetrics

HANDICAP = MetricsHandicapContent(enabled=True)


def test_handicap_raises_floors_and_lowers_ceilings() -> None:
    message_count = 120
    metrics = PersonMetrics(
        valence=-0.8,
        toxicity=0.9,
        trust_score=10,
        distance=Distance.FORMAL,
        sympathy=-0.7,
        sarcasm_index=0.9,
        constructiveness=0.0,
        support_index=0.0,
        message_count=message_count,
    )
    got = apply_handicap(metrics, HANDICAP)
    assert got.valence == HANDICAP.valence
    assert got.sympathy == HANDICAP.sympathy
    assert got.trust_score == HANDICAP.trust_score
    assert got.constructiveness == HANDICAP.constructiveness
    assert got.support_index == HANDICAP.support_index
    assert got.toxicity == HANDICAP.toxicity
    assert got.sarcasm_index == HANDICAP.sarcasm_index
    assert got.distance == Distance.FRIENDLY
    # Deterministic counters are facts: never clamped.
    assert got.message_count == message_count


def test_handicap_fills_missing_friendly_fields_only() -> None:
    got = apply_handicap(PersonMetrics(), HANDICAP)
    assert got.trust_score == HANDICAP.trust_score
    assert got.distance == Distance.FRIENDLY
    # A missing hostile value is already favourable — nothing to lower.
    assert got.toxicity is None
    assert got.sarcasm_index is None


def test_handicap_keeps_better_values() -> None:
    good_valence = 0.9
    good_trust = 95
    metrics = PersonMetrics(
        valence=good_valence,
        trust_score=good_trust,
        distance=Distance.FAMILIAR,
        toxicity=0.0,
        sarcasm_index=0.0,
    )
    got = apply_handicap(metrics, HANDICAP)
    assert got.valence == good_valence
    assert got.trust_score == good_trust
    assert got.distance == Distance.FAMILIAR
    assert got.toxicity == 0.0


def test_handicap_clamps_config_out_of_range() -> None:
    max_trust = 100
    max_valence = 1.0
    wild = MetricsHandicapContent(
        enabled=True, trust_score=500, valence=9, distance="nonsense"
    )
    got = apply_handicap(PersonMetrics(distance=Distance.BUSINESS), wild)
    assert got.trust_score == max_trust
    assert got.valence == max_valence
    # An unknown distance inherits no floor.
    assert got.distance == Distance.BUSINESS


def _combined() -> dict[str, tuple[int | None, str | None, PersonMetrics]]:
    bad = PersonMetrics(
        valence=-1.0, trust_score=0, distance=Distance.FORMAL, toxicity=1.0
    )
    return {"user-7": (7, "owner", bad), "user-8": (8, "guest", bad)}


def test_owner_handicap_touches_only_the_owner(monkeypatch) -> None:
    monkeypatch.setattr(settings, "required_user_telegram_id", 7)
    monkeypatch.setattr(settings, "owner_extra_telegram_ids", "")
    combined = _combined()
    apply_owner_handicap(combined, HANDICAP)
    owner = combined["user-7"][2]
    guest = combined["user-8"][2]
    assert owner.trust_score == HANDICAP.trust_score
    assert owner.distance == Distance.FRIENDLY
    assert guest.trust_score == 0
    assert guest.distance == Distance.FORMAL


def test_owner_handicap_respects_disabled_and_extra_ids(monkeypatch) -> None:
    monkeypatch.setattr(settings, "required_user_telegram_id", 0)
    monkeypatch.setattr(settings, "owner_extra_telegram_ids", "7, 9")
    combined = _combined()
    apply_owner_handicap(combined, MetricsHandicapContent(enabled=False))
    assert combined["user-7"][2].trust_score == 0
    apply_owner_handicap(combined, HANDICAP)
    assert combined["user-7"][2].trust_score == HANDICAP.trust_score
