# Take-home: review an agent-written verifier

`verifier.py` checks decision records against a rule registry. A record
declares which rules were applied and what each returned. The verifier
recomputes those rules and reports whether the declarations hold up.

`test_verifier.py` holds fifteen tests. All fifteen pass:

```bash
python3 -m pytest -q
```

An AI agent wrote both files in one pass. Nobody has reviewed either. That is
the normal starting condition for a lot of code here, and reviewing it is the
work.

## What to send back

**1. A review.** Find what is wrong. Rank the findings by severity. Each one
needs a test that fails against the current code and passes once the defect
is fixed. If you believe something is wrong but cannot write a failing test
for it, say so and explain why.

**2. A verdict on the supplied tests.** Of the fifteen tests that came with
the module, which would still pass if you deleted the body of the function
they claim to test? Show how you checked.

**3. A short note.** Half a page at most, on what should not have been built
at all.

## Ground rules

Standard library only, apart from `pytest`. Use whatever tools you like,
agents included. Keep the co-authorship trailers in your commits, and say in
the note what the model produced and what you changed.

Budget three to four hours. Send a repo link or a zip, and the hours you
actually spent.
