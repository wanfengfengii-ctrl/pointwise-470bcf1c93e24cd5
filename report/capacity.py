from dataclasses import dataclass

from receive.validation import CheckedPiece
from report.provenance import SigningInputs


class CapacityEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BoundaryCapacity:
    ports: tuple[str, ...]
    limits: tuple[int, ...]


def decode_capacity_evidence(piece: CheckedPiece) -> BoundaryCapacity:
    evidence = piece.capacity
    if evidence.keys() != {"scheme", "limits"} or evidence.get("scheme") != "port-limit-v1":
        raise CapacityEvidenceError("unsupported or missing capacity evidence")
    limits = evidence["limits"]
    if not isinstance(limits, list) or len(limits) != len(piece.ports):
        raise CapacityEvidenceError("incomplete port capacity evidence")
    if any(type(value) is not int or not 0 <= value <= piece.demand for value in limits):
        raise CapacityEvidenceError("invalid port capacity value")
    return BoundaryCapacity(piece.ports, tuple(limits))


def compute_joint_capacity(inputs: SigningInputs) -> int:
    sending = decode_capacity_evidence(inputs.sending.piece)
    receiving = decode_capacity_evidence(inputs.receiving.piece)
    if set(sending.ports) != set(receiving.ports):
        raise CapacityEvidenceError("capacity evidence names different ports")
    receiver_limits = dict(zip(receiving.ports, receiving.limits, strict=True))
    blocks = sum(
        min(limit, receiver_limits[name])
        for name, limit in zip(sending.ports, sending.limits, strict=True)
    )
    return min(inputs.demand, blocks)
