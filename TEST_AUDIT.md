# Original supplied-test mutation audit

Run the reproducible audit with:

```text
python audit_tests.py --output evidence/original-test-audit.json
```

The runner reads `verifier.py` and `test_verifier.py` from
`dd0e41b2f4b1846d83fcc9945267b4e876abfca1` with `git show`, so later checkout
changes cannot affect the fixture. It copies those files into a fresh
temporary directory for the baseline control and for every mutant. For each
mutant it parses the verifier with `ast`, replaces the whole mapped function
body with `pass`, and invokes pytest with `sys.executable`. The environment
sets `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `PYTHONDONTWRITEBYTECODE=1`.

The baseline control passed all 15 tests. The mapped run killed 14 mutants and
had exactly one survivor. JUnit XML keeps an assertion failure, an exception
error, and a collection error distinct; only a failure or error is counted as
a mutation kill. This run had 14 ordinary test failures, with no test errors,
collection errors, timeouts, or runner errors. The runner fingerprints the
working copies before and after the audit; both original files were unchanged.
The JSON evidence records the source hashes and every `git show`/pytest
command.

| Supplied test | Intended target | Call path | Result |
| --- | --- | --- | --- |
| `test_freshness_passes_for_a_recent_record` | `check_freshness` | direct | killed |
| `test_freshness_fails_for_an_old_record` | `check_freshness` | direct | killed |
| `test_freshness_skips_when_no_timestamp` | `check_freshness` | direct | killed |
| `test_freshness_rejects_an_unparseable_timestamp` | `check_freshness` | direct | killed |
| `test_actor_present_passes_for_a_named_actor` | `check_actor_present` | direct | killed |
| `test_actor_present_fails_for_whitespace` | `check_actor_present` | direct | killed |
| `test_amount_bounds_passes_inside_the_range` | `check_amount_bounds` | direct | killed |
| `test_amount_bounds_flags_negative_amounts` | `check_amount_bounds` | `reconcile` → `evaluate_rule` → rule | **survives** |
| `test_amount_bounds_fails_above_the_ceiling` | `check_amount_bounds` | direct | killed |
| `test_approval_required_above_the_threshold` | `check_approval_recorded` | direct | killed |
| `test_approval_satisfied_by_a_named_approver` | `check_approval_recorded` | direct | killed |
| `test_reconcile_agrees_when_the_declaration_is_honest` | `reconcile` | direct → `evaluate_rule` | killed |
| `test_reconcile_catches_a_lie` | `reconcile` | direct → `evaluate_rule` | killed |
| `test_reconcile_rejects_an_unknown_rule` | `reconcile` | direct → `evaluate_rule` | killed |
| `test_verify_returns_a_verdict_and_a_report` | `verify` | direct → `reconcile` → `evaluate_rule` | killed |

The negative-amount test is intentionally mapped to `check_amount_bounds`,
even though its body calls `reconcile`. The record declares the
`amount_bounds` rule and the assertion only checks that one report entry
exists. Replacing `check_amount_bounds` with `pass` makes `evaluate_rule`
return `None`; `reconcile` treats that as an unresolved extension and still
appends the entry, so this test passes. Replacing `reconcile` would make it
fail, but that would answer a different target question.

`evaluate_rule` is indirectly exercised by the reconciliation and end-to-end
tests, including the negative-amount test. It has no direct supplied test.
`load_plugins` is never called by the supplied suite, so it is untested and
has no mutation row.
