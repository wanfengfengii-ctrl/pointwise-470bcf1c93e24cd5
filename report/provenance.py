from dataclasses import dataclass

from receive.receipts import Receipt


class SigningInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReceiptProvenance:
    receipt_id: int
    issue_id: str
    site: str
    batch_id: str
    revision: int
    freeze_id: str

    @classmethod
    def from_receipt(cls, receipt: Receipt) -> "ReceiptProvenance":
        piece = receipt.piece
        return cls(receipt.receipt_id, piece.issue_id, piece.site, piece.batch_id, piece.revision, piece.freeze_id)


@dataclass(frozen=True, slots=True)
class SigningInputs:
    sending: Receipt
    receiving: Receipt
    origins: tuple[ReceiptProvenance, ReceiptProvenance]

    @property
    def demand(self) -> int:
        return self.sending.piece.demand


def prepare_signing_inputs(first: Receipt, second: Receipt) -> SigningInputs:
    left, right = first.piece, second.piece
    if (left.batch_id, left.revision, left.freeze_id) != (right.batch_id, right.revision, right.freeze_id):
        raise SigningInputError("receipts belong to different frozen batch revisions")
    if (left.sender, left.receiver, left.demand) != (right.sender, right.receiver, right.demand):
        raise SigningInputError("receipts disagree on task roles or demand")
    if {left.site, right.site} != {left.sender, left.receiver}:
        raise SigningInputError("a signing requires a receipt from each task station")

    sending, receiving = (first, second) if left.site == left.sender else (second, first)
    origins = (ReceiptProvenance.from_receipt(sending), ReceiptProvenance.from_receipt(receiving))
    return SigningInputs(sending, receiving, origins)
