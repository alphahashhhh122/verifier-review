# Debugging notes

These are historical observations recorded while reading the supplied baseline, before fixes. They are not the final findings list. See REVIEW.md for corrected classifications, evidence, implemented changes, and policies deliberately preserved.

Review corrections: explicit plugin registration with `RULES.update(load_plugins(path))` works; automatic registration was not promised. `evaluate_rule` is indirectly exercised by supplied reconciliation tests even though it has no direct test. Empty/all-skip reports are documented policy, not automatically critical bugs. A runtime exception does not necessarily crash the host process: it may be caught by a caller. Statements below suggesting implicit author intent are hypotheses, not established facts.

## `check_freshness`

- Missing or empty `created_at` returns `skip`.
- Invalid timestamps raise `VerifierError`.
- A future timestamp produces a negative age and currently returns `pass`.
- The record may choose `max_age_days`; otherwise the default is 30 days.
- A non-numeric `max_age_days` may raise a raw `TypeError`.
- `now` and the parsed timestamp must be timezone-compatible for subtraction.

## Evidence run

With `now = 2026-09-01T00:00:00Z`:

```text
recent timestamp       -> pass
old timestamp           -> fail
missing timestamp       -> skip
invalid timestamp       -> VerifierError
```

## `_parse_timestamp`

- Leading and trailing whitespace is removed.
- A trailing `Z` is converted to an explicit UTC offset before parsing.
- Offset-aware timestamps retain their supplied offset.
- Naive timestamps are treated as UTC.
- Invalid timestamp text is converted to `VerifierError`.
- Truthy non-string values such as `123` reach this helper and raise `AttributeError` from `.strip()` rather than `VerifierError`.

## `check_actor_present`

- Missing or `None` actor returns `skip`.
- Empty or whitespace-only string returns `fail`.
- A non-empty string returns `pass`.
- The function converts every non-`None` value to text before checking it. Therefore `0`, `False`, `[]`, and `['alice']` currently return `pass`, even though they are not clearly actor names.
- The `now` parameter is accepted for a uniform rule signature but is unused here.

## `check_amount_bounds`

- Missing or `None` amount returns `skip`.
- The amount must be an `int`; booleans are explicitly rejected even though Python makes `bool` a subclass of `int`.
- Zero and negative values return `fail`.
- Values from 1 through 10,000,000 cents pass; values above 10,000,000 fail.
- Floats and numeric strings return `fail` rather than being coerced.
- The `now` parameter is unused here.

## `check_approval_recorded`

- Missing amount returns `skip`.
- Amounts at or below 1,000,000 cents return `pass` without checking `approver`; the threshold is exclusive.
- Amounts above the threshold require a truthy, non-whitespace approver.
- For large amounts, `None`, empty strings, whitespace, zero, `False`, and empty lists fail.
- For large amounts, non-empty lists and arbitrary objects can pass after conversion to text, even though they are not clearly approver names.
- Invalid amount types such as `2_000_000.0` or `'2000000'` return `pass` because they are not integers and the condition uses `or amount <= threshold`. This assumes `check_amount_bounds` is always run separately; the verifier does not enforce that.
- Negative amounts and booleans also return `pass` here; `check_amount_bounds` would reject them if declared.
- The `now` parameter is unused.

## Possible hardening improvements (not yet fixes)

These ideas should be evaluated against the intended contract after the full module review:

- `check_freshness`: validate that `created_at` is a string; validate that `max_age_days` is an integer (not a boolean) and non-negative; decide whether future timestamps should fail; normalize or explicitly reject incompatible timezone inputs; decide whether the freshness policy should be trusted from the record.
- `_parse_timestamp`: reject non-string and blank inputs with `VerifierError` rather than allowing `AttributeError`; decide whether naive timestamps should be assumed UTC or rejected as ambiguous.
- `check_actor_present`: require a string actor and apply `.strip()` to that string, so numbers, lists, and arbitrary objects cannot count as names. Preserve the current distinction between missing (`skip`) and present-but-empty (`fail`) if that is the intended contract.
- `check_amount_bounds`: move the hard-coded ceiling into a named constant; keep the strict integer and boolean checks; confirm that the inclusive upper boundary is intended.
- `check_approval_recorded`: validate amount type instead of treating every non-integer as safely below the threshold; require a string approver; decide whether this rule must be safe when declared without `amount_bounds`, or whether the verifier should enforce required rule dependencies.
- The unused `now` parameter is acceptable if all rules share one callable signature, but the reason should remain documented.

## Built-in `RULES` registry

