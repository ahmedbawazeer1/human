"""Checkout (MOCKED): opens a test checkout for a buyer and returns the order id.

No real or sandbox payment page exists. The order is created in the local
ledger as "pending"; only a signed `payment.succeeded` webhook from the
(mock) provider marks it paid and triggers delivery (see webhooks.py).
"""
from __future__ import annotations

from payments import MockPaymentProvider

MOCK = "MOCKED"


def start_checkout(provider: MockPaymentProvider, product: str, amount: float, buyer_ref: str,
                   currency: str = "USD") -> str:
    if amount is None or amount <= 0:
        raise ValueError("checkout needs a positive price")
    return provider.create_checkout(product, float(amount), buyer_ref, currency)
