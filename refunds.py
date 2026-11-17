"""Refunds: the founder approves, the (mock) provider executes, this module
records it and revokes access. The system never refunds money by itself."""
from __future__ import annotations

import sqlite3

from decision_log import now_iso


def record_refund(ledger, order_id: str, amount: float) -> str:
    try:
        ledger.x("INSERT INTO refunds VALUES (?,?,?,?,?)", "re_" + order_id[4:], order_id, amount, "founder", now_iso())
    except sqlite3.IntegrityError:
        return "ignored:already_refunded"
    ledger.x("UPDATE orders SET status='refunded' WHERE id=?", order_id)
    ledger.x("UPDATE grants SET active=0, revoked=? WHERE order_id=?", now_iso(), order_id)
    return "refunded:access_revoked"
