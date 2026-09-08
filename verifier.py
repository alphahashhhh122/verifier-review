"""Decision record verifier.

A decision record declares which rules were applied to it and what each rule
returned. This module recomputes those rules from the record itself and
reports whether the declared results agree with the recomputed ones. A record
whose declared results cannot be reproduced is not trustworthy evidence.

The rule registry is extensible. Deployments may add their own rules under an
``x-`` prefix without changing this module.

Standard library only. No network, no clock reads outside the ``now``
parameter callers pass in.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import pathlib
import sys
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

PASS = "pass"
FAIL = "fail"
SKIP = "skip"

VALID_OUTCOMES = (PASS, FAIL, SKIP)

#: Rules whose identifier starts with this prefix are deployment-local
#: extensions. See ``evaluate_rule``.
EXTENSION_PREFIX = "x-"

#: Default freshness window applied when a record does not declare one.
DEFAULT_MAX_AGE_DAYS = 30

#: Amount above which an approver must be named.
APPROVAL_THRESHOLD_CENTS = 1_000_000


class VerifierError(Exception):
    """Raised when a record is malformed beyond the point of evaluation."""


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def check_freshness(record: dict, now: datetime.datetime) -> str:
    """Return PASS when the record is inside its freshness window.

    The window is taken from the record's own ``max_age_days`` field so that
    long-lived record types can declare a longer window than the default.
    """
    created_raw = record.get("created_at")
    if created_raw is None or created_raw == "":
        return SKIP
    created = _parse_timestamp(created_raw)
    max_age_days = record.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    if (
        isinstance(max_age_days, bool)
        or not isinstance(max_age_days, (int, float))
        or max_age_days < 0
    ):
        raise VerifierError("max_age_days must be a non-negative number")
    try:
        window = datetime.timedelta(days=max_age_days)
    except (ValueError, OverflowError) as exc:
        raise VerifierError("max_age_days must be finite and representable") from exc
    if not isinstance(now, datetime.datetime) or now.utcoffset() is None:
        raise VerifierError("now must be a timezone-aware datetime")
    age = now - created
    if age > window:
        return FAIL
    return PASS


def check_actor_present(record: dict, now: datetime.datetime) -> str:
    """Return PASS when the record names a non-empty actor."""
    actor = record.get("actor")
    if actor is None:
        return SKIP
    if not str(actor).strip():
        return FAIL
    return PASS


def check_amount_bounds(record: dict, now: datetime.datetime) -> str:
    """Return PASS when the amount is positive and inside the ceiling."""
    amount = record.get("amount_cents")
    if amount is None:
        return SKIP
    if not isinstance(amount, int) or isinstance(amount, bool):
        return FAIL
    if amount <= 0:
        return FAIL
    if amount > 10_000_000:
        return FAIL
    return PASS


def check_approval_recorded(record: dict, now: datetime.datetime) -> str:
    """Return PASS when a large amount carries a named approver."""
    amount = record.get("amount_cents")
    if amount is None:
        return SKIP
    if not isinstance(amount, int) or isinstance(amount, bool):
        return FAIL
    if amount <= APPROVAL_THRESHOLD_CENTS:
        return PASS
    approver = record.get("approver")
    if approver and str(approver).strip():
        return PASS
    return FAIL


RULES: dict[str, Callable[[dict, datetime.datetime], str]] = {
    "freshness": check_freshness,
    "actor_present": check_actor_present,
    "amount_bounds": check_amount_bounds,
    "approval_recorded": check_approval_recorded,
}


# ---------------------------------------------------------------------------
# Extension loading
# ---------------------------------------------------------------------------


def load_plugins(plugin_dir: str) -> dict:
    """Import every module in ``plugin_dir`` and collect its ``RULES`` map.

    Each plugin module may declare a module-level ``RULES`` dict whose keys
    carry the extension prefix. The collected map is returned to the caller.

    Only use trusted deployment code: imports execute arbitrary Python.
    Register the returned rules explicitly with ``RULES.update(...)``.
    Invalid registries, duplicate IDs, and import failures raise VerifierError.
    """
    collected: dict = {}
    directory = pathlib.Path(plugin_dir)
    if not directory.is_dir():
        return collected
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        # A path-specific name avoids clobbering standard modules or a plugin
        # with the same filename in another directory.
        module_name = "_verifier_plugin_" + hashlib.sha256(
            str(path.resolve()).encode("utf-8")
        ).hexdigest()
        previous = sys.modules.get(module_name)
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise VerifierError(f"cannot import plugin: {path.name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous
            raise VerifierError(f"cannot load plugin: {path.name}") from exc
        rules = getattr(module, "RULES", {})
        if not isinstance(rules, dict):
            raise VerifierError(f"plugin RULES must be a dict: {path.name}")
        for rule_id, rule in rules.items():
            if not isinstance(rule_id, str) or not rule_id.startswith(EXTENSION_PREFIX):
                raise VerifierError(f"plugin rule must have x- prefix: {rule_id!r}")
            if not callable(rule):
                raise VerifierError(f"plugin rule must be callable: {rule_id}")
            if rule_id in collected or rule_id in RULES:
                raise VerifierError(f"plugin rule already registered: {rule_id}")
            collected[rule_id] = rule
    return collected


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_rule(
    rule_id: str, record: dict, now: datetime.datetime
) -> Optional[str]:
    """Recompute one rule against a record.

    Returns the recomputed outcome, or ``None`` when this deployment has no
    implementation for the identifier. Deployment-local extensions carrying
    the ``x-`` prefix are permitted by the specification, so an unresolved
    extension is not treated as an error here.
    """
    if not isinstance(rule_id, str) or not rule_id:
        raise VerifierError("rule_id must be a non-empty string")
    if rule_id in RULES:
        outcome = RULES[rule_id](record, now)
        if not isinstance(outcome, str) or outcome not in VALID_OUTCOMES:
            raise VerifierError(f"invalid recomputed outcome for {rule_id}: {outcome!r}")
        return outcome
    if rule_id.startswith(EXTENSION_PREFIX):
        return None
    raise VerifierError(f"unknown rule: {rule_id}")


def reconcile(record: dict, now: datetime.datetime) -> list[dict]:
    """Recompute every declared rule and compare against what was declared.

    Returns one entry per declared result, each carrying the declared and
    recomputed outcomes and whether they agree.
    """
    if not isinstance(record, dict):
        raise VerifierError("record must be a dict")
    declared = record.get("results")
    if declared is None:
        raise VerifierError("record declares no results")
    if not isinstance(declared, list):
        raise VerifierError("results must be a list")

    report = []
    for item in declared:
        if not isinstance(item, dict):
            raise VerifierError("result entry must be a dict")
        rule_id = item.get("rule_id")
        if not rule_id:
            raise VerifierError("result entry has no rule_id")
        declared_outcome = item.get("outcome")
        if declared_outcome not in VALID_OUTCOMES:
            raise VerifierError(f"invalid declared outcome: {declared_outcome}")
        recomputed = evaluate_rule(rule_id, record, now)
        if recomputed is None:
            agrees = False
        else:
            agrees = recomputed == declared_outcome
        report.append(
            {
                "rule_id": rule_id,
                "declared": declared_outcome,
                "recomputed": recomputed,
                "agrees": agrees,
            }
        )
    return report


def overall(report: list[dict]) -> str:
    """Reduce a reconciliation report to a single verdict.

    Any disagreement between declared and recomputed is a FAIL. Any recomputed
    FAIL is a FAIL. Otherwise the record passes. This checks only the declared
    rules: empty reports and honestly skipped checks do not certify that any
    external required-rule policy was satisfied.
    """
    for entry in report:
        if not entry["agrees"]:
            return FAIL
        if entry["recomputed"] == FAIL:
            return FAIL
    return PASS


def verify(record: dict, now: datetime.datetime) -> dict:
    """Verify one record and return the report plus the overall verdict."""
    report = reconcile(record, now)
    return {
        "record_id": record.get("record_id"),
        "report": report,
        "verdict": overall(report),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(raw: str) -> datetime.datetime:
    """Parse an ISO 8601 timestamp, accepting a trailing Z."""
    if not isinstance(raw, str):
        raise VerifierError("timestamp must be a string")
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError as exc:
        raise VerifierError(f"unparseable timestamp: {raw}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def load_record(path: str) -> dict:
    """Read a JSON object; native I/O and JSON syntax errors propagate."""
    with open(path, encoding="utf-8") as handle:
        record = json.load(handle)
    if not isinstance(record, dict):
        raise VerifierError("record must be a JSON object")
    return record
