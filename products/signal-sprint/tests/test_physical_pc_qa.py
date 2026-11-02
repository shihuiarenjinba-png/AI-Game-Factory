"""Synthetic physical-PC receipt fixtures; NOT evidence of a real Windows QA PASS."""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
from signal_sprint_physical_pc_qa import (
    EXE_SHA, EXE_SIZE, MATRIX, QUESTIONS, RELEASE, aggregate, check_session, lineage
)


class PhysicalPcQaReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sessions = []
        for i, (lang, dpi) in enumerate(sorted(MATRIX)):
            shots = {}
            for j, phase in enumerate(("initial", "lost", "replay")):
                path = self.root / f"{lang}-{dpi}-{phase}.png"
                Image.new("RGB", (1024, 768), (i * 30, j * 60, 70)).save(path)
                from signal_sprint_physical_pc_qa import digest
                shots[phase] = {"path": path.name, "sha256": digest(path)}
            self.sessions.append({
                **lineage(), "language": lang, "target_dpi_percent": dpi,
                "os_observation": {
                    "source": "windows-user32-live",
                    "raw_dpi": {100: 96, 125: 120, 150: 144}[dpi],
                    "os_dpi_percent": dpi, "screen_bounds": [0, 0, 1024, 768],
                    "work_area_bounds": [0, 0, 1024, 720],
                    "window_bounds": [16, 16, 932, 675],
                    "running_exe_sha256": EXE_SHA, "running_exe_size_bytes": EXE_SIZE},
                "screenshots": shots, "code_integrity_blocked": False,
                "human_answers": {k: True for k in QUESTIONS},
                "release_gates": {k: False for k in RELEASE},
                "status": "SESSION_HUMAN_REVIEW_REQUIRED"
            })

    def errors(self):
        return aggregate(self.sessions, self.root)["errors"]

    def test_synthetic_complete_never_certifies_or_sells(self):
        result = aggregate(self.sessions, self.root)
        self.assertEqual(result["status"], "PHYSICAL_HUMAN_QA_EVIDENCE_REVIEW_REQUIRED")
        self.assertFalse(result["physical_qa_certified"])
        self.assertFalse(result["sale_ready"])
        self.assertFalse(result["msixvc2_built"])

    def test_missing_125_150_holds(self):
        self.sessions = [s for s in self.sessions if s["target_dpi_percent"] == 100]
        self.assertIn("INCOMPLETE_JA_EN_100_125_150", self.errors())

    def test_forged_os_dpi_holds(self):
        self.sessions[0]["os_observation"]["raw_dpi"] = 96 if self.sessions[0]["target_dpi_percent"] != 100 else 120
        self.assertIn("ACTUAL_OS_DPI_MISMATCH", self.errors())

    def test_wrong_or_old_gdk_exe_holds(self):
        self.sessions[0]["os_observation"]["running_exe_sha256"] = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
        self.assertIn("RUNNING_EXE_WRONG", self.errors())

    def test_receipt_exe_sha_or_request_holds(self):
        self.sessions[0]["exe_sha256"] = "f" * 64
        self.sessions[0]["original_request_id"] = "unauthorized"
        self.assertIn("LINEAGE_exe_sha256", self.errors())
        self.assertIn("LINEAGE_original_request_id", self.errors())

    def test_code_integrity_block_holds(self):
        self.sessions[0]["code_integrity_blocked"] = True
        self.assertIn("CODE_INTEGRITY_HOLD", self.errors())

    def test_workarea_overlap_holds(self):
        self.sessions[0]["os_observation"]["window_bounds"] = [16, 16, 932, 745]
        self.assertIn("WINDOW_OVERLAPS_TASKBAR_OR_OUTSIDE_WORKAREA", self.errors())

    def test_forged_release_gate_holds(self):
        self.sessions[0]["release_gates"]["sale_ready"] = True
        self.assertIn("FORGED_RELEASE_GATE", self.errors())

    def test_missing_first30_answer_holds(self):
        self.sessions[0]["human_answers"]["retry_understood_in_30s"] = None
        self.assertIn("HUMAN_FIRST30_OR_REPLAY_HOLD", self.errors())

    def test_reused_screenshot_holds(self):
        self.sessions[1]["screenshots"]["initial"] = dict(self.sessions[0]["screenshots"]["initial"])
        self.assertIn("SCREENSHOT_REUSED_BETWEEN_SESSIONS", self.errors())

    def test_tampered_screenshot_holds(self):
        path = self.root / self.sessions[0]["screenshots"]["lost"]["path"]
        path.write_bytes(b"tampered")
        self.assertIn("SCREENSHOT_MISSING_OR_TAMPERED", self.errors())

    def test_fake_session_pass_holds(self):
        self.sessions[0]["status"] = "PASS"
        self.assertIn("SESSION_STATUS_FALSE_PASS", self.errors())

    def test_missing_phase_holds(self):
        self.sessions[0]["screenshots"].pop("replay")
        self.assertIn("THREE_SCREENSHOTS_REQUIRED", self.errors())


    def test_new_gui_bundle_cannot_masquerade_as_old_pinned_physical_qa(self):
        # Observed GitHub Artifact #13167801977 (run #41498959569), NOT the
        # pinned physical-PC protocol Artifact #13164091404.
        session = self.sessions[0]
        session.update({
            "artifact_id": 13167801977,
            "workflow_run_id": "41498959569",
            "build_head_sha": "f5bc1e0d495bdcd65bf25fa370d7e68ef415d323",
            "exe_sha256": "b17424ba8b0954162a1087e7db90cdcb34ca1c30e0a992da53ff61cd17f63ad4",
            "exe_size_bytes": 11445122,
        })
        session["os_observation"].update({
            "running_exe_sha256": session["exe_sha256"],
            "running_exe_size_bytes": session["exe_size_bytes"],
        })
        errors = check_session(session, self.root)
        for key in ("artifact_id", "workflow_run_id", "build_head_sha",
                    "exe_sha256", "exe_size_bytes"):
            self.assertIn("LINEAGE_" + key, errors)
        self.assertIn("RUNNING_EXE_WRONG", errors)

if __name__ == "__main__":
    unittest.main()
