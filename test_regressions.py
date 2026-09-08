"""Regression cases; uses only unittest and the standard library."""

import datetime
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import verifier as v

NOW = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)


def record(rule, outcome=v.PASS, **fields):
    return {**fields, "results": [{"rule_id": rule, "outcome": outcome}]}


class RegressionTests(unittest.TestCase):
    def test_unresolved_extensions_are_not_agreement(self):
        for outcome in v.VALID_OUTCOMES:
            with self.subTest(outcome=outcome):
                result = v.verify(record("x-unavailable", outcome), NOW)
                self.assertIsNone(result["report"][0]["recomputed"])
                self.assertIs(result["report"][0]["agrees"], False)
                self.assertEqual(result["verdict"], v.FAIL)

    def test_registered_rule_must_return_a_valid_outcome(self):
        for value in (None, "unknown", True, [], {"outcome": "pass"}):
            with self.subTest(value=value):
                with patch.dict(v.RULES, {"x-broken": lambda r, n: value}):
                    with self.assertRaises(v.VerifierError):
                        v.verify(record("x-broken"), NOW)

    def test_approval_cannot_pass_malformed_amounts(self):
        for amount in (2_000_000.0, "2000000", True, False, [], {}):
            with self.subTest(amount=amount):
                result = v.verify(record("approval_recorded", amount_cents=amount), NOW)
                self.assertEqual(result["report"][0]["recomputed"], v.FAIL)
                self.assertEqual(result["verdict"], v.FAIL)

    def test_valid_plugin_loads_without_incidental_imports(self):
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "valid.py").write_text(
                "RULES = {'x-valid': lambda record, now: 'pass'}\n", encoding="utf-8"
            )
            # A fresh interpreter deliberately excludes site startup and pytest.
            source = (
                "import verifier; "
                f"rules = verifier.load_plugins({folder!r}); "
                "assert 'x-valid' in rules, rules; "
                "assert rules['x-valid']({}, None) == 'pass'"
            )
            completed = subprocess.run(
                [sys.executable, "-S", "-B", "-c", source],
                cwd=pathlib.Path(v.__file__).parent,
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_plugin_registry_is_validated_before_registration(self):
        sources = (
            "RULES = {'amount_bounds': lambda record, now: 'pass'}",
            "RULES = {'x-invalid': 42}",
            "RULES = None",
            "RULES = [('x-invalid', lambda record, now: 'pass')]",
            "RULES = {12: lambda record, now: 'pass'}",
        )
        for source in sources:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as folder:
                pathlib.Path(folder, "plugin.py").write_text(source, encoding="utf-8")
                with self.assertRaises(v.VerifierError):
                    v.load_plugins(folder)

    def test_plugin_callback_must_accept_record_and_now(self):
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "arity.py").write_text(
                "RULES = {'x-arity': lambda: 'pass'}",
                encoding="utf-8",
            )
            with self.assertRaises(v.VerifierError):
                v.load_plugins(folder)

    def test_invalid_plugin_registry_is_removed_from_sys_modules(self):
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "bad.py").write_text(
                "RULES = {'x-bad': 1}", encoding="utf-8"
            )
            before = {
                name for name in sys.modules
                if name.startswith("_verifier_plugin_")
            }
            with self.assertRaises(v.VerifierError):
                v.load_plugins(folder)
            after = {
                name for name in sys.modules
                if name.startswith("_verifier_plugin_")
            }
            self.assertEqual(after, before)

    def test_plugin_supports_standard_dataclass_import(self):
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "typed_plugin.py").write_text(
                "from __future__ import annotations\n"
                "from dataclasses import dataclass\n"
                "@dataclass\n"
                "class Result:\n"
                "    outcome: str = 'pass'\n"
                "RULES = {'x-typed': lambda record, now: Result().outcome}\n",
                encoding="utf-8",
            )
            loaded = v.load_plugins(folder)
            self.assertIn("x-typed", loaded)
            self.assertEqual(loaded["x-typed"]({}, NOW), v.PASS)

    def test_duplicate_plugin_ids_are_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, outcome in (("a.py", "fail"), ("b.py", "pass")):
                pathlib.Path(folder, name).write_text(
                    f"RULES = {{'x-duplicate': lambda record, now: {outcome!r}}}",
                    encoding="utf-8",
                )
            with self.assertRaises(v.VerifierError):
                v.load_plugins(folder)

    def test_broken_plugin_is_reported_to_the_caller(self):
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "broken.py").write_text(
                "raise RuntimeError('broken plugin')", encoding="utf-8"
            )
            with self.assertRaises(v.VerifierError):
                v.load_plugins(folder)

    def test_malformed_record_shapes_raise_verifier_error(self):
        cases = [None, [], "record", {"results": [None]}, {"results": ["rule"]}]
        cases.extend(record(rule_id) for rule_id in (123, ["actor_present"], {"id": "x"}))
        for case in cases:
            with self.subTest(record=case):
                with self.assertRaises(v.VerifierError):
                    v.verify(case, NOW)

    def test_malformed_freshness_fields_raise_verifier_error(self):
        cases = [{"created_at": value} for value in (123, False, 0, [], {})]
        cases.extend(
            {"created_at": "2026-08-30T00:00:00Z", "max_age_days": days}
            for days in ("30", None, True, -1, float("nan"), float("inf"), 10**100)
        )
        for fields in cases:
            with self.subTest(fields=fields):
                with self.assertRaises(v.VerifierError):
                    v.verify(record("freshness", **fields), NOW)

    def test_load_record_rejects_non_object_json(self):
        for contents in ("[]", "null", "42", '"record"'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as folder:
                path = pathlib.Path(folder, "record.json")
                path.write_text(contents, encoding="utf-8")
                with self.assertRaises(v.VerifierError):
                    v.load_record(str(path))


if __name__ == "__main__":
    unittest.main()
