#!/usr/bin/env python3
"""Local, hash-linked JUnit evidence. Standard library only; no network calls."""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET

VERSION = 1
MAX_REPORT = 32 * 1024 * 1024
BAD = {"failure", "error"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_report(path):
    path = Path(path)
    if path.stat().st_size > MAX_REPORT:
        raise ValueError("Report exceeds 32 MiB; split by test shard before analysis")
    raw = path.read_bytes()
    raw.decode("utf-8-sig")  # Intentionally support UTF-8 only; reject UTF-16 DTD bypasses.
    if b"\x00" in raw:
        raise ValueError("NUL bytes / non-UTF-8 XML are unsupported")
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD/entity declarations are unsupported")
    root = ET.fromstring(raw)
    if local(root.tag) not in {"testsuites", "testsuite"}:
        raise ValueError("Expected JUnit testsuites or testsuite root")
    cases, issues, consumed = [], [], set()

    def visit(node, suites=()):
        tag = local(node.tag)
        if tag == "testsuite":
            suites = suites + (node.get("name", ""),)
        if tag == "testcase":
            consumed.add(id(node))
            name = node.get("name", "")
            identity = {"suite": list(suites), "class": node.get("classname", ""),
                        "file": node.get("file", ""), "name": name}
            outcomes = [c for c in node if local(c.tag) in BAD | {"skipped"}]
            retries = [c for c in node if local(c.tag) in
                       {"flakyFailure", "flakyError", "rerunFailure", "rerunError"}]
            kinds = {local(c.tag) for c in outcomes}
            outcome_tags = BAD | {"skipped", "flakyFailure", "flakyError", "rerunFailure", "rerunError"}
            nested_outcomes = any(local(desc.tag) in outcome_tags
                                  for child in node for desc in child.iter() if desc is not child)
            status_attr, result_attr = node.get("status", "").lower(), node.get("result", "").lower()
            disabled = status_attr in {"notrun", "disabled", "skipped"} or result_attr in {"suppressed", "skipped"}
            unsupported_outcome = (status_attr not in {"", "run", "pass", "passed", "notrun", "disabled", "skipped"}
                                   or result_attr not in {"", "completed", "pass", "passed", "suppressed", "skipped"})
            if not name:
                issues.append("testcase without a name")
            if retries or nested_outcomes or unsupported_outcome or ((disabled or "skipped" in kinds) and kinds & BAD):
                status = "ambiguous"
                issues.append("retry or contradictory outcome: " + name)
            elif "error" in kinds:
                status = "error"
            elif "failure" in kinds:
                status = "failure"
            elif "skipped" in kinds or disabled:
                status = "skipped"
            else:
                status = "pass"
            errors = [{"kind": local(c.tag), "type": c.get("type", ""),
                       "message": c.get("message", ""),
                       "text": "".join(c.itertext()).replace("\r\n", "\n")}
                      for c in outcomes if local(c.tag) in BAD]
            skipped = [{"message": c.get("message", ""), "text": "".join(c.itertext())}
                       for c in outcomes if local(c.tag) == "skipped"]
            cases.append({"id": digest(encoded(identity)), "identity": identity,
                          "label": " / ".join((*suites, identity["class"], name)),
                          "status": status, "signature": digest(encoded(errors)) if errors else None,
                          "errors": errors, "skip_details": skipped})
        for child in node:
            if local(child.tag) in {"testsuites", "testsuite", "testcase"}:
                visit(child, suites)
        # Validate declared counts against actual descendants, not just the root.
        if tag in {"testsuite", "testsuites"}:
            descendants = [n for n in node.iter() if local(n.tag) == "testcase"]
            observed = {"tests": len(descendants)}
            for key, kind in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
                observed[key] = sum(any(local(c.tag) == kind for c in n) for n in descendants)
            for key, actual in observed.items():
                if key in node.attrib:
                    try:
                        if int(node.get(key)) != actual:
                            issues.append(f"declared {key} mismatch in {node.get('name', tag)}")
                    except ValueError:
                        issues.append(f"invalid {key} count")
            if any(local(c.tag) in BAD for c in node):
                issues.append("suite-level failure/error is not a testcase")

    visit(root)
    parents = {id(child): parent for parent in root.iter() for child in parent}
    for node in root.iter():
        kind = local(node.tag)
        parent = parents.get(id(node))
        if kind == "testcase" and (id(node) not in consumed or parent is None or local(parent.tag) != "testsuite"):
            issues.append("unsupported testcase nesting; report cannot be completely interpreted")
        if kind in BAD | {"skipped", "flakyFailure", "flakyError", "rerunFailure", "rerunError"}:
            if parent is None or local(parent.tag) != "testcase":
                issues.append("unsupported outcome nesting")
    duplicates = [k for k, n in collections.Counter(c["id"] for c in cases).items() if n > 1]
    if duplicates:
        issues.append(f"{len(duplicates)} duplicate test identities; do not collapse retries/shards")
    if not cases:
        issues.append("empty report: no tests observed")
    return {"sha256": digest(raw), "bytes": len(raw), "cases": cases,
            "counts": dict(collections.Counter(c["status"] for c in cases)),
            "issues": sorted(set(issues))}


def git_state(cwd):
    def git(*argv):
        return subprocess.check_output(["git", "-C", str(cwd), *argv], stderr=subprocess.DEVNULL)
    try:
        root = Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve()
        head = git("rev-parse", "HEAD").decode().strip()
        files = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]).split(b"\0")
        inventory, limitations = [], []
        total = 0
        for raw in sorted(set(files)):
            if not raw:
                continue
            relative = os.fsdecode(raw)
            p = root / relative
            if p.is_symlink():
                limitations.append("symlink inputs are not recursively fingerprinted")
                value = [relative, "symlink", os.readlink(p)]
            elif p.is_file():
                size = p.stat().st_size
                total += size
                if total > 128 * 1024 * 1024:
                    limitations.append("source fingerprint exceeds 128 MiB")
                    break
                value = [relative, "file", p.stat().st_mode & 0o777, file_digest(p)]
            else:
                value = [relative, "missing-or-submodule"]
                if p.is_dir():
                    limitations.append("submodule contents are not fingerprinted")
            inventory.append(value)
        # Include index changes as well as file content, without storing source text.
        state = {"head": head, "files": inventory, "index": digest(git("diff", "--cached", "--binary"))}
        return {"head": head, "fingerprint": digest(encoded(state)), "files": len(inventory),
                "limitations": sorted(set(limitations)), "root": str(root)}
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        return {"head": None, "fingerprint": None, "limitations": ["Git source identity unavailable"],
                "error": type(exc).__name__}


