import sqlite3
import unittest

from report.readback import ReportNotFound, read_report
from report.sign import sign_capacity
from tests import Exchange, counts, reject_commit_after_insert


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.exchange = Exchange(self)
        self.receiving = self.exchange.register("receiver")

    def prepare(self, batch, profile):
        exchange = self.exchange
        key = exchange.freeze(batch, exchange.register(profile), self.receiving)
        return exchange.accept_pair(exchange.issue_pair(key))

    def sign(self, pair):
        left, right = pair
        return sign_capacity(self.exchange.receipts, self.exchange.archive, left.receipt_id, right.receipt_id)

    def test_commit_rejected(self):
        exchange = self.exchange
        first = self.prepare("NIGHT", "shared")
        second = self.prepare("NIGHT", "independent")
        exchange.offline()
        previous = self.sign(first)
        self.assertEqual(previous.blocks, 1)
        tables = ("signed_report", "report_origin", "report_ack")
        self.assertEqual(counts(exchange.reports, *tables), (1, 2, 1))
        reject_commit_after_insert(exchange.reports, "report_ack")
        with self.assertRaises(sqlite3.IntegrityError):
            self.sign(second)
        exchange.reopen_night()
        self.assertEqual(counts(exchange.reports, *tables, "test_pending"), (1, 2, 1, 0))
        self.assertEqual(read_report(exchange.archive, previous.report_id), previous)
        with self.assertRaises(ReportNotFound):
            read_report(exchange.archive, previous.report_id + 1)

    def test_old_report_after_new_revision(self):
        exchange = self.exchange
        first = self.prepare("HISTORY", "shared")
        exchange.offline()
        old = self.sign(first)
        exchange.restore_source()
        second = self.prepare("HISTORY", "independent")
        exchange.offline()
        new = self.sign(second)
        self.assertEqual((old.blocks, new.blocks), (1, 2))
        self.assertNotEqual(old.report_id, new.report_id)
        self.assertNotEqual(old.freeze_id, new.freeze_id)
        self.assertNotEqual(old.acknowledgment, new.acknowledgment)
        exchange.reopen_night()
        for expected, pair in ((new, second), (old, first)):
            actual = read_report(exchange.archive, expected.report_id)
            self.assertEqual(actual, expected)
            self.assertEqual(
                [(item.receipt_id, item.issue_id, item.revision) for item in actual.origins],
                [(item.receipt_id, item.piece.issue_id, item.piece.revision) for item in pair],
            )

    def test_unknown_report(self):
        with self.assertRaises(ReportNotFound):
            read_report(self.exchange.archive, 5)
        self.assertEqual(counts(self.exchange.reports, "signed_report", "report_origin", "report_ack"), (0, 0, 0))
