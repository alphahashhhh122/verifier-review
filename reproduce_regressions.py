"""Run the same regression tests against the baseline and current implementation."""

import os
import pathlib
import subprocess
import sys
import tempfile

BASELINE = "dd0e41b2f4b1846d83fcc9945267b4e876abfca1"
ROOT = pathlib.Path(__file__).resolve().parent


def run(source, label):
    with tempfile.TemporaryDirectory(prefix="verifier-regressions-") as directory:
        path = pathlib.Path(directory)
        (path / "verifier.py").write_bytes(source)
        (path / "test_regressions.py").write_bytes((ROOT / "test_regressions.py").read_bytes())
        env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        print(f"\n{label}: python -m pytest -q --tb=short test_regressions.py", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider", "test_regressions.py"],
            cwd=path, env=env, timeout=120,
        )
        return result.returncode


def main():
    original = subprocess.run(
        ["git", "show", f"{BASELINE}:verifier.py"], cwd=ROOT, capture_output=True, check=True,
    ).stdout
    before = run(original, "SUPPLIED BASELINE (expected test failures)")
    after = run((ROOT / "verifier.py").read_bytes(), "CURRENT IMPLEMENTATION (expected success)")
    print(f"\nBaseline exit={before}; current exit={after}")
    if before != 1 or after != 0:
        print("Unexpected result: inspect output; collection or infrastructure errors do not count as proof.")
        return 1
    print("Confirmed: unchanged regression tests fail on baseline and pass on current code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
