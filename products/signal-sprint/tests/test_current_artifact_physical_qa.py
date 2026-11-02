"""Synthetic-only negative fixtures: never physical QA evidence."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
import signal_sprint_current_artifact_physical_qa as current
base = current.base


class CurrentPhysicalQaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.s = self.session("ja", 125)

    def session(self, lang, dpi):
        shots = {}
        for i, phase in enumerate(current.PHASES):
            f = self.root / f"{lang}-{dpi}-{phase}.png"
            Image.new("RGB", (1024, 768), (i * 45 + (10 if lang == "en" else 0), dpi // 2, 100)).save(f)
            shots[phase] = {"path": f.name, "sha256": base.digest(f)}
        return {**base.lineage(), "gui_artifact_id": current.GUI_ARTIFACT_ID,
                "language": lang, "target_dpi_percent": dpi,
                "os_observation": {"source": "windows-user32-live",
                                   "raw_dpi": {100: 96, 125: 120, 150: 144}[dpi],
                                   "os_dpi_percent": dpi, "screen_bounds": [0, 0, 1024, 768],
                                   "work_area_bounds": [0, 0, 1024, 720],
                                   "window_bounds": [16, 16, 932, 675],
                                   "running_exe_sha256": base.EXE_SHA,
                                   "running_exe_size_bytes": base.EXE_SIZE},
                "screenshots": shots, "code_integrity_blocked": False,
                "human_answers": {k: True for k in (*base.QUESTIONS, *current.EXTRA_ANSWERS)},
                "release_gates": {k: False for k in base.RELEASE},
                "status": "SESSION_HUMAN_REVIEW_REQUIRED",
                "physical_qa_certified": False}

    def errors(self):
        return current.extended_errors(self.s, self.root)

    def test_pinned_current_exe_is_not_old_protocol_or_gdk(self):
        self.assertEqual(base.ARTIFACT_ID, 13180405918)
        self.assertEqual(base.RUN, "41525954534")
        self.assertNotEqual(base.EXE_SHA, current.OLD_QA_EXE_SHA)
        self.assertNotEqual(base.EXE_SHA, current.OLD_GDK_EXE_SHA)
        self.assertEqual(len(base.EXE_SHA), 64)

    def test_synthetic_session_is_only_schema_compatible(self):
        self.assertEqual(self.errors(), [])
        self.assertFalse(self.s["physical_qa_certified"])

    def test_old_exe_substitution_rejected(self):
        self.s["os_observation"]["running_exe_sha256"] = current.OLD_GDK_EXE_SHA
        self.assertIn("RUNNING_EXE_WRONG", self.errors())

    def test_wrong_dpi_rejected(self):
        self.s["os_observation"]["raw_dpi"] = 96
        self.assertIn("ACTUAL_OS_DPI_MISMATCH", self.errors())

    def test_workarea_overflow_rejected(self):
        self.s["os_observation"]["window_bounds"] = [0, 0, 1024, 750]
        self.assertIn("WINDOW_OVERLAPS_TASKBAR_OR_OUTSIDE_WORKAREA", self.errors())

    def test_restart_missing_rejected(self):
        del self.s["screenshots"]["restart"]
        self.assertIn("FOUR_PHASE_SCREENSHOTS_REQUIRED", self.errors())

    def test_restart_reused_rejected(self):
        self.s["screenshots"]["restart"] = dict(self.s["screenshots"]["lost"])
        self.assertIn("RESTART_SCREENSHOT_REUSED", self.errors())

    def test_restart_tamper_rejected(self):
        self.s["screenshots"]["restart"]["sha256"] = "f" * 64
        self.assertIn("RESTART_SCREENSHOT_TAMPERED", self.errors())

    def test_restart_human_unmeasured_rejected(self):
        self.s["human_answers"]["restart_state_reset_confirmed"] = None
        self.assertIn("RESTART_HUMAN_EVIDENCE_HOLD", self.errors())

    def test_fake_physical_pass_rejected(self):
        self.s["physical_qa_certified"] = True
        self.assertIn("PHYSICAL_CERTIFICATION_FALSE_PASS", self.errors())

    def test_wrong_gui_artifact_rejected(self):
        self.s["gui_artifact_id"] = 13164091404
        self.assertIn("GUI_ARTIFACT_BINDING_MISMATCH", self.errors())

    def test_no_bundle_is_physical_hold(self):
        absent = self.root / "not-an-artifact.zip"
        self.assertTrue(current.bundle_errors(absent))
        out = self.root / "report.json"
        self.assertEqual(current.main(["--mode", "inspect", "--bundle", str(absent),
                                       "--output", str(out)]), 2)
        self.assertIn('"PHYSICAL_HOLD"', out.read_text())

    def test_synthetic_six_sessions_never_certify(self):
        sessions = [self.session(lang, dpi) for lang in ("ja", "en") for dpi in (100, 125, 150)]
        result = current.aggregate(sessions, self.root)
        self.assertEqual(result["status"], "HUMAN_EVIDENCE_REVIEW_REQUIRED")
        self.assertFalse(result["physical_qa_certified"])
        self.assertFalse(result["sale_ready"])
        self.assertFalse(result["gdk_package_ready"])


if __name__ == "__main__":
    unittest.main()
