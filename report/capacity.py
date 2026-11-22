from dataclasses import dataclass

from receive.validation import CheckedPiece
from report.provenance import SigningInputs
from station.ports import port_subsets


class CapacityEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BoundaryCapacity:
    ports: tuple[str, ...]
    cuts: tuple[tuple[tuple[str, ...], int], ...]

    def cut_map(self) -> dict[tuple[str, ...], int]:
        return dict(self.cuts)


def decode_capacity_evidence(piece: CheckedPiece) -> BoundaryCapacity:
    evidence = piece.capacity
    if evidence.keys() != {"scheme", "cuts"} or evidence.get("scheme") != "port-cut-v2":
        raise CapacityEvidenceError("unsupported or missing capacity evidence")
    entries = evidence["cuts"]
    expected = set(port_subsets(piece.ports))
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise CapacityEvidenceError("incomplete port capacity evidence")
    cuts = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.keys() != {"ports", "limit"}:
            raise CapacityEvidenceError("invalid port capacity evidence entry")
        names = entry["ports"]
        if (
            not isinstance(names, list)
            or len(names) != len(set(names))
            or any(not isinstance(name, str) or name not in piece.ports for name in names)
        ):
            raise CapacityEvidenceError("invalid port capacity evidence ports")
        limit = entry["limit"]
        if type(limit) is not int or not 0 <= limit <= piece.demand:
            raise CapacityEvidenceError("invalid port capacity value")
        cuts.append((tuple(sorted(names)), limit))
    if set(dict(cuts)) != expected or len(set(subset for subset, _ in cuts)) != len(cuts):
        raise CapacityEvidenceError("incomplete port capacity evidence")
    return BoundaryCapacity(piece.ports, tuple(cuts))


def compute_joint_capacity(inputs: SigningInputs) -> int:
    sending = decode_capacity_evidence(inputs.sending.piece)
    receiving = decode_capacity_evidence(inputs.receiving.piece)
    if set(sending.ports) != set(receiving.ports):
        raise CapacityEvidenceError("capacity evidence names different ports")
    sender_cuts = sending.cut_map()
    receiver_cuts = receiving.cut_map()
    blocks = min(
        sender_cuts[subset] + receiver_cuts[subset]
        for subset in port_subsets(sending.ports)
    )
    return min(inputs.demand, blocks)
