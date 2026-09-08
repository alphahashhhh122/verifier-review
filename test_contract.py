"""Boundary and integration controls that preserve the stated contract."""

import datetime
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import verifier as v
from test_regressions import NOW, record


class ContractTests(unittest.TestCase):
    def test_amount_boundaries(self):
        for amount, expected in ((None, v.SKIP), (-1, v.FAIL), (0, v.FAIL),
                                 (1, v.PASS), (10_000_000, v.PASS), (10_000_001, v.FAIL)):
            with self.subTest(amount=amount):
                self.assertEqual(v.check_amount_bounds({"amount_cents": amount}, NOW), expected)

    def test_approval_threshold_and_names(self):
        for amount, name, expected in ((None, None, v.SKIP), (1_000_000, None, v.PASS),
                                      (1_000_001, None, v.FAIL), (1_000_001, "  ", v.FAIL),
                                      (1_000_001, "carol", v.PASS)):
            with self.subTest(amount=amount, name=name):
                self.assertEqual(v.check_approval_recorded(
                    {"amount_cents": amount, "approver": name}, NOW), expected)

    def test_freshness_boundary_offsets_and_fractional_window(self):
        base = NOW - datetime.timedelta(days=30)
        for created, expected in ((base, v.PASS), (base - datetime.timedelta(microseconds=1), v.FAIL)):
            self.assertEqual(v.check_freshness({"created_at": created.isoformat()}, NOW), expected)
        self.assertEqual(v.check_freshness({"created_at": "2026-09-01T05:30:00+05:30",
                                           "max_age_days": 0}, NOW), v.PASS)
        self.assertEqual(v.check_freshness({"created_at": "2026-08-31T12:00:00",
                                           "max_age_days": 0.5}, NOW), v.PASS)

    def test_caller_time_contract_is_explicit(self):
        for now in (None, "today", NOW.replace(tzinfo=None)):
            with self.subTest(now=now), self.assertRaises(v.VerifierError):
                v.check_freshness({"created_at": "2026-09-01T00:00:00Z"}, now)

    def test_empty_and_honest_skip_semantics_are_preserved(self):
        self.assertEqual(
            v.verify({"record_id": "rec-empty", "results": []}, NOW)["verdict"],
            v.PASS,
        )
        self.assertEqual(v.verify(record("actor_present", v.SKIP), NOW)["verdict"], v.PASS)
        # No new required-rule policy is imposed on the existing API.
        self.assertEqual(v.check_freshness({"created_at": "2030-01-01T00:00:00Z"}, NOW), v.PASS)

    def test_actor_requires_a_non_empty_string(self):
        for actor in (True, 0, [], {}, "", "   "):
            with self.subTest(actor=actor):
                self.assertEqual(
                    v.check_actor_present({"actor": actor}, NOW), v.FAIL
                )
        self.assertEqual(v.check_actor_present({"actor": "alice"}, NOW), v.PASS)

    def test_approval_requires_a_non_empty_string_approver(self):
        base = {"amount_cents": v.APPROVAL_THRESHOLD_CENTS + 1}
        for approver in (True, 1, [], {}, "", "   ", None):
            with self.subTest(approver=approver):
                self.assertEqual(
                    v.check_approval_recorded(
                        {**base, "approver": approver}, NOW
                    ),
                    v.FAIL,
                )
        self.assertEqual(
            v.check_approval_recorded({**base, "approver": "carol"}, NOW),
            v.PASS,
        )

    def test_verify_rejects_invalid_now_for_empty_results(self):
        for now in (None, "today", NOW.replace(tzinfo=None)):
            with self.subTest(now=now), self.assertRaises(v.VerifierError):
                v.verify({"results": []}, now)

    def test_verify_requires_a_record_id(self):
        for record_id in (None, "", "   ", 123, [], {}):
            with self.subTest(record_id=record_id), self.assertRaises(
                v.VerifierError
            ):
                v.verify({"record_id": record_id, "results": []}, NOW)

        result = v.verify(
            {"record_id": "rec-001", "results": []}, NOW
        )
        self.assertEqual(result["record_id"], "rec-001")

    def test_overall_rejects_malformed_reports(self):
        malformed = (
            None,
            {},
            [{}],
            [{"agrees": True}],
            [{"recomputed": v.PASS}],
            [{"agrees": "yes", "recomputed": v.PASS}],
            [{"agrees": True, "recomputed": "unknown"}],
        )
        for report in malformed:
            with self.subTest(report=report), self.assertRaises(v.VerifierError):
                v.overall(report)

    def test_duplicate_declarations_do_not_hide_disagreement(self):
        rec = record("actor_present", actor="alice")
        rec["results"].append({"rule_id": "actor_present", "outcome": v.FAIL})
        result = v.verify(rec, NOW)
        self.assertEqual(result["verdict"], v.FAIL)
        self.assertEqual([entry["agrees"] for entry in result["report"]], [True, False])

    def test_honest_failure_is_not_an_overall_pass(self):
        result = v.verify(record("amount_bounds", v.FAIL, amount_cents=-1), NOW)
        self.assertEqual(result["report"][0]["recomputed"], v.FAIL)
        self.assertIs(result["report"][0]["agrees"], True)
        self.assertEqual(result["verdict"], v.FAIL)

    def test_valid_plugin_can_be_explicitly_registered(self):
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "valid.py").write_text(
                "RULES = {'x-deny': lambda record, now: 'fail'}", encoding="utf-8")
            pathlib.Path(folder, "_ignored.py").write_text("raise RuntimeError()", encoding="utf-8")
            pathlib.Path(folder, "helper.py").write_text("VALUE = 1", encoding="utf-8")
            loaded = v.load_plugins(folder)
            self.assertEqual(list(loaded), ["x-deny"])
            self.assertNotIn("x-deny", v.RULES)
            with patch.dict(v.RULES, loaded):
                result = v.verify(record("x-deny", v.FAIL), NOW)
                self.assertEqual(result["report"][0]["recomputed"], v.FAIL)
                self.assertIs(result["report"][0]["agrees"], True)
                self.assertEqual(result["verdict"], v.FAIL)

    def test_json_object_and_native_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder, "record.json")
            path.write_text('{"results": []}', encoding="utf-8")
            self.assertEqual(v.load_record(str(path)), {"results": []})
            path.write_text("{bad", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                v.load_record(str(path))
            with self.assertRaises(FileNotFoundError):
                v.load_record(str(path.with_name("missing.json")))


if __name__ == "__main__":
    unittest.main()