def capture(args):
    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd or not any("{junit}" in a for a in cmd):
        raise ValueError("Command must contain a literal {junit} report-path placeholder")
    cwd, out = Path(args.cwd).resolve(), Path(args.out).resolve()
    if not cwd.is_dir():
        raise ValueError("cwd is not a directory")
    source_before = git_state(cwd)
    if source_before.get("root") and out.is_relative_to(Path(source_before["root"])):
        raise ValueError("Put evidence outside the source repository to avoid fingerprint contamination")
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = out / "junit.xml"
    actual = [a.replace("{junit}", str(report)) for a in cmd]
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    timed_out = False
    with open(out / "console.log", "xb") as stream:
        os.chmod(out / "console.log", 0o600)
        process = subprocess.Popen(actual, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=os.name == "posix", shell=False)
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            code = process.wait()
    source_after = git_state(cwd)
    report_hash = file_digest(report) if report.is_file() else None
    if report.is_file():
        os.chmod(report, 0o600)
    receipt = {"version": VERSION, "kind": "captured", "project": args.project,
               "scope": args.scope, "environment": args.environment,
               "environment_note": "caller-declared; dependencies/services/ignored files not fingerprinted",
               "command_template": cmd, "cwd": str(cwd),
               "cwd_relative": str(cwd.relative_to(Path(source_before["root"]))) if source_before.get("root") else None,
               "started": started,
               "ended": dt.datetime.now(dt.timezone.utc).isoformat(), "returncode": code,
               "timed_out": timed_out, "source_before": source_before, "source_after": source_after,
               "junit_sha256": report_hash, "console_sha256": file_digest(out / "console.log")}
    write_private(out / "receipt.json", json.dumps(receipt, indent=2).encode())
    print(json.dumps({"receipt": str(out / "receipt.json"), "test_returncode": code,
                      "report_created": bool(report_hash), "timed_out": timed_out}))
    return 0 if code == 0 else 1


