# Candidate review before sending

This checklist is for Nirwan. It is not a claim that these review steps have already happened.

Two tasks are intentionally left for the candidate: [extension disagreement coverage](https://github.com/alphahashhhh122/verifier-review/issues/1) and [personal review and final note](https://github.com/alphahashhhh122/verifier-review/issues/2). These are real candidate contributions, not fabricated defects or a reason to remove prior AI attribution.

1. Read F1 in REVIEW.md. Explain why an unavailable result is not agreement, and why the patch keeps `None` visible but makes the final verdict fail. Read its regression test and compare the failed and passing runs.
2. Read the other findings and the hardening table. Explain why duplicate plugin IDs and plugin error reporting are explicit policy choices. Be able to explain why empty/skip reports and future dates were left unchanged.
3. Run `python reproduce_regressions.py`. Confirm the same tests fail against the original implementation and pass against the fixed version. A red historical run is expected; the latest run should be green.
4. Run `python audit_tests.py` and read TEST_AUDIT.md. Explain why the negative-amount test survives removal of `check_amount_bounds`, even though its direct call is to `reconcile`. Understand the mapping and the difference between a test failure and a test-collection problem.
5. Read NOTE.md. It must remain at most half a page and include what should not have been built plus accurate AI attribution. If you personally change code, tests, or reasoning, record those specific changes. If you make no code changes after review, say so; do not invent manual authorship.
6. Add any final review time to the reported 2–2.5 hours. Use your actual total.
7. Check the repository commit history and AI co-authorship trailers, and the latest successful Actions run. Give Ben access to the private repository or send the ZIP with history bundle.

Suggested disclosure after you actually complete the review, if still accurate:

> Codex and Luna agents drafted the analysis, tests, fixes, and audit. I directed the review, checked the code and reproduction results, and accepted the final changes after review; I made no separate manual code edits. An externally supplied Claude-labelled review contributed additional hypotheses that Codex checked.

Until that review is complete, use NOTE.md's current wording rather than asserting completed verification by the candidate.
