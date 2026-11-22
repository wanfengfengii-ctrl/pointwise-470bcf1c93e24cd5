import sqlite3
from dataclasses import dataclass

from receive.validation import CheckedPiece, validate_piece


class ReceiptConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Receipt:
    receipt_id: int
    first_ack: str
    piece: CheckedPiece


class ReceiptStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS received_piece (
                receipt_id INTEGER PRIMARY KEY,
                issue_id TEXT NOT NULL UNIQUE,
                original BLOB NOT NULL,
                first_ack TEXT NOT NULL UNIQUE
            )
        """)

    def accept_checked_piece(self, checked: CheckedPiece) -> Receipt:
        self.connection.execute("BEGIN IMMEDIATE")
        with self.connection:
            existing = self.connection.execute(
                "SELECT receipt_id, original, first_ack FROM received_piece WHERE issue_id = ?",
                (checked.issue_id,),
            ).fetchone()
            if existing is not None:
                receipt_id, original, first_ack = existing
                if original != checked.raw:
                    raise ReceiptConflict(f"issue {checked.issue_id!r} already has different bytes")
            else:
                previous, = self.connection.execute(
                    "SELECT COALESCE(MAX(receipt_id), 0) FROM received_piece"
                ).fetchone()
                receipt_id = previous + 1
                first_ack = f"received-{receipt_id}"
                self.connection.execute(
                    "INSERT INTO received_piece (receipt_id, issue_id, original, first_ack) VALUES (?, ?, ?, ?)",
                    (receipt_id, checked.issue_id, checked.raw, first_ack),
                )
        return Receipt(receipt_id, first_ack, checked)

    def fetch(self, receipt_id: int) -> Receipt | None:
        if type(receipt_id) is not int or not 0 < receipt_id < 1 << 63:
            return None
        row = self.connection.execute(
            "SELECT original, first_ack FROM received_piece WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        if row is None:
            return None
        original, first_ack = row
        return Receipt(receipt_id, first_ack, validate_piece(original))
