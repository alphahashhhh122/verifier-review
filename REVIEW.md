# Review of the supplied verifier

Locations below refer to the unchanged baseline `dd0e41b2f4b1846d83fcc9945267b4e876abfca1`. Severity reflects incorrect verification results and operational reliability; there is no evidence of a production exploit or financial loss.

## Architecture and contract

`load_record` decodes a JSON file. The caller supplies the record and reference time to `verify`, which calls `reconcile`. For each declared result, `evaluate_rule` dispatches through the global `RULES` mapping. `reconcile` records agreement, and `overall` fails on disagreement or a reproduced failure. Rules not declared by the record are not executed.

`load_plugins` returns a separate mapping. An application can register it with `RULES.update(load_plugins(path))`; automatic registration was never promised. The loader executes trusted deployment Python, not sandboxed data. Its existence is an architectural concern, but the lack of automatic registration is not itself a demonstrated defect.

## Findings supported by failing regression tests

Each test below is in `test_regressions.py`; the unchanged tests fail against the original source and pass against the corrected implementation. `python reproduce_regressions.py` reproduces that transition in temporary copies. The original 15 tests remain unchanged.

| ID / severity | Baseline location | Trigger and observed behavior | Expected contract, impact, and correction | Regression method |
|---|---|---|---|---|
| F1 / High | `reconcile`, 187–191; `overall`, 209–214 | An unknown `x-` rule returns `None`, becomes `agrees=True`, and produces overall `pass`, even when the declaration says `fail`. | A declared result that was not reproduced cannot be reported as agreement. Keep `recomputed=None` for diagnosis, set agreement false, and let the existing reducer fail. This avoids inventing a new verdict type. | `test_unresolved_extensions_are_not_agreement` (all three declared outcomes) |
| F2 / Medium | `evaluate_rule`, 160–161 | An installed rule returns `None` or an invalid outcome. `None` is indistinguishable from an unavailable implementation; invalid outputs are returned without diagnosis. | An executed rule must return one of the three documented outcomes. Raise `VerifierError` for implementation contract violations. A registered callback returning `None` is different from an unknown extension. | `test_registered_rule_must_return_a_valid_outcome` |
| F3 / Medium | `check_approval_recorded`, 99–100 | `amount_cents='2000000'` or `2000000.0`, no approver, and only approval declared results in `pass`. | A malformed amount cannot establish that approval is unnecessary. Reject non-integer amounts, including booleans, consistently with the sibling amount rule. This does not assert that a malformed string was actually a financial transaction. Zero/negative integers remain the bounds rule's responsibility. | `test_approval_cannot_pass_malformed_amounts` |
| F4 / Medium | import 18; `load_plugins`, 134–140 | In a fresh `python -S` process a valid plugin silently disappears because `importlib.util` was never imported. Pytest/site startup can mask this. | Loading a valid plugin must not depend on unrelated imports. Import `importlib.util` explicitly. A subprocess regression checks the actual loader, not just attribute presence. | `test_valid_plugin_loads_without_incidental_imports` |
| F5 / Medium | `load_plugins`, 141 | A plugin can return built-in IDs or non-callable values; the loader returns these as registrable rules. | The loader documents an extension-prefixed rule map. Validate dict shape, string IDs with `x-`, and callable values before returning it. Prevent accidental built-in replacement through the supported loader; trusted code can still deliberately alter globals. | `test_plugin_registry_is_validated_before_registration` |
| F6 / Medium | `reconcile`, 173/181; `evaluate_rule`, 160/162; `_parse_timestamp`, 234; `check_freshness`, 60/65 | Top-level lists, non-dict result entries, non-string IDs, and malformed date/window fields raise raw `AttributeError`/`TypeError` or silently skip. | Malformed record data should use the stated `VerifierError` boundary. Validate shapes and timestamp/window values. Accept nonnegative representable numeric windows, including fractional days; reject booleans, NaN, infinity and overflow. Native file and JSON syntax errors remain documented separately. | `test_malformed_record_shapes_raise_verifier_error`; `test_malformed_freshness_fields_raise_verifier_error` |
| F7 / Low | `load_record`, 246–249 | Valid JSON arrays/scalars are returned despite the helper promising a record dict, then fail later in verification. | Require a JSON object at the loader boundary, with `VerifierError` for wrong top-level shape. This improves diagnosis; it is not evidence of a passing-verdict bypass. | `test_load_record_rejects_non_object_json` |
| F8 / Medium | `load_plugins`, 137–138 | A plugin with postponed annotations and a dataclass fails import: dataclasses cannot find its defining module in `sys.modules`. The baseline silently omits it; the initial patch surfaced the error but did not make it work. | Support ordinary module initialization by registering the module before execution. Use a path-specific name to avoid overwriting unrelated imported modules, and restore prior state on execution failure. This supports standalone files, not a package-discovery framework. | `test_plugin_supports_standard_dataclass_import` |

