"""Synthetic receipt contract tests only; never evidence of real GUI success."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / "qa" / "signal_sprint_exhaustion_receipt.py"
spec = importlib.util.spec_from_file_location("gui_receipt_contract", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SyntheticReceiptContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.images = root / "screenshots"
        self.images.mkdir()
        hashes = {}
        for field, filename in mod.IMAGES.items():
            # Test bytes are NOT real screenshots; they are local unit fixtures.
            if field in ("jp_window_sha256", "post_exhaustion_restart_window_sha256"):
                payload = b"synthetic-initial"
            elif field in ("after_input_window_sha256", "replay_window_sha256"):
                payload = b"synthetic-one-move"
            else:
                payload = field.encode()
            (self.images / filename).write_bytes(payload)
            hashes[field] = hashlib.sha256(payload).hexdigest()
        self.receipt = dict(
            product="Signal Sprint", registration="GDK_GAME",
            immutable_source_sha=mod.IMMUTABLE,
            evidence_kind="NEW_REVISION_REAL_WINDOWS_GUI_CHECK_ONLY",
            revision_sha="a" * 40, workflow_run_id="12345",
            exe_sha256="b" * 64, exe_size_bytes=123456,
            status="GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
            exhaustion_gui_check_only="REAL_30_KEYS_AND_CHANGED_LAST_FRAME_CHECK_ONLY",
            exhaustion_move_count=30,
            exhaustion_input_sequence=["RIGHT" if i % 2 == 0 else "LEFT" for i in range(30)],
            retry_restores_initial_window_pixels=True,
            exhaustion_pixel_change_observed=True,
            exhaustion_reset_pixel_match=True, replay_pixel_match=True,
            jp_window_title_observed=True,
            human_qa_pass=False, sale_ready=False, cas_return_pass=False,
            gdk_sdk_executed=False, msixvc2_built=False, store_submitted=False,
            dpi_125="HOLD_UNMEASURED", dpi_150="HOLD_UNMEASURED",
            dpi_125_150="HOLD_NOT_TESTED",
            jp_en_text_clipping="HOLD_UNMEASURED",
            lost_text_semantics="HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED",
            work_area_bounds=[0, 0, 1024, 720],
            window_bounds=[16, 16, 932, 675],
            **hashes,
        )

    def verify(self):
        return mod.verify_receipt(self.receipt, self.images, expected_revision="a" * 40)

    def test_synthetic_structural_fixture_only(self):
        self.assertEqual(self.verify(), [])

    def test_rejects_short_or_wrong_move_sequence(self):
        self.receipt["exhaustion_input_sequence"][-1] = "RIGHT"
        self.assertIn("INPUT_SEQUENCE_WRONG", self.verify())

    def test_rejects_old_lineage_and_fake_package_pass(self):
        self.receipt["immutable_source_sha"] = "c" * 40
        self.receipt["msixvc2_built"] = True
        errors = self.verify()
        self.assertIn("IMMUTABLE_SOURCE_MISMATCH", errors)
        self.assertIn("FORBIDDEN_SUCCESS_CLAIM_msixvc2_built", errors)

    def test_rejects_screenshot_tampering(self):
        (self.images / "signal-sprint-jp-turn-30-expected-lost.png").write_bytes(b"tampered")
        self.assertTrue(any(e.startswith("SCREENSHOT_TAMPER_") for e in self.verify()))

    def test_rejects_dpi_or_clipping_false_pass(self):
        self.receipt["dpi_125"] = "PASS"
        self.receipt["jp_en_text_clipping"] = "PASS"
        errors = self.verify()
        self.assertIn("UNMEASURED_FALSE_PASS_dpi_125", errors)
        self.assertIn("UNMEASURED_FALSE_PASS_jp_en_text_clipping", errors)

    def test_rejects_window_outside_work_area(self):
        self.receipt["window_bounds"] = [16, 16, 1040, 788]
        self.assertIn("WINDOW_OUTSIDE_WORK_AREA", self.verify())

    def test_rejects_fake_human_approval(self):
        self.receipt["human_qa_pass"] = True
        self.receipt["sale_ready"] = True
        errors = self.verify()
        self.assertIn("FORBIDDEN_SUCCESS_CLAIM_human_qa_pass", errors)
        self.assertIn("FORBIDDEN_SUCCESS_CLAIM_sale_ready", errors)


if __name__ == "__main__":
    unittest.main()
