#!/usr/bin/env python3
"""Reproducible fixture comparison, not a model-performance or production benchmark."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/preexisting.py"
spec = importlib.util.spec_from_file_location("preexisting", SCRIPT)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
parser = argparse.ArgumentParser()
parser.add_argument("--out", help="New output directory; defaults to a temporary directory")
args = parser.parse_args()
out = Path(args.out).resolve() if args.out else Path(tempfile.mkdtemp(prefix="preexisting-proof-eval-"))
if args.out:
    out.mkdir(parents=True, exist_ok=False)
repo = out / "repo"
repo.mkdir()
shutil.copyfile(ROOT / "tests/fixtures/runner.py", repo / "runner.py")
(repo / ".gitignore").write_text("__pycache__/\n")


def git(*argv):
    subprocess.run(["git", "-C", str(repo), *argv], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def state(which):
    value = {"stable": 1, "changed": 1 if which == "before" else 2,
             "healed": 1 if which == "before" else 0, "skip": which == "after",
             "include_missing": which == "before",
             "regressions": {} if which == "before" else {"0": 1, "1": 1, "2": 1}}
    (repo / "state.json").write_text(json.dumps(value, indent=2))


state("before")
git("init", "-q")
git("config", "user.name", "Local fixture")
git("config", "user.email", "fixture@example.invalid")
git("add", ".")
git("commit", "-qm", "synthetic baseline")
for which in ("before", "after"):
    state(which)
    command = [sys.executable, str(SCRIPT), "capture", "--out", str(out / which), "--cwd", str(repo),
               "--project", "synthetic-app", "--scope", "all-unittest-checks",
               "--environment", f"Python {sys.version_info.major}.{sys.version_info.minor}; stdlib; no services",
               "--", sys.executable, "runner.py", "{junit}"]
    process = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 1:
        raise RuntimeError(process.stdout + process.stderr)
result = p.compare(out / "before", out / "after")
assert result["comparable"], result["blockers"]
expected = {"new_failure": 3, "changed_failure": 1, "same_failure_observed_before": 1,
            "now_passing": 1, "skipped_not_verified": 1, "missing_not_verified": 1}
observed = {k: len(v) for k, v in result["categories"].items()}
assert observed == expected, observed
old = p.parse_report(out / "before/junit.xml")
new = p.parse_report(out / "after/junit.xml")
raw_bytes = old["bytes"] + new["bytes"]
handoff = p.markdown(result)
old_ids = {c["id"] for c in old["cases"] if c["status"] in p.BAD}
new_ids = {c["id"] for c in new["cases"] if c["status"] in p.BAD}
metrics = {"fixture": "305 -> 304 actually executed synthetic unittest checks; five failures in both runs",
           "baseline_count_only_new_failures": max(0, len(new_ids) - len(old_ids)),
           "baseline_failed_id_set_new_failures": len(new_ids - old_ids),
           "signature_aware_new_or_changed": observed["new_failure"] + observed["changed_failure"],
           "lost_verification_detected": observed["skipped_not_verified"] + observed["missing_not_verified"],
           "expected_categories": expected, "observed_categories": observed,
           "raw_report_bytes": raw_bytes, "compact_handoff_bytes": len(handoff.encode()),
           "handoff_byte_reduction_percent": round(100 * (1 - len(handoff.encode()) / raw_bytes), 2),
           "comparison_test_reruns": 0, "evidence_directory": str(out),
           "limitations": ["Synthetic fixture, not user field validation", "Byte reduction, not tokens or wall-time savings",
                           "No agent A/B trial; simple scripted baselines", "Environment labels are declarations"]}
(out / "comparison.json").write_text(json.dumps(result, indent=2))
(out / "handoff.md").write_text(handoff)
(out / "metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics, indent=2))
