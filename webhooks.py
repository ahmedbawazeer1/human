"""Webhook handler: verifies the signature, ignores duplicate events
(idempotency), and turns payment events into delivery or access revocation."""
from __future__ import annotations

import json
import sqlite3

import delivery
import refunds
from decision_log import now_iso


def handle(provider, ledger, body: str, signature: str, mailer=None) -> str:
    if not provider.verify(body, signature):
        return "rejected:bad_signature"
    evt = json.loads(body)
    try:
        ledger.x("INSERT INTO events VALUES (?,?,?)", evt["id"], evt["type"], now_iso())
    except sqlite3.IntegrityError:
        return "ignored:duplicate_event"
    d = evt["data"]
    if evt["type"] == "payment.succeeded":
        try:
            ledger.x("INSERT INTO payments VALUES (?,?,?,?,?)", "pay_" + evt["id"][4:], d["order_id"], d["amount"], d["fee"], now_iso())
        except sqlite3.IntegrityError:
            return "ignored:order_already_paid"
        ledger.x("UPDATE orders SET status='paid' WHERE id=?", d["order_id"])
        return delivery.deliver(ledger, d["order_id"], mailer=mailer)
    if evt["type"] == "refund.succeeded":
        return refunds.record_refund(ledger, d["order_id"], d["amount"])
    if evt["type"] == "payout.paid":
        ledger.x("INSERT INTO payouts VALUES (?,?,?)", "po_" + evt["id"][4:], d["amount"], now_iso())
        return "recorded:payout"
    return "ignored:unknown_type"
