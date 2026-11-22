from dataclasses import dataclass

from issue.envelope import decode_v1, verify_v1_digest


class PieceValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CheckedPiece:
    raw: bytes
    issue_id: str
    batch_id: str
    revision: int
    freeze_id: str
    site: str
    sender: str
    receiver: str
    demand: int
    ports: tuple[str, ...]
    capacity: dict[str, object]


def _required_name(body: dict[str, object], field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PieceValidationError(f"invalid station piece field {field!r}")
    return value


def validate_piece(raw: bytes) -> CheckedPiece:
    try:
        envelope = decode_v1(raw)
    except ValueError as exc:
        raise PieceValidationError(str(exc)) from exc
    if not verify_v1_digest(envelope):
        raise PieceValidationError("V1 digest mismatch")

    body = envelope.body
    batch_id = _required_name(body, "batch_id")
    freeze_id = _required_name(body, "freeze_id")
    site = _required_name(body, "site")
    sender = _required_name(body, "sender")
    receiver = _required_name(body, "receiver")
    if sender == receiver or site not in (sender, receiver):
        raise PieceValidationError("invalid station roles")

    revision = body.get("revision")
    demand = body.get("demand")
    if type(revision) is not int or not 0 < revision < 1 << 63:
        raise PieceValidationError("invalid frozen revision")
    if type(demand) is not int or demand < 0:
        raise PieceValidationError("invalid block demand")
    ports = body.get("ports")
    if not isinstance(ports, list) or any(not isinstance(port, str) or not port.strip() for port in ports):
        raise PieceValidationError("invalid port names")
    if len(set(ports)) != len(ports):
        raise PieceValidationError("repeated port name")
    capacity = body.get("capacity")
    if not isinstance(capacity, dict):
        raise PieceValidationError("missing capacity evidence object")
    return CheckedPiece(
        raw, envelope.issue_id, batch_id, revision, freeze_id, site, sender, receiver,
        demand, tuple(ports), capacity,
    )
