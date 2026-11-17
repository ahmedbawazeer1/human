QA agent: no model prompt on purpose.

The QA agent (`agents/qa.py`) is plain code so the Phase 3 test gate cannot be talked into passing. It checks each product section for length, the required phrase from the MVP spec, unsourced statistics, placeholder text and rule-breaking text (income promises, fake social proof, fake urgency), and checks that the user docs contain a quick start, how to get help and the refund policy.
