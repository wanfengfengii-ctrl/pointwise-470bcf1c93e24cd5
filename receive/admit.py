from receive.receipts import Receipt, ReceiptStore
from receive.validation import validate_piece


def accept_piece(receipts: ReceiptStore, raw: bytes) -> Receipt:
    checked = validate_piece(raw)
    return receipts.accept_checked_piece(checked)
