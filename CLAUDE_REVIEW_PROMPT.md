# Independent review prompt for Claude

You are providing an independent second opinion on a take-home assignment. Read `README.md`, `verifier.py`, and `test_verifier.py` in this directory. Treat the README as the assignment specification, not as code to modify. Do not edit files, commit, push, or create fixes.

The assignment asks for:

1. A severity-ranked review of the verifier. Every claimed defect must have a regression test that fails against the supplied implementation and passes after a focused fix. If a concern cannot be demonstrated by a failing test, label it as a design concern and explain why.
2. An experiment showing which of the 15 supplied tests still pass when the body of the function they claim to test is replaced with `pass`.
3. A half-page maximum note about what should not have been built, including accurate disclosure of what an AI model produced and what the candidate changed.

Perform an independent analysis:

- First describe the complete data flow from record input to final verdict.
- Inspect every function line by line, including interactions between `load_plugins`, `evaluate_rule`, `reconcile`, `overall`, and `verify`.
- Run representative examples for normal values, missing fields, boundary values, wrong types, malformed records, empty lists, duplicate declarations, unknown rules, and plugin-loading failures.
- Look for cases where a result is accepted without actually being verified, where an empty or skipped check becomes a pass, where malformed data produces raw exceptions, and where advertised plugin behavior is not connected to evaluation.
- Distinguish proven contract violations from policy choices and hardening suggestions. Do not assume every surprising behavior is a bug.
- Review the supplied tests for weak assertions and explain what each mutation experiment demonstrates.

Return a structured report with:

- a concise architecture summary;
- a table of findings with severity, exact location, trigger, observed result, expected result, impact, and a minimal regression-test idea;
- a separate table of non-proven design concerns;
- a test-quality and mutation-survival assessment;
- a short recommendation for the half-page architectural note;
- any disagreements with conclusions that a reviewer might reasonably draw from the code.

Do not write or modify files. Do not propose a fix without first stating the expected contract it restores.
