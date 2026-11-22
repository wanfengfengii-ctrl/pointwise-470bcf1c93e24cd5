import unittest

from issue.envelope import decode_v1, encode_v1
from report.capacity import CapacityEvidenceError
from report.sign import sign_capacity
from station.ports import PortBinding
from station.topology import DirectedLink, build_station_graph
from tests import Exchange, counts


class IncidentRegressionTests(unittest.TestCase):
    """Regression for the SHIFT-17 night-shift signing incident."""

    def setUp(self):
        self.exchange = Exchange(self)

    def sign(self, pair):
        left, right = pair
        return sign_capacity(self.exchange.receipts, self.exchange.archive, right.receipt_id, left.receipt_id)

    def test_shift_17_offline_matches_online(self):
        exchange = self.exchange
        cases = (
            ("shared", "receiver", 1),
            ("independent", "receiver", 2),
            ("relay_sender", "relay_receiver", 1),
            ("relay_sender", "relay_receiver_broken", 0),
        )
        rows = exchange.sample["archive_rows"][:2]
        pairs, online = [], []
        for sender_name, receiver_name, _ in cases:
            key = exchange.freeze(
                "SHIFT-17", exchange.register(sender_name), exchange.register(receiver_name), rows
            )
            online.append(exchange.online(key))
            pairs.append(exchange.accept_pair(exchange.issue_pair(key)))
        exchange.offline()
        reports = [self.sign(pair) for pair in pairs]
        expected = [case[2] for case in cases]
        self.assertEqual(online, expected)
        self.assertEqual([report.blocks for report in reports], expected)
        for report, pair in zip(reports, pairs, strict=True):
            self.assertEqual(
                [origin.receipt_id for origin in report.origins],
                [receipt.receipt_id for receipt in pair],
            )
        self.assertEqual(counts(exchange.reports, "signed_report", "report_origin", "report_ack"), (4, 8, 4))

    def test_empty_port_set_signs_zero(self):
        exchange = self.exchange
        east = build_station_graph(
            "east", "east-in", ["east-in", "east-spare"], [DirectedLink("east-in", "east-spare", 1)], []
        )
        west = build_station_graph("west", "west-out", ["west-out"], [], [])
        key = exchange.freeze(
            "NO-PORTS", exchange.stations.register(east), exchange.stations.register(west)
        )
        self.assertEqual(exchange.online(key), 0)
        pair = exchange.accept_pair(exchange.issue_pair(key))
        exchange.offline()
        report = self.sign(pair)
        self.assertEqual(report.blocks, 0)
        self.assertEqual(
            [origin.receipt_id for origin in report.origins],
            [receipt.receipt_id for receipt in pair],
        )

    def test_cut_limits_capped_at_demand(self):
        exchange = self.exchange
        rows = exchange.sample["archive_rows"][:2]
        east = build_station_graph(
            "east", "east-in", ["east-in", "east-p", "east-q"],
            [DirectedLink("east-in", "east-p", 9), DirectedLink("east-in", "east-q", 9)],
            [PortBinding("P", "east-p"), PortBinding("Q", "east-q")],
        )
        west = build_station_graph(
            "west", "west-out", ["west-out", "west-p", "west-q"],
            [DirectedLink("west-p", "west-out", 9), DirectedLink("west-q", "west-out", 9)],
            [PortBinding("P", "west-p"), PortBinding("Q", "west-q")],
        )
        key = exchange.freeze(
            "CAPPED", exchange.stations.register(east), exchange.stations.register(west), rows
        )
        self.assertEqual(exchange.online(key), 2)
        originals = exchange.issue_pair(key)
        for raw in originals:
            cuts = decode_v1(raw).body["capacity"]["cuts"]
            self.assertEqual(len(cuts), 4)
            for cut in cuts:
                self.assertTrue(0 <= cut["limit"] <= 2)
        pair = exchange.accept_pair(originals)
        exchange.offline()
        self.assertEqual(self.sign(pair).blocks, 2)

    def test_malformed_cut_evidence_is_not_signed(self):
        exchange = self.exchange
        key = exchange.freeze("EVIDENCE", exchange.register("shared"), exchange.register("receiver"))
        sender, receiver = exchange.issue_pair(key)
        normal = decode_v1(sender)
        good_cuts = normal.body["capacity"]["cuts"]
        variants = (
            {"scheme": "port-limit-v1", "limits": [1, 1]},
            {"scheme": "port-cut-v2", "cuts": good_cuts[:-1]},
            {"scheme": "port-cut-v2", "cuts": [good_cuts[0], good_cuts[0], *good_cuts[2:]]},
            {"scheme": "port-cut-v2", "cuts": [{**cut, "limit": 99} for cut in good_cuts]},
            {"scheme": "port-cut-v2", "cuts": [{**cut, "ports": ["UNKNOWN"]} for cut in good_cuts]},
        )
        exchange.offline()
        for index, capacity in enumerate(variants):
            with self.subTest(capacity=capacity):
                altered = encode_v1(f"altered-{index}", {**normal.body, "capacity": capacity})
                pair = exchange.accept_pair((altered, receiver))
                with self.assertRaises(CapacityEvidenceError):
                    self.sign(pair)
        self.assertEqual(counts(exchange.reports, "signed_report", "report_origin", "report_ack"), (0, 0, 0))
