from app.core.nicknames import find_nicknames_in_text
from app.llm.turn_planner import TurnPlan
from app.rag.search_plan import build_main_rag_plan


def test_find_nicknames_in_text_matches_inflected_form():
    assert "Тик так" in find_nicknames_in_text("что думаешь про тик така")


def test_build_main_rag_plan_embeds_original_and_subquery():
    plan = build_main_rag_plan(
        "что думаешь про тик така",
        TurnPlan(
            original="что думаешь про тик така",
            text="тик ток платформа",
            skip_search=False,
        ),
    )

    assert plan.semantic_queries == (
        "что думаешь про тик така",
        "тик ток платформа",
    )
    assert "Тик так" in plan.fts_query


def test_build_main_rag_plan_dedupes_same_semantic_text():
    plan = build_main_rag_plan(
        "крабер",
        TurnPlan(
            original="крабер",
            text="крабер",
            skip_search=False,
        ),
    )

    assert plan.semantic_queries == ("крабер",)