def load_run(directory):
    directory = Path(directory)
    receipt = json.loads((directory / "receipt.json").read_text())
    if receipt.get("version") != VERSION or receipt.get("kind") != "captured":
        raise ValueError("Unsupported receipt format")
    report = parse_report(directory / "junit.xml")
    issues = list(report["issues"])
    try:
        started = dt.datetime.fromisoformat(receipt["started"])
        ended = dt.datetime.fromisoformat(receipt["ended"])
        if started.tzinfo is None or ended.tzinfo is None or ended < started:
            raise ValueError("invalid time interval")
    except (KeyError, TypeError, ValueError):
        issues.append("missing or invalid timezone-aware run timestamps")
    if report["sha256"] != receipt.get("junit_sha256"):
        issues.append("report hash changed after capture")
    if file_digest(directory / "console.log") != receipt.get("console_sha256"):
        issues.append("console log hash changed after capture")
    before, after = receipt.get("source_before", {}), receipt.get("source_after", {})
    if not before.get("fingerprint") or before.get("fingerprint") != after.get("fingerprint"):
        issues.append("source identity unavailable or changed during the run")
    issues.extend(before.get("limitations", []))
    issues.extend(after.get("limitations", []))
    failed = sum(report["counts"].get(k, 0) for k in BAD)
    rc = receipt.get("returncode")
    if receipt.get("timed_out") or rc not in {0, 1}:
        issues.append("run interrupted or has unsupported process exit code")
    elif bool(failed) != bool(rc):
        issues.append("process exit code and test outcomes disagree")
    return receipt, report, sorted(set(issues))


def compare(before_dir, after_dir):
    before, old, old_issues = load_run(before_dir)
    after, new, new_issues = load_run(after_dir)
    blockers = ["before: " + x for x in old_issues] + ["after: " + x for x in new_issues]
    for key in ("project", "scope", "environment", "command_template", "cwd_relative"):
        if not before.get(key) or before.get(key) != after.get(key):
            blockers.append(key + " differs or is missing")
    try:
        ended = dt.datetime.fromisoformat(before["ended"])
        started = dt.datetime.fromisoformat(after["started"])
        if ended.tzinfo is None or started.tzinfo is None or ended > started:
            blockers.append("baseline was not completed before candidate started")
    except (KeyError, TypeError, ValueError):
        blockers.append("baseline/candidate chronology is unavailable")
    old_cases = {c["id"]: c for c in old["cases"]}
    new_cases = {c["id"]: c for c in new["cases"]}
    changes = collections.defaultdict(list)
    for ident in sorted(old_cases.keys() | new_cases.keys()):
        a, b = old_cases.get(ident), new_cases.get(ident)
        category = None
        if b is None:
            category = "missing_not_verified" if a["status"] in BAD else "other_missing"
        elif b["status"] == "ambiguous":
            category = "ambiguous"
        elif b["status"] in BAD:
            if a is None or a["status"] not in BAD:
                category = "new_failure"
            elif a["status"] != b["status"] or a["signature"] != b["signature"]:
                category = "changed_failure"
            else:
                category = "same_failure_observed_before" if not blockers else "same_signature_unverified"
        elif a and a["status"] in BAD:
            category = ("now_passing" if not blockers else "reported_passing_unverified") if b["status"] == "pass" else "skipped_not_verified"
        elif b["status"] == "skipped" and (a is None or a["status"] != "skipped"):
            category = "newly_skipped"
        elif a is None:
            category = "new_passing"
        if category:
            item = {"id": ident, "test": (b or a)["label"],
                    "before": a["status"] if a else "absent", "after": b["status"] if b else "absent"}
            if a and a["signature"]:
                item["before_signature"] = a["signature"]
            if b and b["signature"]:
                item["after_signature"] = b["signature"]
                item["message"] = " | ".join(e["message"] for e in b["errors"])[:220]
            changes[category].append(item)
    return {"comparable": not blockers, "blockers": blockers,
            "before_counts": old["counts"], "after_counts": new["counts"],
            "categories": dict(changes), "before_source": before["source_before"],
            "after_source": after["source_before"],
            "limits": ["Observed before is not proof of causality or permission to ignore it.",
                       "Environment and test scope labels are caller-declared, not attested.",
                       "Exact signatures deliberately retain numbers/paths; noisy changes need inspection.",
                       "Local hashes detect accidental artifact changes; receipts are not signed."]}


