"""Synthetic JP/EN GUI transition and fail-closed receipt fixtures.

Never treat synthetic bytes as Windows GUI, OS DPI, UIAutomation, human QA,
GDK SDK, CAS, MSIXVC2 or sale readiness evidence.
"""
import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
from signal_sprint_bilingual_receipt import EN_IMAGES, verify_bilingual
from signal_sprint_exhaustion_receipt import IMAGES, IMMUTABLE

HEAD = "a" * 40
EXE_SHA = "b" * 64
RUN = "123456789"
MOVES = ["RIGHT" if i % 2 == 0 else "LEFT" for i in range(30)]


def synthetic_png_marker(payload):
    # PNG signature and IHDR dimension fields only. Not a real image.
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 916, 659) + payload


class SameExeBilingualTransitionContract(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.receipt = dict(
            product="Signal Sprint", registration="GDK_GAME",
            immutable_source_sha=IMMUTABLE,
            evidence_kind="NEW_REVISION_REAL_WINDOWS_GUI_CHECK_ONLY",
            revision_sha=HEAD, workflow_run_id=RUN,
            exe_sha256=EXE_SHA, exe_size_bytes=11445122,
            status="GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
            exhaustion_gui_check_only="REAL_30_KEYS_AND_CHANGED_LAST_FRAME_CHECK_ONLY",
            exhaustion_move_count=30, exhaustion_input_sequence=MOVES[:],
            en_exhaustion_gui_check_only="REAL_EN_30_KEYS_RESTART_REPLAY_CHECK_ONLY",
            en_exhaustion_move_count=30, en_exhaustion_input_sequence=MOVES[:],
            retry_restores_initial_window_pixels=True,
            exhaustion_pixel_change_observed=True,
            exhaustion_reset_pixel_match=True, replay_pixel_match=True,
            jp_window_title_observed=True,
            human_qa_pass=False, sale_ready=False, cas_return_pass=False,
            gdk_sdk_executed=False, msixvc2_built=False, store_submitted=False,
            target_dpi_percent=100, dpi_percent=100,
            dpi_125="HOLD_UNMEASURED", dpi_150="HOLD_UNMEASURED",
            dpi_125_150="HOLD_NOT_TESTED",
            jp_en_text_clipping="HOLD_UNMEASURED",
            lost_text_semantics="HOLD_UIAUTOMATION_UNAVAILABLE",
            en_lost_text_semantics="HOLD_UIAUTOMATION_UNAVAILABLE",
            language_matrix_status="REAL_JP_AND_EN_SAME_EXE_CHECK_ONLY",
            work_area_bounds=[0, 0, 1024, 720],
            window_bounds=[16, 16, 932, 675],
        )
        for lang, mapping in (("jp", IMAGES), ("en", EN_IMAGES)):
            for field, filename in mapping.items():
                if "post_exhaustion_restart" in field or field in ("jp_window_sha256", "en_window_sha256"):
                    phase = "initial"
                elif field in ("after_input_window_sha256", "replay_window_sha256",
                               "en_after_input_window_sha256", "en_replay_window_sha256"):
                    phase = "one-move"
                else:
                    phase = field
                payload = synthetic_png_marker((lang + ":" + phase).encode())
                (self.root / filename).write_bytes(payload)
                self.receipt[field] = hashlib.sha256(payload).hexdigest()

    def errors(self, head=HEAD, exe=EXE_SHA):
        return verify_bilingual(self.receipt, self.root, head, exe)

    def test_valid_synthetic_transition_is_check_only_even_without_uia(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.receipt["lost_text_semantics"], "HOLD_UIAUTOMATION_UNAVAILABLE")
        self.assertEqual(self.receipt["en_lost_text_semantics"], "HOLD_UIAUTOMATION_UNAVAILABLE")
        self.assertIs(self.receipt["human_qa_pass"], False)
        self.assertIs(self.receipt["sale_ready"], False)

    def test_rejects_new_old_artifact_exe_or_head_swap(self):
        self.assertIn("EXE_SHA_MISMATCH", self.errors(exe="c" * 64))
        self.assertIn("REVISION_SHA_DRIFT", self.errors(head="d" * 40))
        self.receipt["workflow_run_id"] = "not-a-run"
        self.assertIn("GITHUB_RUN_ID_MISSING", self.errors())

    def test_rejects_unproven_uia_semantic_pass_both_languages(self):
        self.receipt["lost_text_semantics"] = "PASS"
        self.receipt["en_lost_text_semantics"] = "PASS"
        errors = self.errors()
        self.assertIn("LOST_TEXT_UNTRUSTED", errors)
        self.assertIn("EN_TEXT_UNTRUSTED", errors)

    def test_rejects_fake_dpi_and_text_clipping_pass(self):
        self.receipt["dpi_125"] = "REAL_OS_DPI_125_GUI_CHECK_ONLY"
        self.receipt["dpi_150"] = "PASS"
        self.receipt["jp_en_text_clipping"] = "PASS"
        errors = self.errors()
        self.assertIn("UNMEASURED_FALSE_PASS_dpi_125", errors)
        self.assertIn("UNMEASURED_FALSE_PASS_dpi_150", errors)
        self.assertIn("GLYPH_CLIPPING_FALSE_PASS", errors)

    def test_rejects_false_jp_and_en_last_move_transition(self):
        self.receipt["exhausted_window_sha256"] = self.receipt["pre_exhaustion_window_sha256"]
        self.receipt["en_exhausted_window_sha256"] = self.receipt["en_pre_exhaustion_window_sha256"]
        errors = self.errors()
        self.assertIn("LAST_MOVE_NO_CHANGE", errors)
        self.assertIn("EN_LAST_MOVE_NO_CHANGE", errors)

    def test_rejects_replay_or_retry_that_does_not_restore_expected_pixels(self):
        self.receipt["post_exhaustion_restart_window_sha256"] = self.receipt["after_input_window_sha256"]
        self.receipt["en_replay_window_sha256"] = self.receipt["en_window_sha256"]
        errors = self.errors()
        self.assertIn("RESET_NOT_EQUAL", errors)
        self.assertIn("EN_REPLAY_NOT_EQUAL", errors)

    def test_rejects_relabelled_japanese_as_english(self):
        self.receipt["en_window_sha256"] = self.receipt["jp_window_sha256"]
        self.assertIn("EN_JP_SAME_PIXELS", self.errors())

    def test_rejects_changed_screenshot_bytes_and_workarea_escape(self):
        path = self.root / "signal-sprint-en-turn-30-expected-lost.png"
        path.write_bytes(path.read_bytes() + b"tamper")
        self.receipt["window_bounds"] = [16, 16, 1040, 788]
        errors = self.errors()
        self.assertIn("EN_IMAGE_TAMPER_signal-sprint-en-turn-30-expected-lost.png", errors)
        self.assertIn("WINDOW_OUTSIDE_WORK_AREA", errors)


if __name__ == "__main__":
    unittest.main()
