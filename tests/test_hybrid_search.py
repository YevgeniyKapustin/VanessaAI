from tests.conftest import make_message

from app.rag.merger import merge_hybrid_results


def test_merge_hybrid_results_deduplicates():
    vector_hits = [
        {"message_id": 1, "score": 0.9},
        {"message_id": 2, "score": 0.8},
        {"message_id": 3, "score": 0.7},
    ]
    fts_hits = [
        make_message(2),
        make_message(4),
    ]

    result = merge_hybrid_results(
        vector_hits,
        fts_hits,
        context_min=2,
        context_max=10,
    )

    assert 2 in result
    assert 4 in result


def test_merge_hybrid_results_respects_max():
    vector_hits = [{"message_id": i, "score": 1.0 / i} for i in range(1, 60)]
    fts_hits = []

    result = merge_hybrid_results(
        vector_hits,
        fts_hits,
        context_min=20,
        context_max=50,
    )

    assert len(result) == 50
