# Payment and delivery test log

Run `20261117-200539-79c8` | 2026-11-17T20:23:06Z | provider: **MOCKED** (no real or sandbox payment service; test buyers only)

| # | Step | Result |
|---|---|---|
| 1 | create checkout A (MOCKED) | ord_1d8b14698f |
| 2 | payment webhook A | delivered |
| 3 | same webhook A delivered again | ignored:duplicate_event |
| 4 | second payment event for order A | ignored:order_already_paid |
| 5 | forged webhook (bad signature) | rejected:bad_signature |
| 6 | create checkout B (MOCKED) | ord_9f38b2d082 |
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

- to test-buyer-a@example.invalid: Your download link (MOCKED email): /download/_Ba6E24YVeg6OFITLvAmtw
- to test-buyer-b@example.invalid: Your download link (MOCKED email): /download/Bz9KYMeOs-gGKa3r2dnYqw

## Checks

- paid_delivers: PASS
- duplicate_webhook_ignored: PASS
- refund_revokes: PASS
- reconciliation_balances: PASS
