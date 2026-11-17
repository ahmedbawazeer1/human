# How evidence is collected and checked

1. The Researcher model writes search queries in the customer's words.
2. Code fetches real posts from Hacker News (Algolia API) and Stack Exchange, and existing products from Show HN and GitHub. Every result keeps its URL and gets an id (S1, S2...).
3. Posts must mention at least two key terms of the problem (code filter).
4. The model marks posts that show someone experiencing the problem and copies an exact quote.
5. Code keeps a quote only if it appears word for word in the fetched text **and** mentions a term from the founder's own description of the problem. Everything dropped is logged (`drop_unverified_quote`, `drop_offtopic_quote`).
6. Claims in later phases cite these ids; a claim without a valid id is printed as **ASSUMPTION**.

In the demo run this left 0 signals for the weak idea (STOP) and 3 for the scope-creep idea (REPEAT, overridden by the founder and logged).
