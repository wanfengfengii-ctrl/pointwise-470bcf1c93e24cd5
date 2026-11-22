import unittest
from dataclasses import replace

from report.capacity import CapacityEvidenceError
from report.sign import sign_capacity
from station.flow import max_flow
from station.ports import PortBinding
from station.topology import DirectedLink, build_station_graph
from tests import Exchange, counts


class StationTests(unittest.TestCase):
    def setUp(self):
        self.exchange = Exchange(self)

    def test_parallel_links(self):
        exchange = self.exchange
        graph = exchange.graph("independent")
        first_link = graph.links[0]
        # P carries both parallel links. Q has no sending link in either revision.
        two = exchange.stations.register(replace(graph, links=(first_link, first_link)))
        one = exchange.stations.register(replace(graph, links=(first_link,)))
        west = exchange.graph("receiver")
        receiving = exchange.stations.register(replace(west, links=(DirectedLink("west-p", "west-output", 2),)))
        combined = exchange.freeze("PARALLEL", two, receiving)
        removed = exchange.freeze("PARALLEL", one, receiving)
        self.assertEqual((exchange.online(combined), exchange.online(removed)), (2, 1))
        self.assertEqual(len(exchange.stations.get(two).links), 2)

    def test_port_names(self):
        exchange = self.exchange
        east = exchange.graph("independent")
        west = exchange.graph("receiver")
        sending = exchange.stations.register(replace(east, links=(east.links[1],), ports=east.ports[::-1]))
        receiving = exchange.stations.register(replace(west, links=(west.links[1],)))
        key = exchange.freeze("NAMED", sending, receiving)
        self.assertEqual(exchange.online(key), 1)
        left, right = exchange.accept_pair(exchange.issue_pair(key))
        exchange.offline()
        self.assertEqual(sign_capacity(exchange.receipts, exchange.archive, left.receipt_id, right.receipt_id).blocks, 1)

    def test_port_mismatch(self):
        exchange = self.exchange
        west = exchange.graph("receiver")
        changed = exchange.stations.register(replace(west, ports=(PortBinding("R", "west-p"), west.ports[1])))
        key = exchange.freeze("PORTS", exchange.register("shared"), changed)
        with self.assertRaisesRegex(ValueError, "port names differ"):
            exchange.online(key)
        left, right = exchange.accept_pair(exchange.issue_pair(key))
        exchange.offline()
        with self.assertRaises(CapacityEvidenceError):
            sign_capacity(exchange.receipts, exchange.archive, left.receipt_id, right.receipt_id)
        self.assertEqual(counts(exchange.reports, "signed_report", "report_ack"), (0, 0))

    def test_aliased_ports_and_terminal(self):
        exchange = self.exchange
        east = build_station_graph("east", "s", ["s"], [], [PortBinding("P", "s"), PortBinding("Q", "s")])
        west = build_station_graph(
            "west", "t", ["p", "q", "t"], [DirectedLink("p", "t", 1), DirectedLink("q", "t", 1)],
            [PortBinding("P", "p"), PortBinding("Q", "q")],
        )
        key = exchange.freeze("ALIASES", exchange.stations.register(east), exchange.stations.register(west))
        self.assertEqual(exchange.online(key), 2)
        left, right = exchange.accept_pair(exchange.issue_pair(key))
        exchange.offline()
        self.assertEqual(sign_capacity(exchange.receipts, exchange.archive, left.receipt_id, right.receipt_id).blocks, 2)

    def test_invalid_registration_keeps_revisions(self):
        exchange = self.exchange
        good = exchange.graph("shared")
        first = exchange.stations.register(good)
        invalid = (
            replace(good, links=(DirectedLink("east-input", "unknown", 1),)),
            replace(good, links=(DirectedLink("east-input", "east-p", -1),)),
            replace(good, links=(DirectedLink("east-input", "east-p", True),)),
            replace(good, ports=(good.ports[0], good.ports[0])),
        )
        for graph in invalid:
            with self.subTest(graph=graph), self.assertRaises(ValueError):
                exchange.stations.register(graph)
        self.assertEqual(counts(exchange.source, "station_revision"), (1,))
        self.assertEqual(exchange.stations.get(first), good)

    def test_integer_flow_can_reroute_an_augmentation(self):
        arcs = [("s", "a", 1), ("s", "b", 1), ("a", "c", 1), ("a", "d", 1),
                ("b", "c", 1), ("c", "t", 1), ("d", "t", 1)]
        self.assertEqual(max_flow(arcs, "s", "t", 3), 2)
        self.assertEqual(max_flow(arcs, "s", "t", 1), 1)
        self.assertEqual(max_flow(arcs, "t", "s", 3), 0)
