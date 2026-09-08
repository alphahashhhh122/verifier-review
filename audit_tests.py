#!/usr/bin/env python3
"""Reproduce the original 15-test mutation audit in isolated directories."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


BASELINE_REF = "dd0e41b2f4b1846d83fcc9945267b4e876abfca1"
VERIFIER = "verifier.py"
TESTS = "test_verifier.py"
TEST_MAP = (
    ("test_freshness_passes_for_a_recent_record", "check_freshness", "direct"),
    ("test_freshness_fails_for_an_old_record", "check_freshness", "direct"),
    ("test_freshness_skips_when_no_timestamp", "check_freshness", "direct"),
    ("test_freshness_rejects_an_unparseable_timestamp", "check_freshness", "direct"),
    ("test_actor_present_passes_for_a_named_actor", "check_actor_present", "direct"),
    ("test_actor_present_fails_for_whitespace", "check_actor_present", "direct"),
    ("test_amount_bounds_passes_inside_the_range", "check_amount_bounds", "direct"),
    ("test_amount_bounds_flags_negative_amounts", "check_amount_bounds", "reconcile -> evaluate_rule -> rule"),
    ("test_amount_bounds_fails_above_the_ceiling", "check_amount_bounds", "direct"),
    ("test_approval_required_above_the_threshold", "check_approval_recorded", "direct"),
    ("test_approval_satisfied_by_a_named_approver", "check_approval_recorded", "direct"),
    ("test_reconcile_agrees_when_the_declaration_is_honest", "reconcile", "direct -> evaluate_rule"),
    ("test_reconcile_catches_a_lie", "reconcile", "direct -> evaluate_rule"),
    ("test_reconcile_rejects_an_unknown_rule", "reconcile", "direct -> evaluate_rule"),
    ("test_verify_returns_a_verdict_and_a_report", "verify", "direct -> reconcile -> evaluate_rule"),
)


class AuditError(RuntimeError):
    pass


def fingerprint(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False}
    data = path.read_bytes()
    return {"exists": True, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def command_text(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv) if os.name == "nt" else " ".join(argv)


def git_show(repo: Path, ref: str, name: str, timeout: float) -> tuple[str, dict[str, object]]:
    argv = ["git", "show", f"{ref}:{name}"]
    try:
        result = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuditError(f"{command_text(argv)} failed: {exc}") from exc
    if result.returncode:
        raise AuditError(f"{command_text(argv)} failed: {result.stderr.strip()}")
    return result.stdout, {
        "argv": argv,
        "command": command_text(argv),
        "cwd": "<repository>",
        "status": "passed",
        "sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
    }


def mutate(source: str, target: str) -> str:
    tree = ast.parse(source, filename=VERIFIER)
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == target]
    if len(matches) != 1:
        raise AuditError(f"expected one {target} function, found {len(matches)}")
    matches[0].body = [ast.copy_location(ast.Pass(), matches[0])]
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


def pytest_status(xml_path: Path, returncode: int) -> str:
    """Use JUnit XML so failures, errors, and collection errors stay distinct."""
    if returncode == 2:
        return "collection_error"
    if returncode not in (0, 1):
        return "runner_error"
    if not xml_path.exists():
        return "runner_error" if returncode != 0 else "collection_error"
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError:
        return "runner_error"
    cases = root.findall(".//testcase")
    if not cases:
        return "collection_error" if returncode != 0 else "runner_error"
    if any(case.find("error") is not None for case in cases):
        return "error"
    if any(case.find("failure") is not None for case in cases):
        return "failure"
    if any(case.find("skipped") is not None for case in cases):
        return "skipped"
    return "passed" if returncode == 0 else "runner_error"


def run_pytest(directory: Path, timeout: float, nodeid: str | None = None) -> dict[str, object]:
    xml_name = "pytest-result.xml"
    argv = [sys.executable, "-m", "pytest", "-q", "--junitxml", xml_name]
    if nodeid:
        argv.append(nodeid)
    env = os.environ.copy()
    env.update({"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        result = subprocess.run(argv, cwd=directory, env=env, capture_output=True, text=True, timeout=timeout, check=False)
        status = pytest_status(directory / xml_name, result.returncode)
        return {
            "argv": argv,
            "command": command_text(argv),
            "cwd": "<isolated-copy>",
            "status": status,
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {"argv": argv, "command": command_text(argv), "cwd": "<isolated-copy>", "status": "timeout", "returncode": None, "stdout": str(exc.stdout or ""), "stderr": str(exc.stderr or "")}
    except OSError as exc:
        return {"argv": argv, "command": command_text(argv), "cwd": "<isolated-copy>", "status": "runner_error", "returncode": None, "error": str(exc)}


def outcome(status: str) -> str:
    if status == "passed":
        return "survives"
    if status in {"failure", "error"}:
        return "killed"
    return "inconclusive"


def write_fixture(directory: Path, verifier: str, tests: str) -> None:
    (directory / VERIFIER).write_text(verifier, encoding="utf-8", newline="\n")
    (directory / TESTS).write_text(tests, encoding="utf-8", newline="\n")


def validate_map(tests: str) -> None:
    tree = ast.parse(tests, filename=TESTS)
    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
    expected = [entry[0] for entry in TEST_MAP]
    if names != expected or len(names) != 15:
        raise AuditError(f"baseline test map mismatch: found {names!r}")


def repository(requested: Path | None) -> Path:
    path = (requested or Path(__file__).resolve().parent).resolve()
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    if result.returncode:
        raise AuditError(f"not a git repository: {path}")
    return Path(result.stdout.strip()).resolve()


def audit(repo: Path, ref: str, timeout: float) -> dict[str, object]:
    before = {name: fingerprint(repo / name) for name in (VERIFIER, TESTS)}
    verifier, verifier_fetch = git_show(repo, ref, VERIFIER, timeout)
    tests, tests_fetch = git_show(repo, ref, TESTS, timeout)
    validate_map(tests)

    with tempfile.TemporaryDirectory(prefix="verifier-audit-control-") as temp:
        control_dir = Path(temp)
        write_fixture(control_dir, verifier, tests)
        control = run_pytest(control_dir, timeout)

    rows: list[dict[str, object]] = []
    if control["status"] == "passed":
        for test, target, call_path in TEST_MAP:
            with tempfile.TemporaryDirectory(prefix=f"verifier-audit-{target}-") as temp:
                mutant_dir = Path(temp)
                write_fixture(mutant_dir, mutate(verifier, target), tests)
                run = run_pytest(mutant_dir, timeout, f"{TESTS}::{test}")
            rows.append({"test": test, "target": target, "call_path": call_path, "run_status": run["status"], "mutation_outcome": outcome(str(run["status"])), "returncode": run["returncode"], "command": run["command"], "argv": run["argv"], "stdout": run.get("stdout", ""), "stderr": run.get("stderr", "")})

    after = {name: fingerprint(repo / name) for name in (VERIFIER, TESTS)}
    survivors = [row["test"] for row in rows if row["mutation_outcome"] == "survives"]
    if control["status"] != "passed":
        status = "baseline_failed"
    elif before != after:
        status = "working_tree_changed"
    elif any(row["mutation_outcome"] == "inconclusive" for row in rows):
        status = "inconclusive"
    else:
        status = "complete"
    return {
        "schema_version": 1,
        "baseline_ref": ref,
        "source_files": {"verifier": VERIFIER, "tests": TESTS},
        "pytest_environment": {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        "retrieval": [verifier_fetch, tests_fetch],
        "baseline_control": control,
        "mapped_tests": rows,
        "summary": {"audit_status": status, "survivors": survivors, "killed": sum(row["mutation_outcome"] == "killed" for row in rows), "inconclusive": sum(row["mutation_outcome"] == "inconclusive" for row in rows), "working_tree_unchanged": before == after, "working_tree_before": before, "working_tree_after": after, "expected_survivor": "test_amount_bounds_flags_negative_amounts"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--baseline-ref", default=BASELINE_REF)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        document = audit(repository(args.repo), args.baseline_ref, args.timeout)
    except (AuditError, ValueError) as exc:
        print(f"audit_tests.py: error: {exc}", file=sys.stderr)
        return 1
    if args.output:
        output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    summary = document["summary"]
    print(f"Baseline control: {document['baseline_control']['status']}")
    print(f"Mapped audit: {summary['killed']} killed, {len(summary['survivors'])} survived, {summary['inconclusive']} inconclusive")
    if summary["survivors"]:
        print("Survivors: " + ", ".join(summary["survivors"]))
    print(f"Audit status: {summary['audit_status']}")
    return 0 if summary["audit_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
