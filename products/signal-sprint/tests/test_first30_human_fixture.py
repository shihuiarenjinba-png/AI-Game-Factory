"""Synthetic contract tests: no real human QA or GDK certification."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
from signal_sprint_first30_human_gate import FIXTURE, HEAD, IMMUTABLE, RUN, validate_fixture, validate_observation


class HumanFirst30FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def errors(self, **updates):
        f = copy.deepcopy(self.f)
        f.update(updates)
        return validate_fixture(f)

    def test_plan_valid_but_human_hold(self):
        self.assertEqual(validate_fixture(self.f), [])
        self.assertEqual(validate_observation(self.f, None), ([], "HOLD_HUMAN_NOT_EXECUTED"))
        self.assertFalse(self.f["release_gates"]["sale_ready"])

    def test_pinned_actual_gui_lineage_not_immutable_gdk_exe(self):
        self.assertEqual(self.f["pinned_revision_sha"], HEAD)
        self.assertNotEqual(HEAD, IMMUTABLE)
        self.assertEqual(self.f["pinned_windows_run_id"], RUN)
        self.assertEqual(self.f["pinned_artifact_id"], "13154872780")
        self.assertIn("EVIDENCE_ONLY", self.f["exe_availability"])

    def test_rejects_wrong_artifact_and_source(self):
        self.assertIn("ARTIFACT_DRIFT", self.errors(pinned_artifact_id="13135583436"))
        self.assertIn("REVISION_DRIFT", self.errors(pinned_revision_sha=IMMUTABLE))

    def test_rejects_ordinary_msix_route(self):
        self.assertIn("GDK_ROUTE", self.errors(registration="MSIX"))

    def test_rejects_fake_dpi_125_pass(self):
        d = copy.deepcopy(self.f["reference_display"])
        d["dpi_125"] = "PASS"
        self.assertIn("FALSE_DPI_PASS", self.errors(reference_display=d))

    def test_rejects_missing_japanese_loss_text(self):
        s = copy.deepcopy(self.f["screenshots"])
        s["jp_lost"]["expected_visible"] = []
        self.assertIn("SCREEN_CONTRACT_jp_lost", self.errors(screenshots=s))

    def test_rejects_incomplete_first30_step(self):
        steps = copy.deepcopy(self.f["steps"])
        steps[0]["fail_if"] = ""
        self.assertIn("STEP_MISSING_EXPECTATION_blind_start", self.errors(steps=steps))

    def test_rejects_missing_negative_case(self):
        n = list(self.f["negative_cases"])
        n.remove("WINDOW_OVER_TASKBAR")
        self.assertIn("NEGATIVE_CASES", self.errors(negative_cases=n))

    def test_rejects_forged_human_and_sdk_pass(self):
        t = copy.deepcopy(self.f["human_observation_template"])
        t["human_qa_pass"] = True
        self.assertIn("FALSE_HUMAN_PASS", self.errors(human_observation_template=t))
        g = copy.deepcopy(self.f["release_gates"])
        g["msixvc2_built"] = True
        self.assertIn("FALSE_RELEASE_GATE", self.errors(release_gates=g))

    def test_no_observation_may_pass_without_real_exe(self):
        errors, status = validate_observation(self.f, {"status": "HUMAN_REPORTED_CHECK_ONLY"})
        self.assertEqual(status, "HOLD")
        self.assertIn("PINNED_REAL_EXE_AND_SCREENSHOT_RECEIPT_REQUIRED", errors)


if __name__ == "__main__":
    unittest.main()
