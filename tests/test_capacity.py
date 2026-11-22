import json
import unittest

from issue.envelope import decode_v1, encode_v1
from receive.admit import accept_piece
from receive.lookup import ReceiptNotFound
from report.capacity import CapacityEvidenceError
from report.provenance import SigningInputError
from report.sign import sign_capacity
from station.ports import PortBinding
from station.topology import DirectedLink, build_station_graph
from tests import Exchange, counts


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.exchange = Exchange(self)

    def assert_origins(self, report, pair):
        actual = [(origin.receipt_id, origin.issue_id, origin.site, origin.batch_id,
                   origin.revision, origin.freeze_id) for origin in report.origins]
        expected = [(receipt.receipt_id, receipt.piece.issue_id, receipt.piece.site,
                     receipt.piece.batch_id, receipt.piece.revision, receipt.piece.freeze_id)
                    for receipt in pair]
        self.assertEqual(actual, expected)
        self.assertTrue(report.acknowledgment)

    def sign(self, pair):
        left, right = pair
        return sign_capacity(self.exchange.receipts, self.exchange.archive, right.receipt_id, left.receipt_id)

    def test_shared_and_independent(self):
        exchange = self.exchange
        receiving = exchange.register("receiver")
        profiles = ("shared", "independent")
        pairs = []
        online = []
        for profile in profiles:
            key = exchange.freeze("COMPARE", exchange.register(profile), receiving, exchange.sample["archive_rows"][:2])
            online.append(exchange.online(key))
            pairs.append(exchange.accept_pair(exchange.issue_pair(key)))
        self.assertEqual(online, [1, 2])
        exchange.offline()
        reports = [self.sign(pair) for pair in pairs]
        blocks = [report.blocks for report in reports]
        if blocks[0] > 1:
            self.fail(f"CAPACITY_OVERREPORTED expected=1 actual={blocks[0]}")
        self.assertEqual(blocks, [1, 2])
        for report, pair in zip(reports, pairs, strict=True):
            self.assert_origins(report, pair)
        print("POINTWISE_SCENARIO " + json.dumps({
            "case_id": "v5",
            "input": {"demand": 2, "senders": [exchange.sample["graphs"][name] for name in profiles],
                      "receiver": exchange.sample["graphs"]["receiver"]},
            "expected": [1, 2], "actual": online,
            "downstream_expected": {"blocks": [1, 2], "receipts": [[r.receipt_id for r in pair] for pair in pairs]},
            "downstream_actual": {"blocks": blocks, "receipts": [[o.receipt_id for o in r.origins] for r in reports]},
            "code_paths": ["station/online_check.py", "issue/evidence.py", "receive/receipts.py",
                           "report/capacity.py", "report/archive.py"],
            "oracle": "The shared sending edge has capacity one. The independent graph has two edge-disjoint unit paths."
        }, sort_keys=True))

    def test_return_through_another_port(self):
        exchange = self.exchange
        sending = exchange.register("relay_sender")
        profiles = ("relay_receiver", "relay_receiver_broken")
        pairs = []
        online = []
        for profile in profiles:
            key = exchange.freeze("RELAY", sending, exchange.register(profile))
            online.append(exchange.online(key))
            pairs.append(exchange.accept_pair(exchange.issue_pair(key)))
        self.assertEqual(online, [1, 0])
        exchange.offline()
        reports = [self.sign(pair) for pair in pairs]
        blocks = [report.blocks for report in reports]
        self.assertEqual(blocks, [1, 0])
        for report, pair in zip(reports, pairs, strict=True):
            self.assert_origins(report, pair)
        print("POINTWISE_SCENARIO " + json.dumps({
            "case_id": "v6",
            "input": {"sender": exchange.sample["graphs"]["relay_sender"],
                      "receivers": [exchange.sample["graphs"][name] for name in profiles]},
            "expected": [1, 0], "actual": online,
            "downstream_expected": [1, 0], "downstream_actual": blocks,
            "code_paths": ["station/online_check.py", "issue/evidence.py", "report/capacity.py", "report/sign.py"],
            "oracle": "The only path crosses P, returns through Q, then crosses R. Removing the return breaks it."
        }, sort_keys=True))

    def test_evidence_distinguishes(self):
        exchange = self.exchange
        receiver = exchange.register("receiver")
        shared = exchange.freeze("EVIDENCE", exchange.register("shared"), receiver)
        independent = exchange.freeze("EVIDENCE", exchange.register("independent"), receiver)
        first = exchange.issue(shared, "east")
        second = exchange.issue(independent, "east")
        self.assertNotEqual(decode_v1(first).body["capacity"], decode_v1(second).body["capacity"])
        for forbidden in (b"east-private-bottleneck", b"east-input", b"east-p", b"east-q",
                          b"run17-block-a", b"ledger/17#a"):
            self.assertNotIn(forbidden, first)
            self.assertNotIn(forbidden, second)

    def test_joint_consumer(self):
        exchange = self.exchange
        ports = [PortBinding(name, name) for name in "PQR"]
        left_nodes = ["s", "x", "P", "Q", "R"]
        right_nodes = ["P", "Q", "R", "t"]
        receiver = exchange.stations.register(build_station_graph(
            "west", "t", right_nodes, [DirectedLink("P", "t", 1), DirectedLink("Q", "t", 1)], ports,
        ))
        variants = [
            [("s", "x", 1), ("x", "P", 1), ("x", "Q", 1), ("s", "R", 1)],
            [("s", "x", 1), ("x", "P", 1), ("x", "R", 1), ("s", "Q", 1)],
        ]
        actual_online = []
        pairs = []
        for arcs in variants:
            sending = exchange.stations.register(build_station_graph(
                "east", "s", left_nodes, [DirectedLink(*arc) for arc in arcs], ports,
            ))
            key = exchange.freeze("SUBSET", sending, receiver)
            actual_online.append(exchange.online(key))
            pairs.append(exchange.accept_pair(exchange.issue_pair(key)))
        exchange.offline()
        self.assertEqual(actual_online, [1, 2])
        reports = [self.sign(pair) for pair in pairs]
        self.assertEqual([report.blocks for report in reports], [1, 2])
        for report, pair in zip(reports, pairs, strict=True):
            self.assert_origins(report, pair)

    def test_missing_capacity_evidence_is_not_signed(self):
        exchange = self.exchange
        key = exchange.freeze("MALFORMED", exchange.register("shared"), exchange.register("receiver"))
        sender, receiver = exchange.issue_pair(key)
        normal = decode_v1(sender)
        incomplete = encode_v1(normal.issue_id, {**normal.body, "capacity": {}})
        exchange.offline()
        pair = exchange.accept_pair((incomplete, receiver))
        with self.assertRaises(CapacityEvidenceError):
            self.sign(pair)
        self.assertEqual(counts(exchange.reports, "signed_report", "report_origin", "report_ack"), (0, 0, 0))

    def test_mixed_batch(self):
        exchange = self.exchange
        sending, receiving = exchange.register("shared"), exchange.register("receiver")
        first = exchange.freeze("FIRST", sending, receiving)
        second = exchange.freeze("SECOND", sending, receiving)
        pair = exchange.accept_pair((exchange.issue(first, "east"), exchange.issue(second, "west")))
        exchange.offline()
        with self.assertRaises(SigningInputError):
            self.sign(pair)
        self.assertEqual(counts(exchange.reports, "signed_report", "report_origin", "report_ack"), (0, 0, 0))

    def test_mixed_revisions(self):
        exchange = self.exchange
        receiving = exchange.register("receiver")
        first = exchange.freeze("SAME", exchange.register("shared"), receiving)
        second = exchange.freeze("SAME", exchange.register("independent"), receiving)
        old = exchange.accept_pair(exchange.issue_pair(first))
        new = exchange.accept_pair(exchange.issue_pair(second))
        exchange.offline()
        with self.assertRaises(SigningInputError):
            self.sign((old[0], new[1]))
        self.assertEqual(counts(exchange.reports, "signed_report", "report_origin", "report_ack"), (0, 0, 0))
        report = self.sign(new)
        self.assertEqual(report.blocks, 2)
        self.assert_origins(report, new)

    def test_missing_or_same_site(self):
        exchange = self.exchange
        key = exchange.freeze("PAIR", exchange.register("shared"), exchange.register("receiver"))
        first = accept_piece(exchange.receipts, exchange.issue(key, "east"))
        second = accept_piece(exchange.receipts, exchange.issue(key, "east"))
        exchange.offline()
        with self.assertRaises(ReceiptNotFound):
            sign_capacity(exchange.receipts, exchange.archive, first.receipt_id, second.receipt_id + 1)
        with self.assertRaises(SigningInputError):
            self.sign((first, second))
        self.assertEqual(counts(exchange.reports, "signed_report", "report_origin", "report_ack"), (0, 0, 0))

    def test_distinct_freeze_id_with_same_batch_number_is_rejected(self):
        exchange = self.exchange
        key = exchange.freeze("KEY", exchange.register("shared"), exchange.register("receiver"))
        left, right = exchange.issue_pair(key)
        original = decode_v1(right)
        different = encode_v1(original.issue_id, {**original.body, "freeze_id": "different-freeze"})
        exchange.offline()
        pair = exchange.accept_pair((left, different))
        with self.assertRaises(SigningInputError):
            self.sign(pair)
        self.assertEqual(counts(exchange.reports, "signed_report", "report_origin", "report_ack"), (0, 0, 0))
