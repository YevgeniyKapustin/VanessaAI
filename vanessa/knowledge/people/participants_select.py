"""Selection and People-card line helpers for ParticipantsDigest."""

from __future__ import annotations

from vanessa.knowledge.people.participants_format import format_person_line


def fill_to_floor(selected: list[str], files: list[str], floor: int) -> None:
    for file in files:
        if len(selected) >= floor:
            return
        if file not in selected:
            selected.append(file)


def cap_people(selected: list[str], max_people: int) -> list[str]:
    if max_people and len(selected) > max_people:
        return selected[:max_people]
    return selected


def remember_person_file(seen_files: dict[str, str], alias: object, entry: object) -> None:
    if not isinstance(entry, dict):
        return
    file = entry.get("file")
    if not file or file in seen_files:
        return
    seen_files[file] = str(entry.get("id") or alias)


def unique_people_files(aliases: dict) -> dict[str, str]:
    seen_files: dict[str, str] = {}
    for alias, entry in aliases.items():
        remember_person_file(seen_files, alias, entry)
    return seen_files


def person_line_from_note(note, max_facts: int) -> str:
    if note is None:
        return ""
    return format_person_line(note, max_facts)
