from app.rag.search.merger import merge_vector_search_hits


def test_merge_vector_search_hits_keeps_best_score():
    hits = merge_vector_search_hits(
        [
            [{"message_id": 1, "score": 0.4}, {"message_id": 2, "score": 0.3}],
            [{"message_id": 1, "score": 0.8}, {"message_id": 3, "score": 0.2}],
        ]
    )

    assert [int(hit["message_id"]) for hit in hits] == [1, 2, 3]
    assert float(hits[0]["score"]) == 0.8
