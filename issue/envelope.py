import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class V1Envelope:
    issue_id: str
    body: dict[str, object]
    digest: str


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")


def _payload(issue_id: str, body: dict[str, object]) -> dict[str, object]:
    return {"version": 1, "issue_id": issue_id, "body": body}


def _digest(issue_id: str, body: dict[str, object]) -> str:
    return hashlib.sha256(_canonical(_payload(issue_id, body))).hexdigest()


def encode_v1(issue_id: str, body: dict[str, object]) -> bytes:
    if not isinstance(issue_id, str) or not issue_id.strip() or not isinstance(body, dict):
        raise ValueError("invalid V1 issue identity or body")
    return _canonical({**_payload(issue_id, body), "digest": _digest(issue_id, body)})


def decode_v1(raw: bytes) -> V1Envelope:
    if not isinstance(raw, bytes):
        raise ValueError("V1 piece must be bytes")
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.keys() != {"version", "issue_id", "body", "digest"}:
            raise ValueError("invalid V1 envelope fields")
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("unsupported envelope version")
        issue_id, body, digest = data["issue_id"], data["body"], data["digest"]
        if not isinstance(issue_id, str) or not issue_id.strip() or not isinstance(body, dict):
            raise ValueError("invalid V1 issue identity or body")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid V1 digest field")
        if raw != _canonical(data):
            raise ValueError("V1 piece must use canonical bytes")
        return V1Envelope(issue_id, body, digest)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid V1 envelope encoding") from exc


def verify_v1_digest(envelope: V1Envelope) -> bool:
    return envelope.digest == _digest(envelope.issue_id, envelope.body)
