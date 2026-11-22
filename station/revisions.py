import json
import sqlite3
from dataclasses import dataclass

from station.ports import PortBinding
from station.topology import DirectedLink, StationGraph, build_station_graph


class UnknownGraphRevision(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GraphRevisionId:
    site: str
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.site, str) or not self.site.strip():
            raise ValueError("site must be a nonempty string")
        if type(self.revision) is not int or not 0 < self.revision < 1 << 63:
            raise ValueError("invalid station revision number")


class StationRevisionStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS station_revision (
                site TEXT NOT NULL,
                revision INTEGER NOT NULL,
                terminal TEXT NOT NULL,
                nodes TEXT NOT NULL,
                directed_links TEXT NOT NULL,
                ports TEXT NOT NULL,
                PRIMARY KEY (site, revision)
            )
        """)

    def register(self, graph: StationGraph) -> GraphRevisionId:
        graph = build_station_graph(graph.site, graph.terminal, graph.nodes, graph.links, graph.ports)
        # Hexadecimal preserves arbitrary Python integer capacities in the stored graph.
        links = [(link.start, link.end, format(link.capacity, "x")) for link in graph.links]
        ports = [(port.name, port.node) for port in graph.ports]
        self.connection.execute("BEGIN IMMEDIATE")
        with self.connection:
            previous, = self.connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM station_revision WHERE site = ?",
                (graph.site,),
            ).fetchone()
            key = GraphRevisionId(graph.site, previous + 1)
            self.connection.execute(
                """INSERT INTO station_revision (site, revision, terminal, nodes, directed_links, ports)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (key.site, key.revision, graph.terminal, json.dumps(graph.nodes),
                 json.dumps(links), json.dumps(ports)),
            )
        return key

    def get(self, key: GraphRevisionId) -> StationGraph:
        stored = self.connection.execute(
            """SELECT terminal, nodes, directed_links, ports FROM station_revision
               WHERE site = ? AND revision = ?""",
            (key.site, key.revision),
        ).fetchone()
        if stored is None:
            raise UnknownGraphRevision(f"unknown station revision {key!r}")
        terminal, nodes, links, ports = stored
        return build_station_graph(
            key.site,
            terminal,
            json.loads(nodes),
            (DirectedLink(start, end, int(capacity, 16)) for start, end, capacity in json.loads(links)),
            (PortBinding(name, node) for name, node in json.loads(ports)),
        )
