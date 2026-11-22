import unittest

from batch.manifest import DuplicateBlockError
from batch.revisions import BatchRevisionId
from report.sign import sign_capacity
from tests import Exchange, counts


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.exchange = Exchange(self)
        self.sending = self.exchange.register("independent")
        self.receiving = self.exchange.register("receiver")

    def test_empty_manifest(self):
        exchange = self.exchange
        key = exchange.freeze("EMPTY", self.sending, self.receiving, [])
        self.assertEqual(exchange.batches.get(key).manifest.rows, ())
        self.assertEqual(exchange.online(key), 0)
        left, right = exchange.accept_pair(exchange.issue_pair(key))
        exchange.offline()
        report = sign_capacity(exchange.receipts, exchange.archive, left.receipt_id, right.receipt_id)
        self.assertEqual(report.blocks, 0)
        self.assertEqual([origin.receipt_id for origin in report.origins], [left.receipt_id, right.receipt_id])

    def test_duplicate_block(self):
        exchange = self.exchange
        good = [{"block_id": "a", "locator": "shelf-a"}]
        baseline = exchange.freeze("DUPLICATE", self.sending, self.receiving, good)
        with self.assertRaisesRegex(DuplicateBlockError, "lines 1 and 2"):
            exchange.freeze("DUPLICATE", self.sending, self.receiving,
                            good + [{"block_id": "a", "locator": "other-shelf"}])
        with self.assertRaises(KeyError):
            exchange.issue(BatchRevisionId("DUPLICATE", 2), "east")
        self.assertEqual(exchange.batches.get(baseline).manifest.rows[0].locator, "shelf-a")
        self.assertEqual(counts(exchange.source, "batch_snapshot", "archive_block", "issued_piece"), (1, 1, 0))

    def test_missing_block_identity(self):
        exchange = self.exchange
        for rows in ([{"locator": "no-block"}], [{"block_id": "  "}]):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "missing a block identity"):
                exchange.freeze("BAD", self.sending, self.receiving, rows)
        self.assertEqual(counts(exchange.source, "batch_snapshot", "archive_block"), (0, 0))

    def test_manifest_persists_input_order(self):
        exchange = self.exchange
        rows = [{"block_id": "b", "locator": "second shelf"}, {"block_id": "a"}]
        key = exchange.freeze("ORDER", self.sending, self.receiving, iter(rows))
        exchange.offline()
        exchange.restore_source()
        snapshot = exchange.batches.get(key)
        self.assertEqual(snapshot.demand, 2)
        self.assertEqual([(row.line_number, row.block_id, row.locator) for row in snapshot.manifest.rows],
                         [(1, "b", "second shelf"), (2, "a", "")])
