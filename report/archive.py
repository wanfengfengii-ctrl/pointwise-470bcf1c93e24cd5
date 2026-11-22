import sqlite3
from dataclasses import dataclass

from report.provenance import ReceiptProvenance, SigningInputs


@dataclass(frozen=True, slots=True)
class StoredReport:
    report_id: int
    batch_id: str
    revision: int
    freeze_id: str
    blocks: int
    origins: tuple[ReceiptProvenance, ReceiptProvenance]
    acknowledgment: str


class ReportArchive:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS signed_report (
                report_id INTEGER PRIMARY KEY,
                batch_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                freeze_id TEXT NOT NULL,
                blocks INTEGER NOT NULL CHECK (blocks >= 0)
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS report_origin (
                report_id INTEGER NOT NULL REFERENCES signed_report (report_id),
                position INTEGER NOT NULL CHECK (position IN (0, 1)),
                receipt_id INTEGER NOT NULL,
                issue_id TEXT NOT NULL,
                site TEXT NOT NULL,
                PRIMARY KEY (report_id, position)
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS report_ack (
                report_id INTEGER PRIMARY KEY REFERENCES signed_report (report_id),
                acknowledgment TEXT NOT NULL UNIQUE
            )
        """)

    def publish(self, inputs: SigningInputs, blocks: int) -> StoredReport:
        if type(blocks) is not int or not 0 <= blocks <= inputs.demand:
            raise ValueError("capacity falls outside the signing demand")
        batch = inputs.sending.piece
        self.connection.execute("BEGIN IMMEDIATE")
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO signed_report (batch_id, revision, freeze_id, blocks) VALUES (?, ?, ?, ?)",
                (batch.batch_id, batch.revision, batch.freeze_id, blocks),
            )
            report_id = cursor.lastrowid
            self.connection.executemany(
                "INSERT INTO report_origin (report_id, position, receipt_id, issue_id, site) VALUES (?, ?, ?, ?, ?)",
                ((report_id, index, origin.receipt_id, origin.issue_id, origin.site)
                 for index, origin in enumerate(inputs.origins)),
            )
            acknowledgment = f"signed-{report_id}"
            self.connection.execute(
                "INSERT INTO report_ack (report_id, acknowledgment) VALUES (?, ?)",
                (report_id, acknowledgment),
            )
        return StoredReport(
            report_id, batch.batch_id, batch.revision, batch.freeze_id,
            blocks, inputs.origins, acknowledgment,
        )

    def get(self, report_id: int) -> StoredReport | None:
        if type(report_id) is not int or not 0 < report_id < 1 << 63:
            return None
        head = self.connection.execute(
            "SELECT batch_id, revision, freeze_id, blocks FROM signed_report WHERE report_id = ?",
            (report_id,),
        ).fetchone()
        if head is None:
            return None
        batch_id, revision, freeze_id, blocks = head
        origins = self.connection.execute(
            "SELECT receipt_id, issue_id, site FROM report_origin WHERE report_id = ? ORDER BY position",
            (report_id,),
        ).fetchall()
        ack = self.connection.execute(
            "SELECT acknowledgment FROM report_ack WHERE report_id = ?", (report_id,)
        ).fetchone()
        if len(origins) != 2 or ack is None:
            raise sqlite3.DatabaseError(f"incomplete persisted report {report_id}")
        first, second = (ReceiptProvenance(*row, batch_id, revision, freeze_id) for row in origins)
        return StoredReport(report_id, batch_id, revision, freeze_id, blocks, (first, second), ack[0])
