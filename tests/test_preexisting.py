import contextlib
import argparse
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("preexisting", ROOT / "scripts/preexisting.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ParsingTests(unittest.TestCase):
    def parse(self, xml):
        with tempfile.TemporaryDirectory() as temp:
            f = Path(temp) / "r.xml"
            f.write_bytes(xml if isinstance(xml, bytes) else xml.encode())
            return p.parse_report(f)

    def test_nested_namespaced_identity(self):
        parsed = self.parse('<testsuites xmlns="urn:junit"><testsuite name="a"><testsuite name="b"><testcase classname="C" name="x"/></testsuite></testsuite></testsuites>')
        self.assertEqual(parsed["cases"][0]["identity"]["suite"], ["a", "b"])
        self.assertFalse(parsed["issues"])

    def test_duplicate_is_blocker(self):
        parsed = self.parse('<testsuite><testcase name="x"/><testcase name="x"/></testsuite>')
        self.assertTrue(any("duplicate" in x for x in parsed["issues"]))

    def test_parameters_preserved(self):
        parsed = self.parse('<testsuite><testcase name="x[0]"/><testcase name="x[1]"/></testsuite>')
        self.assertNotEqual(parsed["cases"][0]["id"], parsed["cases"][1]["id"])

    def test_failure_numbers_not_normalized(self):
        a = self.parse('<testsuite><testcase name="x"><failure>expected 1 got 2</failure></testcase></testsuite>')
        b = self.parse('<testsuite><testcase name="x"><failure>expected 1 got 3</failure></testcase></testsuite>')
        self.assertNotEqual(a["cases"][0]["signature"], b["cases"][0]["signature"])

    def test_retry_is_ambiguous(self):
        a = self.parse('<testsuite><testcase name="x"><flakyFailure>old error</flakyFailure></testcase></testsuite>')
        self.assertEqual(a["cases"][0]["status"], "ambiguous")
        self.assertTrue(a["issues"])

    def test_counts_disagree(self):
        a = self.parse('<testsuite tests="9" failures="0"><testcase name="x"><failure>bad</failure></testcase></testsuite>')
        self.assertEqual(len(a["issues"]), 2)

    def test_disabled_case_not_green(self):
        a = self.parse('<testsuite><testcase name="x" status="notrun" result="suppressed"/></testsuite>')
        self.assertEqual(a["cases"][0]["status"], "skipped")

    def test_skip_reason_recoverable(self):
        a = self.parse('<testsuite><testcase name="x"><skipped message="disabled">reason detail</skipped></testcase></testsuite>')
        self.assertEqual(a["cases"][0]["skip_details"], [{"message": "disabled", "text": "reason detail"}])

    def test_unknown_result_is_not_green(self):
        a = self.parse('<testsuite><testcase name="x" result="failed"/></testsuite>')
        self.assertEqual(a["cases"][0]["status"], "ambiguous")
        self.assertTrue(a["issues"])

    def test_unconsumed_testcase_blocks(self):
        a = self.parse('<testsuite tests="2" failures="2"><testcase name="x"><failure/></testcase><wrapper><testcase name="new"><failure/></testcase></wrapper></testsuite>')
        self.assertTrue(any("nesting" in x for x in a["issues"]))

    def test_hidden_failure_blocks(self):
        a = self.parse('<testsuite><testcase name="x"><wrapper><failure/></wrapper></testcase></testsuite>')
        self.assertTrue(any("outcome nesting" in x for x in a["issues"]))
        self.assertEqual(a["cases"][0]["status"], "ambiguous")

    def test_suite_level_error(self):
        a = self.parse('<testsuite><error>collection failed</error></testsuite>')
        self.assertTrue(any("suite-level" in x for x in a["issues"]))

    def test_dtd_rejected(self):
        with self.assertRaises(ValueError):
            self.parse('<!DOCTYPE x [<!ENTITY y "payload">]><testsuite/>')

    def test_utf16_rejected(self):
        with self.assertRaises(ValueError):
            self.parse('<?xml version="1.0" encoding="utf-16"?><testsuite/>'.encode("utf-16"))


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def receipt(self, name, cases, **overrides):
        directory = self.root / name
        directory.mkdir()
        report = ('<testsuite name="s">' + cases + '</testsuite>').encode()
        p.write_private(directory / "junit.xml", report)
        p.write_private(directory / "console.log", b"recorded output")
        r = {"version": 1, "kind": "captured", "project": "app", "scope": "unit", "environment": "py3",
             "command_template": ["python", "runner", "{junit}"], "cwd_relative": ".",
             "started": "2026-10-22T08:00:00+00:00" if name == "before" else "2026-10-22T08:01:00+00:00",
             "ended": "2026-10-22T08:00:30+00:00" if name == "before" else "2026-10-22T08:01:30+00:00",
             "source_before": {"head": "abc", "fingerprint": "a", "limitations": []},
             "source_after": {"head": "abc", "fingerprint": "a", "limitations": []},
             "returncode": int("<failure" in cases or "<error" in cases), "timed_out": False,
             "junit_sha256": p.digest(report), "console_sha256": p.digest(b"recorded output")}
        r.update(overrides)
        p.write_private(directory / "receipt.json", json.dumps(r).encode())
        return directory

    def test_exact_failure_observed_before(self):
        cases = '<testcase name="x"><failure message="bad">assert 1==2</failure></testcase>'
        a, b = self.receipt("before", cases), self.receipt("after", cases)
        result = p.compare(a, b)
        self.assertTrue(result["comparable"])
        self.assertEqual(len(result["categories"]["same_failure_observed_before"]), 1)

    def test_changed_same_id_is_not_known(self):
        a = self.receipt("before", '<testcase name="x"><failure>1</failure></testcase>')
        b = self.receipt("after", '<testcase name="x"><failure>2</failure></testcase>')
        self.assertIn("changed_failure", p.compare(a, b)["categories"])

    def test_skipped_and_missing_not_fixed(self):
        a = self.receipt("before", '<testcase name="x"><failure>bad</failure></testcase><testcase name="y"><failure>bad</failure></testcase>')
        b = self.receipt("after", '<testcase name="x"><skipped/></testcase>')
        categories = p.compare(a, b)["categories"]
        self.assertIn("skipped_not_verified", categories)
        self.assertIn("missing_not_verified", categories)
        self.assertNotIn("now_passing", categories)

    def test_environment_mismatch_withholds_preexisting(self):
        cases = '<testcase name="x"><failure>bad</failure></testcase>'
        a, b = self.receipt("before", cases), self.receipt("after", cases, environment="different")
        result = p.compare(a, b)
        self.assertFalse(result["comparable"])
        self.assertIn("same_signature_unverified", result["categories"])

    def test_command_mismatch(self):
        cases = '<testcase name="x"/>'
        a, b = self.receipt("before", cases), self.receipt("after", cases, command_template=["other"])
        self.assertFalse(p.compare(a, b)["comparable"])

    def test_tampered_report(self):
        cases = '<testcase name="x"/>'
        a, b = self.receipt("before", cases), self.receipt("after", cases)
        with (b / "junit.xml").open("ab") as f:
            f.write(b"\n")
        self.assertTrue(any("hash" in x for x in p.compare(a, b)["blockers"]))

    def test_source_mutation(self):
        cases = '<testcase name="x"/>'
        a = self.receipt("before", cases)
        b = self.receipt("after", cases, source_after={"fingerprint": "changed"})
        self.assertFalse(p.compare(a, b)["comparable"])

    def test_exit_disagreement(self):
        a = self.receipt("before", '<testcase name="x"/>')
        b = self.receipt("after", '<testcase name="x"/>', returncode=1)
        self.assertTrue(any("exit code" in x for x in p.compare(a, b)["blockers"]))

    def test_empty_report_is_not_green(self):
        a, b = self.receipt("before", ""), self.receipt("after", "")
        self.assertFalse(p.compare(a, b)["comparable"])

    def test_missing_time_blocks(self):
        a = self.receipt("before", '<testcase name="x"/>', started=None)
        b = self.receipt("after", '<testcase name="x"/>')
        self.assertFalse(p.compare(a, b)["comparable"])

    def test_overlapping_time_blocks(self):
        a = self.receipt("before", '<testcase name="x"/>', ended="2026-10-22T08:01:01+00:00")
        b = self.receipt("after", '<testcase name="x"/>')
        self.assertFalse(p.compare(a, b)["comparable"])

    def test_untrusted_blocker_newlines_escaped(self):
        result = {"comparable": False, "before_counts": {}, "after_counts": {},
                  "blockers": ["bad\n# FORGED"], "categories": {}, "limits": []}
        output = p.markdown(result)
        self.assertNotIn("\n# FORGED", output)
        self.assertIn("\\n# FORGED", output)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        (self.repo / "source.txt").write_text("stable input")
        for argv in (["init", "-q"], ["config", "user.name", "Fixture"],
                     ["config", "user.email", "fixture@example.invalid"],
                     ["add", "."], ["commit", "-qm", "fixture"]):
            subprocess.run(["git", "-C", str(self.repo), *argv], check=True, capture_output=True)

    def tearDown(self):
        self.temp.cleanup()

    def args(self, out=None):
        code = 'import pathlib,sys; assert sys.argv[2] == "literal ; $(not-a-command)"; pathlib.Path(sys.argv[1]).write_text(\'<testsuite><testcase name="x"/></testsuite>\')'
        return argparse.Namespace(cwd=str(self.repo), out=str(out or self.root / "evidence"),
                                  project="fixture", scope="all", environment="stdlib", timeout=5,
                                  command=[sys.executable, "-c", code, "{junit}", "literal ; $(not-a-command)"])

    def test_capture_preserves_argv_and_spaces(self):
        args = self.args()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(p.capture(args), 0)
        receipt, report, issues = p.load_run(args.out)
        self.assertFalse(issues)
        self.assertEqual(report["counts"], {"pass": 1})
        self.assertEqual(receipt["command_template"][-1], "literal ; $(not-a-command)")

    def test_existing_evidence_never_overwritten(self):
        args = self.args()
        Path(args.out).mkdir()
        with self.assertRaises(FileExistsError):
            p.capture(args)
        self.assertFalse((Path(args.out) / "console.log").exists())

    def test_missing_placeholder_does_not_execute(self):
        args = self.args()
        args.command = [sys.executable, "-c", "raise SystemExit(0)"]
        with self.assertRaises(ValueError):
            p.capture(args)
        self.assertFalse(Path(args.out).exists())

    def test_repo_output_refused(self):
        args = self.args(self.repo / "out")
        with self.assertRaises(ValueError):
            p.capture(args)
        self.assertFalse(Path(args.out).exists())


if __name__ == "__main__":
    unittest.main()
