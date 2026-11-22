import sqlite3
import unittest

from batch.revisions import BatchRevisionId
from issue.envelope import decode_v1, verify_v1_digest
from issue.reissue import IssueNotFound, reissue_station
from station.revisions import GraphRevisionId, UnknownGraphRevision
from tests import Exchange, counts, reject_commit_after_insert


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.exchange = Exchange(self)
        self.sending = self.exchange.register("independent")
        self.receiving = self.exchange.register("receiver")

    def test_normal_issue_and_reissue(self):
        exchange = self.exchange
        key = exchange.freeze("SHIFT-17", self.sending, self.receiving)
        self.assertEqual(exchange.batches.get(key).demand, 3)
        self.assertEqual(exchange.online(key), 2)
        sent, received = exchange.issue_pair(key)
        left, right = decode_v1(sent), decode_v1(received)
        self.assertTrue(verify_v1_digest(left))
        self.assertTrue(verify_v1_digest(right))
        self.assertNotEqual(left.issue_id, right.issue_id)
        for piece in (left, right):
            self.assertEqual((piece.body["batch_id"], piece.body["revision"]), (key.batch_id, key.revision))
            self.assertEqual(piece.body["freeze_id"], exchange.batches.get(key).freeze_id)
        self.assertEqual((left.body["site"], right.body["site"]), ("east", "west"))
        self.assertEqual(reissue_station(exchange.registry, left.issue_id), sent)
        self.assertEqual(reissue_station(exchange.registry, right.issue_id), received)

    def test_unknown_topology(self):
        exchange = self.exchange
        with self.assertRaises(UnknownGraphRevision):
            exchange.freeze("MISSING", GraphRevisionId("east", 99), self.receiving)
        with self.assertRaises(KeyError):
            exchange.issue(BatchRevisionId("MISSING", 1), "east")
        self.assertEqual(counts(exchange.source, "batch_snapshot", "archive_block", "issued_piece"), (0, 0, 0))

    def test_issue_commit_rejected(self):
        exchange = self.exchange
        key = exchange.freeze("COMMIT", self.sending, self.receiving)
        original = exchange.issue(key, "east")
        issue_id = decode_v1(original).issue_id
        reject_commit_after_insert(exchange.source, "issued_piece")
        with self.assertRaises(sqlite3.IntegrityError):
            exchange.issue(key, "west")
        exchange.offline()
        exchange.restore_source()
        self.assertEqual(counts(exchange.source, "issued_piece", "test_pending"), (1, 0))
        self.assertEqual(reissue_station(exchange.registry, issue_id), original)

    def test_reissue_preserves_original(self):
        exchange = self.exchange
        key = exchange.freeze("REISSUE", self.sending, self.receiving)
        original = exchange.issue(key, "east")
        issue_id = decode_v1(original).issue_id
        updated = exchange.register("shared")
        second = exchange.freeze("REISSUE", updated, self.receiving)
        self.assertEqual(exchange.online(second), 1)
        self.assertEqual(reissue_station(exchange.registry, issue_id), original)
        self.assertEqual(reissue_station(exchange.registry, issue_id), original)
        self.assertEqual(counts(exchange.source, "issued_piece"), (1,))

    def test_unknown_issue(self):
        with self.assertRaises(IssueNotFound):
            reissue_station(self.exchange.registry, "missing-issue")
        self.assertEqual(counts(self.exchange.source, "issued_piece"), (0,))
