from datetime import date

from vanessa.knowledge.memory.compaction_body import (
    age_days,
    bucket_key,
    compact_heading_lines,
    compact_quotes,
    compact_section,
    join_sections,
    parse_line_date,
    split_sections,
)

TODAY = date(2026, 9, 8)


def test_parse_line_date_valid_and_invalid() -> None:
    assert parse_line_date("- 2026-09-01: fact") == date(2026, 9, 1)
    assert parse_line_date("not dated") is None
    assert parse_line_date("- 2026-13-40: bad") is None


def test_age_and_bucket_keys() -> None:
    assert age_days(date(2026, 9, 10), TODAY) == 0
    assert bucket_key(0) == "today"
    assert bucket_key(3) == "week"
    assert bucket_key(20) == "month"
    assert bucket_key(60) == "months_3"
    assert bucket_key(120) == "months_6"
    assert bucket_key(200) == "year"
    assert bucket_key(400) == "older"


def test_split_and_join_sections_roundtrip() -> None:
    body = "preamble\n\n## Контекст жизни\n- 2026-09-01: a\n\n## Цитатник\n> hi\n"
    sections = split_sections(body)
    rebuilt = join_sections(sections)
    assert "## Контекст жизни" in rebuilt
    assert "## Цитатник" in rebuilt


def test_compact_section_keeps_undated_and_trims() -> None:
    lines = ["note without date"]
    lines.extend(f"- 2024-01-{day:02d}: old {day}" for day in range(1, 16))
    kept, overflow = compact_section(lines, TODAY, limit=2)
    min_overflow = 10
    assert "note without date" in kept
    assert overflow
    assert len(overflow) >= min_overflow


def test_compact_section_no_dated_keeps_all() -> None:
    lines = ["plain", "", "still plain"]
    kept, overflow = compact_section(lines, TODAY)
    assert kept == lines
    assert overflow == []


def test_compact_quotes_dedupes_and_caps() -> None:
    quote_limit = 5
    lines = ["> same", "> same", *[f"> q{index}" for index in range(25)]]
    kept, overflow = compact_quotes(lines, limit=quote_limit)
    assert len(kept) == quote_limit
    assert overflow
    short, empty = compact_quotes(["> a", "> b"], limit=20)
    assert empty == []
    assert "> a" in short


def test_compact_heading_routes() -> None:
    quotes, _overflow = compact_heading_lines(
        "## Цитатник",
        ["> a"] * 3,
        TODAY,
        10,
        2,
    )
    assert quotes is not None
    life, overflow = compact_heading_lines(
        "## Контекст жизни",
        [f"- 2024-01-{day:02d}: x" for day in range(1, 12)],
        TODAY,
        2,
        20,
    )
    assert life is not None
    assert overflow
    skip, none = compact_heading_lines("## Хроника", ["x"], TODAY, 10, 10)
    assert skip is None
    assert none is None
