"""Tests for the decision record verifier."""

import datetime

import pytest

from verifier import (
    FAIL,
    PASS,
    SKIP,
    VerifierError,
    check_actor_present,
    check_amount_bounds,
    check_approval_recorded,
    check_freshness,
    overall,
    reconcile,
    verify,
)

NOW = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)


def _make_record(**overrides):
    """Build a record that passes everything unless overridden."""
    record = {
        "record_id": "rec-001",
        "created_at": "2026-08-25T00:00:00Z",
        "actor": "alice",
        "amount_cents": 5000,
        "results": [],
    }
    record.update(overrides)
    return record


def _declare(*pairs):
    return [{"rule_id": rule, "outcome": outcome} for rule, outcome in pairs]


# --- freshness -------------------------------------------------------------


def test_freshness_passes_for_a_recent_record():
    record = _make_record(created_at="2026-08-30T00:00:00Z")
    assert check_freshness(record, NOW) == PASS


def test_freshness_fails_for_an_old_record():
    record = _make_record(created_at="2026-01-01T00:00:00Z")
    assert check_freshness(record, NOW) == FAIL


def test_freshness_skips_when_no_timestamp():
    record = _make_record(created_at=None)
    assert check_freshness(record, NOW) == SKIP


def test_freshness_rejects_an_unparseable_timestamp():
    record = _make_record(created_at="not-a-date")
    with pytest.raises(VerifierError):
        check_freshness(record, NOW)


# --- actor -----------------------------------------------------------------


def test_actor_present_passes_for_a_named_actor():
    assert check_actor_present(_make_record(actor="bob"), NOW) == PASS


def test_actor_present_fails_for_whitespace():
    assert check_actor_present(_make_record(actor="   "), NOW) == FAIL


# --- amounts ---------------------------------------------------------------


def test_amount_bounds_passes_inside_the_range():
    assert check_amount_bounds(_make_record(amount_cents=250), NOW) == PASS


def test_amount_bounds_flags_negative_amounts():
    record = _make_record(
        amount_cents=-500, results=_declare(("amount_bounds", FAIL))
    )
    report = reconcile(record, NOW)
    assert len(report) == 1


def test_amount_bounds_fails_above_the_ceiling():
    record = _make_record(amount_cents=99_000_000)
    assert check_amount_bounds(record, NOW) == FAIL


# --- approval --------------------------------------------------------------


def test_approval_required_above_the_threshold():
    record = _make_record(amount_cents=2_000_000, approver=None)
    assert check_approval_recorded(record, NOW) == FAIL


def test_approval_satisfied_by_a_named_approver():
    record = _make_record(amount_cents=2_000_000, approver="carol")
    assert check_approval_recorded(record, NOW) == PASS


# --- reconciliation --------------------------------------------------------


def test_reconcile_agrees_when_the_declaration_is_honest():
    record = _make_record(results=_declare(("actor_present", PASS)))
    report = reconcile(record, NOW)
    assert report[0]["agrees"] is True


def test_reconcile_catches_a_lie():
    record = _make_record(
        actor="   ", results=_declare(("actor_present", PASS))
    )
    report = reconcile(record, NOW)
    assert report[0]["agrees"] is False
    assert overall(report) == FAIL


def test_reconcile_rejects_an_unknown_rule():
    record = _make_record(results=_declare(("no_such_rule", PASS)))
    with pytest.raises(VerifierError):
        reconcile(record, NOW)


# --- end to end ------------------------------------------------------------


def test_verify_returns_a_verdict_and_a_report():
    record = _make_record(
        results=_declare(("actor_present", PASS), ("amount_bounds", PASS))
    )
    result = verify(record, NOW)
    assert result["verdict"] == PASS
    assert len(result["report"]) == 2
