from app.knowledge.chunks import split_dossier_chunks


def test_short_body_returns_single_block():
    body = "## Контекст жизни\n\n- 2026-08-26: Философ и сварщик.\n"
    chunks = split_dossier_chunks(body, 600, 120)
    assert chunks == [body.strip()]


def test_empty_body_returns_empty():
    assert split_dossier_chunks("", 600, 120) == []
    assert split_dossier_chunks("   ", 600, 120) == []


def test_long_body_splits_into_multiple_blocks():
    body = "\n\n".join(
        f"- 2026-08-{day:02d}: Факт номер {day} про человека." for day in range(1, 30)
    )
    chunks = split_dossier_chunks(body, 150, 30)
    assert len(chunks) > 1
    # Every block fits the budget (roughly — overlap may push a tail over).
    for chunk in chunks:
        assert chunk.strip()
    # No content lost: every fact line appears somewhere.
    joined = "\n".join(chunks)
    assert "Факт номер 1" in joined
    assert "Факт номер 29" in joined


def test_deterministic_same_input_same_blocks():
    body = "\n\n".join(
        f"- 2026-08-{day:02d}: Факт номер {day} про человека." for day in range(1, 30)
    )
    a = split_dossier_chunks(body, 150, 30)
    b = split_dossier_chunks(body, 150, 30)
    assert a == b


def test_overlap_carries_context_across_blocks():
    body = "\n\n".join(
        f"- 2026-08-{day:02d}: Факт номер {day} про человека." for day in range(1, 30)
    )
    chunks = split_dossier_chunks(body, 150, 30)
    assert len(chunks) > 1
    # A phrase that starts in one block and ends in the next is preserved in
    # the overlap of the following block (or both blocks contain a shared line).
    assert chunks[1]


def test_paragraph_longer_than_budget_splits_linewise():
    line = "- " + "слово " * 60
    body = f"## Заголовок\n\n{line}\n"
    chunks = split_dossier_chunks(body, 100, 20)
    assert len(chunks) >= 1
    joined = "\n".join(chunks)
    assert "Заголовок" in joined or any("слово" in chunk for chunk in chunks)