- `RULES` maps the four string identifiers used in records to their Python functions.
- `evaluate_rule` later consults this global mapping by exact key.
- The type annotation says each callable returns `str`, although `evaluate_rule` is annotated to allow `None` for unresolved extensions.
- The registry itself has no dependency ordering: a record can declare `approval_recorded` without also declaring `amount_bounds`.
- The later `load_plugins()` function returns a separate mapping; this registry is not automatically updated by it. The integration path for making loaded plugins visible to `evaluate_rule` needs to be checked.

## `load_plugins`

- A missing or non-directory path returns an empty mapping.
- Python files are processed in sorted filename order.
- Files beginning with `_` are skipped.
- Each candidate is imported from its file path, then its module-level `RULES` attribute is collected.
- Any exception during plugin loading is swallowed and the plugin is silently skipped.
- `RULES` is accepted without validating that it is a mapping, that keys use the `x-` prefix, or that values are callable.
- A directory containing `verifier.py` can load the built-in module as if it were a plugin, because the loader scans every non-underscore `.py` file.
- The function returns `collected` but does not merge it into the global built-in `RULES` registry. A caller must perform that integration separately; `evaluate_rule()` currently has no plugin mapping parameter.

## `load_plugins` evidence run

Using a temporary plugin directory containing a valid plugin, a plugin that raises during import, an underscore-prefixed plugin, and a module with no `RULES` attribute:

```text
missing directory -> {}
plugin directory  -> {'x-valid': <function rule ...>}
```

The broken and underscore-prefixed plugins were absent, and the module without `RULES` contributed nothing.

## `evaluate_rule` and its connection to plugins

- A built-in identifier is looked up in the global `RULES` mapping and its function is called.
- An unknown non-extension identifier raises `VerifierError`.
- An unknown `x-` identifier returns `None` instead of raising.
- `reconcile()` later treats `None` as agreement, so an unresolved extension can make an unverified declaration appear honest and can contribute to an overall `pass`.
- `load_plugins()` can return a working `x-valid` function, but `evaluate_rule("x-valid", ...)` still returns `None` because the returned plugin mapping is not connected to the global `RULES` mapping.
- Non-string rule IDs are not validated here: `None` and integers cause `AttributeError`, while a list can cause `TypeError` because dictionary membership requires a hashable value.

## `reconcile`

- The function requires `results` to be present and to be a list.
- An empty list is accepted and returns an empty report.
- Each list item is assumed to be a mapping; a string or other non-mapping item causes a raw `AttributeError` from `.get()`.
- Missing or falsey `rule_id` values raise `VerifierError`.
- Declared outcomes must be exactly `pass`, `fail`, or `skip`.
- Built-in rules are recomputed and compared exactly with the declared outcome.
- A disagreement is represented in the report with `agrees=False`; the function does not itself reduce the report to a final verdict.
- If `evaluate_rule()` returns `None`, `agrees` is forced to `True`, so any declared outcome—including `fail` or `skip`—is accepted for an unresolved extension.
- Duplicate rule entries are allowed and evaluated independently; no uniqueness or required-rule check exists.
- An empty report is structurally valid and will later be treated as a passing overall verdict by `overall()`.

## `overall`

- The function scans report entries in order and immediately returns `fail` on the first disagreement.
- A recomputed `fail` also returns `fail`, even if `agrees` is true.
- Recomputed `pass`, `skip`, or `None` can produce an overall `pass` when `agrees` is true.
- An empty report returns `pass` because the loop has no entries.
- A report containing an unresolved extension (`recomputed=None`, `agrees=True`) therefore returns `pass`.
- The declared outcome is not inspected directly; it matters only through `agrees`.
- The function assumes every entry has `agrees` and `recomputed`; malformed direct inputs cause `KeyError` or `TypeError` rather than `VerifierError`.

## `verify`

- `verify()` is a thin orchestration function: it calls `reconcile()`, then `overall()`, and returns the record ID, report, and verdict.
- Exceptions from `reconcile()` propagate to the caller.
- `record_id` is copied with `.get()` and is not required; a record without one can still receive `pass`.
- An empty `results` list therefore produces a top-level passing result.
- An unresolved extension produces a top-level passing result even when its declared outcome is `fail`, because of the `None`/`agrees=True` behavior in `reconcile()`.
- The supplied `now` value is passed consistently into the rule evaluation path.

## `load_record`

- Opens the supplied path as UTF-8 and calls `json.load()`.
- Valid JSON objects are returned unchanged.
- Valid JSON arrays are also returned unchanged, despite the `dict` return annotation; passing one to `verify()` would later fail at `.get()`.
- Missing files raise `FileNotFoundError`.
- Invalid or empty JSON raises `JSONDecodeError`.
- The helper does not wrap I/O or JSON errors in `VerifierError`, and it does not validate that the decoded value is a dictionary.