F1 and the unknown-extension-declared-failure example are one root cause, not two inflated findings. F2 overlaps F1's symptoms but independently checks an installed implementation's return contract.

## Explicit hardening decisions

The following changes choose a stricter contract rather than claim the original documentation explicitly required it. Their before/after tests are included, but failing a newly chosen assertion alone does not prove an original defect.

| Decision | Evidence / test | Tradeoff |
|---|---|---|
| Raise on plugin import failure rather than quietly omit it. | `test_broken_plugin_is_reported_to_the_caller` | Prevents an operator mistaking a partial load for complete configuration. Applications that intentionally tolerate broken plugins must now handle the error. |
| Reject duplicate plugin IDs, including already registered IDs. | `test_duplicate_plugin_ids_are_not_silently_overwritten` | Avoids filename order silently choosing between pass/fail implementations. Implicit plugin replacement/reloading is no longer supported. |
| Require an aware caller-supplied datetime when evaluating a present timestamp. | `test_contract.py::ContractTests::test_caller_time_contract_is_explicit` | Gives a clear error for ambiguous caller time. This is caller API validation, not a discovered malformed-record exploit. |

## Design concerns and preserved behavior

| Concern | Why it is not claimed as a proven violation / recommendation |
|---|---|
| Empty declarations and all-honest-SKIP reports return PASS. | This follows the reducer's documented policy. The API verifies selected declarations, not compliance with an external required-rule policy. Do not call this a critical bypass without that external requirement. Preserve behavior, document its limits. |
| The record selects rules and its freshness window. | The window override is explicit in the docstring. An external policy authority is required if these records are used as approval evidence. Arbitrarily forcing all four rules would contradict existing subset tests. |
| Future timestamps pass; naive timestamp strings are assumed UTC. | Neither a future-time tolerance nor a stricter timestamp grammar is specified. Preserve and document these choices; a proposed policy test would encode a new requirement. |
| Actor/approver values are converted to strings. | String-only identities are sensible, but no schema states them. Leave unchanged and recommend defining the identity schema. Do not claim a nonempty name establishes authorization or identity authenticity. |
| Duplicate declarations are accepted. | For the deterministic built-ins, conflicting declarations still fail; duplicates do not erase earlier disagreement. Stateful/mutating plugins require a separate trusted plugin contract. |
| Global registry and executable plugins. | Explicit registration works. Callbacks can mutate records, use clocks/network, or modify globals; the loader is not a sandbox. A pure, trusted rule contract is needed. Arbitrary-code import is not a vulnerability by itself when the deployment controls the directory. |
| Missing record IDs, raw file errors, direct malformed reports. | No required ID schema or universal exception wrapper is specified. `overall` consumes an internal report; it need not become another full parser. Keep scope narrow. |

## Validation and limits

- Original baseline: 15 tests pass locally and in GitHub Actions.
- Regression commit `f379c62`: new cases fail on unchanged implementation; GitHub Actions records the failed run. Some pytest versions count unittest subtest failures separately, so their displayed total is not a count of distinct defects.
- Focused implementation commit `5a9591c`: the same regression methods pass, alongside the original suite and boundary controls.
- Independent Luna review found F8 after the first patch. Commit `b11890f` captures its failure before the follow-up import fix. Its regression also fails against the original baseline.
- `test_contract.py` exercises amount/approval boundaries, fractional windows, equivalent timezone instants, explicit plugin registration, honest failure, duplicate disagreement, and preserved empty/skip behavior.
- The mutation audit checks original tests against original source, independently of these fixes; see `TEST_AUDIT.md`.
- Coverage is finite and aimed at the stated contracts. It is not a proof of absence of bugs, a security audit of arbitrary plugins, or an exhaustive test of every possible Python object.

Independent review also reproduced an intentionally mutating callback that changes later rule inputs, making verdicts order-dependent. This remains a trusted-plugin/purity limitation, not an assertion that arbitrary plugin code can be secured by shallow validation. Relative package imports, hot reloading, and plugin isolation are not implemented.
