import unittest

from issue.envelope import decode_v1
from issue.reissue import reissue_station
from receive.admit import accept_piece
from report.readback import read_report
from report.sign import sign_capacity
from tests import Exchange, counts


class WorkdayTests(unittest.TestCase):
    def test_reopen_initialization(self):
        exchange = Exchange(self)
        receiver = exchange.register("receiver")
        original_sender = exchange.register("shared")
        old_key = exchange.freeze("WORKDAY", original_sender, receiver)
        self.assertEqual(exchange.online(old_key), 1)
        originals = exchange.issue_pair(old_key)
        issue_id = decode_v1(originals[0]).issue_id
        old_pair = exchange.accept_pair(originals)
        exchange.offline()
        old_report = sign_capacity(exchange.receipts, exchange.archive, *(r.receipt_id for r in old_pair))
        self.assertEqual(old_report.blocks, 1)

        exchange.restore_source()
        amended_sender = exchange.register("independent")
        amended_rows = [{"block_id": "a", "locator": "amended shelf"}, {"block_id": "b"}]
        new_key = exchange.freeze("WORKDAY", amended_sender, receiver, amended_rows)
        for store in (exchange.stations, exchange.batches, exchange.registry, exchange.receipts, exchange.archive):
            store.initialize()
            store.initialize()
        self.assertEqual(counts(exchange.source, "station_revision", "batch_snapshot", "archive_block", "issued_piece"),
                         (3, 2, 5, 2))
        self.assertEqual(exchange.batches.get(old_key).sender, original_sender)
        self.assertEqual(exchange.batches.get(new_key).sender, amended_sender)
        self.assertEqual(exchange.batches.get(new_key).manifest.rows[0].locator, "amended shelf")
        self.assertEqual((exchange.online(old_key), exchange.online(new_key)), (1, 2))
        self.assertEqual(reissue_station(exchange.registry, issue_id), originals[0])
        reissued_old = exchange.accept_pair(exchange.issue_pair(old_key))
        self.assertNotEqual(reissued_old[0].receipt_id, old_pair[0].receipt_id)
        new_pair = exchange.accept_pair(exchange.issue_pair(new_key))
        exchange.offline()
        repeat = sign_capacity(exchange.receipts, exchange.archive, *(r.receipt_id for r in reissued_old))
        self.assertEqual(repeat.blocks, 1)
        new_report = sign_capacity(exchange.receipts, exchange.archive, *(r.receipt_id for r in new_pair))
        self.assertEqual(new_report.blocks, 2)
        exchange.reopen_night()
        self.assertEqual(accept_piece(exchange.receipts, originals[0]), old_pair[0])
        self.assertEqual(read_report(exchange.archive, old_report.report_id), old_report)
        self.assertEqual(read_report(exchange.archive, new_report.report_id), new_report)
        self.assertEqual(counts(exchange.intake, "received_piece"), (6,))
        self.assertEqual(counts(exchange.reports, "signed_report", "report_origin", "report_ack"), (3, 6, 3))
