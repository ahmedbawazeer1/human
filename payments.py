"""MOCKED payment provider and order ledger.

No real or sandbox payment service is contacted. The mock behaves like a
provider (checkout -> signed webhook -> payout) so the sale-to-cash logic
(delivery, idempotency, refunds, reconciliation) can be tested end to end.
The system never holds or moves money: in real use the founder's own payment
account would do that, and refunds are always approved by the founder.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from pathlib import Path

from decision_log import now_iso

MOCK = "MOCKED"
# ASSUMPTION: a typical card fee schedule used only to exercise reconciliation.
MOCK_FEE_PERCENT = 0.029
MOCK_FEE_FIXED = 0.30

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, product TEXT, amount REAL, currency TEXT,
    buyer_ref TEXT, status TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, order_id TEXT UNIQUE, amount REAL, fee REAL, created TEXT);
CREATE TABLE IF NOT EXISTS refunds (id TEXT PRIMARY KEY, order_id TEXT UNIQUE, amount REAL, approved_by TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS payouts (id TEXT PRIMARY KEY, amount REAL, created TEXT);
CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, type TEXT, received TEXT);
CREATE TABLE IF NOT EXISTS grants (order_id TEXT PRIMARY KEY, token TEXT UNIQUE, active INTEGER, created TEXT, revoked TEXT);
CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, order_id TEXT, created TEXT);
"""


class Ledger:
    def __init__(self, path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def q(self, sql, *args):
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def x(self, sql, *args):
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur


class MockPaymentProvider:
    """Stands in for a payment provider. Label: MOCKED."""

    def __init__(self, ledger: Ledger, secret: str | None = None):
        self.ledger = ledger
        self.secret = (secret or secrets.token_hex(16)).encode()

    def fee_for(self, amount: float) -> float:
        return round(amount * MOCK_FEE_PERCENT + MOCK_FEE_FIXED, 2)

    def sign(self, body: str) -> str:
        return hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()

    def verify(self, body: str, signature: str) -> bool:
        return hmac.compare_digest(self.sign(body), signature or "")

    def create_checkout(self, product: str, amount: float, buyer_ref: str, currency: str = "USD") -> str:
        order_id = "ord_" + uuid.uuid4().hex[:10]
        self.ledger.x("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", order_id, product, amount, currency,
                      buyer_ref, "pending", now_iso())
        return order_id

    def _event(self, etype: str, data: dict) -> tuple[str, str]:
        body = json.dumps({"id": "evt_" + uuid.uuid4().hex[:12], "type": etype, "created": now_iso(),
                           "livemode": False, "mock": True, "data": data})
        return body, self.sign(body)

    def complete_test_payment(self, order_id: str) -> tuple[str, str]:
        """The buyer 'pays' in the mock. Returns the signed webhook the provider would send."""
        o = self.ledger.q("SELECT * FROM orders WHERE id=?", order_id)[0]
        return self._event("payment.succeeded", {"order_id": order_id, "amount": o["amount"],
                                                 "fee": self.fee_for(o["amount"])})

    def refund(self, order_id: str, approval) -> tuple[str, str]:
        """Founder-approved refund executed by the (mock) provider, never by this system."""
        from approval import require_approved
        require_approved(approval, {"refund_order": order_id})
        o = self.ledger.q("SELECT * FROM orders WHERE id=?", order_id)[0]
        return self._event("refund.succeeded", {"order_id": order_id, "amount": o["amount"]})

    def payout(self) -> tuple[str, str]:
        paid = self.ledger.q("SELECT COALESCE(SUM(amount - fee),0) AS net FROM payments")[0]["net"]
        refunded = self.ledger.q("SELECT COALESCE(SUM(amount),0) AS r FROM refunds")[0]["r"]
        already = self.ledger.q("SELECT COALESCE(SUM(amount),0) AS p FROM payouts")[0]["p"]
        return self._event("payout.paid", {"amount": round(paid - refunded - already, 2)})
