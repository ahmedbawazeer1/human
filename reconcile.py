"""Reconciliation: match orders, payments, fees, refunds and payouts."""
from __future__ import annotations


def reconcile(ledger) -> dict:
    issues = []
    orders = ledger.q("SELECT * FROM orders")
    pays = {p["order_id"]: p for p in ledger.q("SELECT * FROM payments")}
    refs = {r["order_id"]: r for r in ledger.q("SELECT * FROM refunds")}
    grants = {g["order_id"]: g for g in ledger.q("SELECT * FROM grants")}
    for o in orders:
        p = pays.get(o["id"])
        if o["status"] in ("paid", "refunded"):
            if not p:
                issues.append(f"{o['id']}: marked {o['status']} but no payment")
            elif abs(p["amount"] - o["amount"]) > 0.001:
                issues.append(f"{o['id']}: payment {p['amount']} != order {o['amount']}")
            if o["id"] not in grants:
                issues.append(f"{o['id']}: paid but never delivered")
        if o["status"] == "pending" and o["id"] in grants:
            issues.append(f"{o['id']}: delivered without payment")
        if o["status"] == "refunded":
            if o["id"] not in refs:
                issues.append(f"{o['id']}: refunded status without refund record")
            if grants.get(o["id"], {}).get("active"):
                issues.append(f"{o['id']}: refunded but access still active")
    gross = round(sum(p["amount"] for p in pays.values()), 2)
    fees = round(sum(p["fee"] for p in pays.values()), 2)
    refunded = round(sum(r["amount"] for r in refs.values()), 2)
    payouts = round(sum(p["amount"] for p in ledger.q("SELECT * FROM payouts")), 2)
    expected = round(gross - fees - refunded, 2)
    if abs(expected - payouts) > 0.01:
        issues.append(f"payouts {payouts} != gross {gross} - fees {fees} - refunds {refunded} = {expected}")
    return {"orders": len(orders), "gross": gross, "fees": fees, "refunds": refunded, "payouts": payouts,
            "expected_payout": expected, "balanced": not issues, "issues": issues}
