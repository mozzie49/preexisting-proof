"""Synthetic application tests, really executed by unittest, emitting JUnit XML."""
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

config = json.loads(Path("state.json").read_text())


class AppChecks(unittest.TestCase):
    def test_stable(self):
        self.assertEqual(config["stable"], 0, "known billing mismatch")

    def test_changed(self):
        self.assertEqual(config["changed"], 0, "cart value mismatch")

    def test_healed(self):
        self.assertEqual(config["healed"], 0)

    def test_skipped(self):
        if config["skip"]:
            self.skipTest("temporarily disabled")
        self.assertEqual(1, 0)

    def test_missing(self):
        self.assertEqual(1, 0)


def make_check(index):
    def test(self):
        self.assertEqual(config["regressions"].get(str(index), 0), 0)
    return test


for i in range(300):
    setattr(AppChecks, f"test_case_{i:03}", make_check(i))
if not config["include_missing"]:
    delattr(AppChecks, "test_missing")


class RecordingResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append((test, "pass", ""))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append((test, "failure", self._exc_info_to_string(err, test)))

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append((test, "error", self._exc_info_to_string(err, test)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append((test, "skipped", reason))


result = RecordingResult()
unittest.defaultTestLoader.loadTestsFromTestCase(AppChecks).run(result)
root = ET.Element("testsuite", name="app", tests=str(result.testsRun),
                  failures=str(len(result.failures)), errors=str(len(result.errors)),
                  skipped=str(len(result.skipped)))
for test, status, message in result.records:
    case = ET.SubElement(root, "testcase", classname="AppChecks", name=test._testMethodName)
    if status != "pass":
        elem = ET.SubElement(case, status, message=message.splitlines()[-1], type="AssertionError")
        elem.text = message
    # Deterministic simulated application logs; compression metrics are artifact bytes,
    # not a claim about production test logs or model-token savings.
    noise = "\n".join(f"fixture request {j}: cache warm; request handled; DB rows=4" for j in range(8))
    ET.SubElement(case, "system-out").text = noise
    print(test.id(), status, message)
ET.ElementTree(root).write(sys.argv[1], encoding="utf-8", xml_declaration=True)
raise SystemExit(0 if result.wasSuccessful() else 1)
