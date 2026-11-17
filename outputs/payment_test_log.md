# Payment and delivery test log

Run `20261117-171828-7aa9` | 2026-11-17T17:35:29Z | provider: **MOCKED** (no real or sandbox payment service; test buyers only)

| # | Step | Result |
|---|---|---|
| 1 | create checkout A (MOCKED) | ord_f37c66fb1b |
| 2 | payment webhook A | delivered |
| 3 | same webhook A delivered again | ignored:duplicate_event |
| 4 | second payment event for order A | ignored:order_already_paid |
| 5 | forged webhook (bad signature) | rejected:bad_signature |
| 6 | create checkout B (MOCKED) | ord_4dd4d3a665 |
| 7 | payment webhook B | delivered |
| 8 | refund B (founder approved, MOCKED provider) | refunded:access_revoked |
| 9 | buyer A can download | True |
| 10 | buyer B can download after refund | False |
| 11 | payout (MOCKED) | recorded:payout |
| 12 | reconciliation | balanced |

## Reconciliation

| Gross | Fees (MOCKED schedule, ASSUMPTION) | Refunds | Payouts | Expected payout | Balanced |
|---|---|---|---|---|---|
| 38.0 | 1.7 | 19.0 | 17.3 | 17.3 | True |

## Delivery emails (MOCKED, not sent)

- to test-buyer-a@example.invalid: Your download link (MOCKED email): /download/f8FJ7f4wOPdt4As1E6hJLw
- to test-buyer-b@example.invalid: Your download link (MOCKED email): /download/_RTz940cEnqkcJHCqQCnFA

## Checks

- paid_delivers: PASS
- duplicate_webhook_ignored: PASS
- refund_revokes: PASS
- reconciliation_balances: PASS
