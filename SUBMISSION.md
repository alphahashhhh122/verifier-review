# Reproducing the submission

The original assignment README and fifteen supplied tests are unchanged. Implementation and new review utilities use the Python standard library; pytest is used to run the supplied suite as permitted by the original README. Python 3.12 was used locally and in CI.

```powershell
python -m pip install pytest
python -m pytest -q
python reproduce_regressions.py
python audit_tests.py
```

`reproduce_regressions.py` checks out no branches and edits no working files: it extracts the original implementation through `git show` into temporary directories and runs the same current regression tests against both versions. Expected: original fails with pytest exit 1, current passes with exit 0. Git history is required. A GitHub source download alone does not include that history; use a clone or the supplied Git bundle.

For a standard-library-only run of the new tests:

```powershell
python -m unittest -v test_regressions test_contract
```

Read `REVIEW.md` for findings and design decisions, `TEST_AUDIT.md` for the mutation experiment, and `NOTE.md` for the short architectural note and AI disclosure.

## History and evidence

- `dd0e41b`: unchanged supplied baseline.
- `4984175`: GitHub test workflow; original 15 pass.
- `f379c62`: failing regression cases, before any implementation change.
- `5a9591c`: focused fixes and boundary controls.
- `b11890f` then `313db86`: independent-review regression for dataclass plugin imports, then its fix.
- Later commits add independently checked audit results and final documentation; all AI-assisted commits retain attribution trailers.

Evidence XML captures before/after output. Temporary paths and test runtime values in those files identify the local run and are not installation paths to reuse.

GitHub Actions runs the complete suite, the expected-before/after reproduction, and the original-test mutation audit. The reproduction step succeeds only when baseline tests fail as expected and the corrected version passes.

## Candidate completion

Candidate-reported active time so far: **2–2.5 hours**, including reading, discussion, and review. Add any subsequent review time before sending to Ben. Automated run duration is not substituted for candidate effort or the suggested three-to-four-hour budget.

The repository is private. Ben needs repository access, or the candidate can send the packaged ZIP/bundle. No email or invitation has been sent automatically.
