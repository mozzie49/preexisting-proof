#!/usr/bin/env python3
"""Bounded publication hygiene: explicit source allowlist, no raw run artifacts."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    ".github/workflows/ci.yml", ".gitignore", "LICENSE", "README.md", "SKILL.md",
    "scripts/preexisting.py", "scripts/release_check.py",
    "references/format.md", "references/evidence.md",
    "tests/test_preexisting.py", "tests/fixtures/runner.py",
    "eval/benchmark.py", "eval/independent-review.md", "eval/synthetic-results.json",
    "eval/real-runner-results.json",
}
FORBIDDEN_ROOTS = ("/" "workspace/shared/", "/" "workspace/scratch/", "/" "home/agent/")
SECRET_PATTERNS = (
    r"AKIA[0-9A-Z]{16}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
)
actual, errors = set(), []
for path in ROOT.rglob("*"):
    rel = path.relative_to(ROOT)
    if any(part in {".git", "__pycache__"} for part in rel.parts):
        continue
    if not path.is_file():
        continue
    name = rel.as_posix()
    actual.add(name)
    if name not in ALLOWED:
        errors.append("unexpected file: " + name)
        continue
    text = path.read_text(encoding="utf-8")
    if any(root in text for root in FORBIDDEN_ROOTS):
        errors.append("private workspace path: " + name)
    if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
        errors.append("credential-like content: " + name)
errors.extend("missing file: " + name for name in sorted(ALLOWED - actual))
if errors:
    raise SystemExit("Release check failed:\n" + "\n".join(errors))
print(f"Release check passed: {len(actual)} allowlisted files; no raw reports, logs, source checkout or detected secret/path patterns")