def markdown(result, limit=12):
    lines = ["# Failure evidence", "", "Comparable receipts: " + ("yes" if result["comparable"] else "NO"),
             f"Before: {result['before_counts']}; after: {result['after_counts']}", ""]
    if result["blockers"]:
        lines += ["Do not classify any failure as pre-existing from this comparison."]
        lines += ["- " + json.dumps(b, ensure_ascii=False) for b in result["blockers"]]
    for category, items in sorted(result["categories"].items()):
        lines += ["", f"## {category}: {len(items)}"]
        for item in items[:limit]:
            # Keep untrusted test output visibly data, on one line, never executable.
            name = json.dumps(item["test"], ensure_ascii=False)
            lines.append(f"- {item['id'][:12]} {name}: {item['before']} -> {item['after']}")
        if len(items) > limit:
            lines.append(f"- {len(items)-limit} more; use --json for the complete list.")
    lines += ["", *["- " + s for s in result["limits"]]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    cap = sub.add_parser("capture", help="Run an explicitly authorized command once and bind its report")
    cap.add_argument("--out", required=True)
    cap.add_argument("--cwd", default=".")
    for arg in ("project", "scope", "environment"):
        cap.add_argument("--" + arg, required=True)
    cap.add_argument("--timeout", type=float, default=600)
    cap.add_argument("command", nargs=argparse.REMAINDER)
    comp = sub.add_parser("compare", help="Read-only comparison; does not rerun tests")
    comp.add_argument("before")
    comp.add_argument("after")
    comp.add_argument("--json", action="store_true")
    inspect = sub.add_parser("inspect", help="Inspect an existing report without claiming provenance")
    inspect.add_argument("report")
    inspect.add_argument("--id", help="Full ID or unique prefix, to recover one failure detail")
    args = parser.parse_args(argv)
    try:
        if args.action == "capture":
            return capture(args)
        if args.action == "compare":
            result = compare(args.before, args.after)
            print(json.dumps(result, indent=2) if args.json else markdown(result), end="\n" if args.json else "")
            return 0 if result["comparable"] else 2
        result = parse_report(args.report)
        if args.id:
            matches = [c for c in result["cases"] if c["id"].startswith(args.id)]
            if len(matches) != 1:
                raise ValueError("ID prefix must identify exactly one test")
            print(json.dumps(matches[0], indent=2))
        else:
            result["cases"] = [{k: v for k, v in c.items() if k != "errors"}
                               for c in result["cases"] if c["status"] != "pass"]
            print(json.dumps(result, indent=2))
        return 0 if not result["issues"] else 2
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        print("Evidence unavailable: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
