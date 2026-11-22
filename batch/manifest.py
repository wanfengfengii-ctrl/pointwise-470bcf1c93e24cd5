from collections.abc import Iterable
from dataclasses import dataclass

from batch.import_rows import ArchiveRow


class DuplicateBlockError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Manifest:
    rows: tuple[ArchiveRow, ...]

    @property
    def demand(self) -> int:
        return len(self.rows)


def build_manifest(rows: Iterable[ArchiveRow]) -> Manifest:
    ordered = tuple(rows)
    seen_at = {}
    for position, row in enumerate(ordered, start=1):
        if not isinstance(row, ArchiveRow) or row.line_number != position:
            raise ValueError(f"invalid archive row at position {position}")
        if not isinstance(row.block_id, str) or not row.block_id.strip():
            raise ValueError(f"archive line {position} is missing a block identity")
        if not isinstance(row.locator, str):
            raise ValueError(f"archive line {position} has an invalid locator")
        if row.block_id in seen_at:
            previous = seen_at[row.block_id]
            raise DuplicateBlockError(f"block {row.block_id!r} occurs at lines {previous} and {position}")
        seen_at[row.block_id] = position
    return Manifest(ordered)
