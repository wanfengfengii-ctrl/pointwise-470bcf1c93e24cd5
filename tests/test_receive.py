import unittest

from issue.envelope import decode_v1, encode_v1, verify_v1_digest
from receive.admit import accept_piece
from receive.receipts import ReceiptConflict
from receive.validation import PieceValidationError
from tests import Exchange, counts


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.exchange = Exchange(self)
        sending = self.exchange.register("independent")
        receiving = self.exchange.register("receiver")
        key = self.exchange.freeze("INTAKE", sending, receiving)
        self.raw = self.exchange.issue(key, "east")
        self.exchange.offline()

    def test_retry_returns_original(self):
        exchange = self.exchange
        first = accept_piece(exchange.receipts, self.raw)
        exchange.reopen_night()
        second = accept_piece(exchange.receipts, self.raw)
        self.assertEqual(second, first)
        self.assertEqual(exchange.receipts.fetch(first.receipt_id), first)
        self.assertEqual(counts(exchange.intake, "received_piece"), (1,))
        self.assertTrue(first.first_ack)

    def test_damaged_envelope(self):
        exchange = self.exchange
        with self.assertRaises(PieceValidationError):
            accept_piece(exchange.receipts, self.raw[:-5])
        with self.assertRaises(PieceValidationError):
            accept_piece(exchange.receipts, self.raw + b" ")
        self.assertEqual(counts(exchange.intake, "received_piece"), (0,))
        self.assertTrue(accept_piece(exchange.receipts, self.raw).first_ack)

    def test_body_digest_mismatch(self):
        exchange = self.exchange
        altered = self.raw.replace(b'"batch_id":"INTAKE"', b'"batch_id":"INBOXA"')
        self.assertNotEqual(altered, self.raw)
        envelope = decode_v1(altered)
        self.assertEqual(envelope.body["batch_id"], "INBOXA")
        self.assertFalse(verify_v1_digest(envelope))
        with self.assertRaisesRegex(PieceValidationError, "digest mismatch"):
            accept_piece(exchange.receipts, altered)
        self.assertEqual(counts(exchange.intake, "received_piece"), (0,))

    def test_identity_conflict(self):
        exchange = self.exchange
        first = accept_piece(exchange.receipts, self.raw)
        original = decode_v1(self.raw)
        changed = encode_v1(original.issue_id, {**original.body, "batch_id": "OTHER"})
        self.assertTrue(verify_v1_digest(decode_v1(changed)))
        with self.assertRaises(ReceiptConflict):
            accept_piece(exchange.receipts, changed)
        self.assertEqual(accept_piece(exchange.receipts, self.raw), first)
        self.assertEqual(exchange.receipts.fetch(first.receipt_id).piece.raw, self.raw)
        self.assertEqual(counts(exchange.intake, "received_piece"), (1,))
