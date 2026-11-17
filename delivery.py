"""Automatic delivery after payment (MOCKED email).

A paid order gets exactly one access grant (order id is the primary key), so
a repeated webhook can never deliver twice. Delivery emails are written to
the local outbox, not sent.
"""
from __future__ import annotations

import secrets
import sqlite3

from decision_log import now_iso


def deliver(ledger, order_id: str, mailer=None) -> str:
    order = ledger.q("SELECT * FROM orders WHERE id=?", order_id)
    if not order or order[0]["status"] != "paid":
        return "skipped:not_paid"
    token = secrets.token_urlsafe(16)
    try:
        ledger.x("INSERT INTO grants VALUES (?,?,?,?,?)", order_id, token, 1, now_iso(), None)
    except sqlite3.IntegrityError:
        return "ignored:already_delivered"
    ledger.x("INSERT INTO deliveries VALUES (?,?,?)", "dlv_" + secrets.token_hex(5), order_id, now_iso())
    if mailer:
        mailer(order[0]["buyer_ref"], f"Your download link (MOCKED email): /download/{token}")
    return "delivered"


def can_download(ledger, token: str) -> bool:
    g = ledger.q("SELECT active FROM grants WHERE token=?", token)
    return bool(g and g[0]["active"])
