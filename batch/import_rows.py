from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArchiveRow:
    line_number: int
    block_id: str
    locator: str


def parse_archive_rows(rows: Iterable[Mapping[str, object]]) -> tuple[ArchiveRow, ...]:
    parsed = []
    for line_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"archive line {line_number} must be a mapping")
        identity = row.get("block_id")
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError(f"archive line {line_number} is missing a block identity")
        locator = row.get("locator", "")
        if not isinstance(locator, str):
            raise ValueError(f"archive line {line_number} has an invalid locator")
        parsed.append(ArchiveRow(line_number, identity, locator))
    return tuple(parsed)
