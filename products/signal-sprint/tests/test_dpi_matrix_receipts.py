"""Synthetic negative/positive contract fixtures. No OS DPI or GUI is simulated as evidence."""
import hashlib
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
import signal_sprint_exhaustion_receipt as base_verifier
import signal_sprint_bilingual_receipt as bilingual
import signal_sprint_dpi_matrix_receipt as matrix


def png(width, height, rgb):
    def chunk(name, data):
        payload = name + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanline = b"\x00" + bytes(rgb) * width
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(scanline * height)) + chunk(b"IEND", b"")


class DpiAndBilingualSyntheticContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.images = Path(self.temp.name) / "screenshots"
        self.images.mkdir()
        self.receipt = {
            "product": "Signal Sprint", "registration": "GDK_GAME",
            "immutable_source_sha": base_verifier.IMMUTABLE,
            "evidence_kind": "NEW_REVISION_REAL_WINDOWS_GUI_CHECK_ONLY",
            "revision_sha": "a" * 40, "workflow_run_id": "12345",
            "exe_sha256": "b" * 64, "exe_size_bytes": 123456,
            "status": "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
            "exhaustion_gui_check_only": "REAL_30_KEYS_AND_CHANGED_LAST_FRAME_CHECK_ONLY",
            "exhaustion_move_count": 30,
            "exhaustion_input_sequence": ["RIGHT" if i % 2 == 0 else "LEFT" for i in range(30)],
            "retry_restores_initial_window_pixels": True,
            "exhaustion_pixel_change_observed": True,
            "exhaustion_reset_pixel_match": True,
            "replay_pixel_match": True, "jp_window_title_observed": True,
            "human_qa_pass": False, "sale_ready": False, "cas_return_pass": False,
            "gdk_sdk_executed": False, "msixvc2_built": False, "store_submitted": False,
            "dpi_125": "HOLD_UNMEASURED", "dpi_150": "HOLD_UNMEASURED",
            "dpi_125_150": "HOLD_NOT_TESTED", "jp_en_text_clipping": "HOLD_UNMEASURED",
            "lost_text_semantics": "HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED",
            "work_area_bounds": [0, 0, 1024, 720],
            "window_bounds": [16, 16, 932, 675],
            "language_matrix_status": "REAL_JP_AND_EN_SAME_EXE_CHECK_ONLY",
            "en_exhaustion_gui_check_only": "REAL_EN_30_KEYS_RESTART_REPLAY_CHECK_ONLY",
            "en_exhaustion_move_count": 30,
            "en_exhaustion_input_sequence": ["RIGHT" if i % 2 == 0 else "LEFT" for i in range(30)],
            "en_lost_text_semantics": "HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED",
            "target_dpi_percent": 100, "dpi_percent": 100,
        }
        for field, filename in base_verifier.IMAGES.items():
            if field in ("jp_window_sha256", "post_exhaustion_restart_window_sha256"):
                payload = b"synthetic-jp-initial"
            elif field in ("after_input_window_sha256", "replay_window_sha256"):
                payload = b"synthetic-jp-move"
            else:
                payload = field.encode()
            (self.images / filename).write_bytes(payload)
            self.receipt[field] = hashlib.sha256(payload).hexdigest()
        for field, filename in bilingual.EN_IMAGES.items():
            if field in ("en_window_sha256", "en_post_exhaustion_restart_window_sha256"):
                payload = png(916, 659, (15, 22, 30))
            elif field in ("en_after_input_window_sha256", "en_replay_window_sha256"):
                payload = png(916, 659, (30, 22, 15))
            elif field == "en_pre_exhaustion_window_sha256":
                payload = png(916, 659, (10, 30, 10))
            else:
                payload = png(916, 659, (30, 10, 10))
            (self.images / filename).write_bytes(payload)
            self.receipt[field] = hashlib.sha256(payload).hexdigest()
        self.probe = {
            "schema_version": 1, "product": "Signal Sprint", "registration": "GDK_GAME",
            "immutable_source_sha": base_verifier.IMMUTABLE,
            "revision_sha": "a" * 40, "workflow_run_id": "12345",
            "exe_sha256": "b" * 64, "exe_size_bytes": 123456,
            "target_dpi_percent": 125, "os_system_dpi_percent": 100,
            "graphics_dpi_percent": 100,
            "monitor_bounds": [0, 0, 1024, 768], "work_area_bounds": [0, 0, 1024, 720],
            "gui_receipt_path": None, "text_clipping": "HOLD_NOT_AUTOMATICALLY_RECOGNIZED",
            "uia_text_semantics": "HOLD_NOT_AUTOMATICALLY_RECOGNIZED",
            "human_qa_pass": False, "sale_ready": False, "cas_return_pass": False,
            "gdk_sdk_executed": False, "msixvc2_built": False, "store_submitted": False,
            "status": "HOLD_OS_DPI_NOT_TARGET",
            "reason": "REAL_WINDOWS_OS_DPI_NOT_TARGET_NO_EMULATION",
        }

    def en_errors(self):
        return bilingual.verify_bilingual(self.receipt, self.images, expected_revision="a" * 40)

    def probe_errors(self):
        return matrix.verify_probe(self.probe, self.receipt, expected_revision="a" * 40)

    def test_synthetic_bilingual_contract_only(self):
        self.assertEqual(self.en_errors(), [])

    def test_synthetic_real_os_dpi_hold_is_valid(self):
        self.assertEqual(self.probe_errors(), [])

    def test_rejects_forged_dpi_pass_without_gui_receipt(self):
        self.probe["status"] = "CHECK_ONLY_REAL_DPI_GUI"
        self.probe["os_system_dpi_percent"] = 125
        self.probe["graphics_dpi_percent"] = 125
        self.assertIn("GUI_RECEIPT_MISSING", self.probe_errors())

    def test_rejects_false_hold_when_os_dpi_matches(self):
        self.probe["os_system_dpi_percent"] = 125
        self.assertIn("FALSE_OS_DPI_HOLD", self.probe_errors())

    def test_rejects_different_exe_and_run(self):
        self.probe["exe_sha256"] = "c" * 64
        self.probe["workflow_run_id"] = "54321"
        errors = self.probe_errors()
        self.assertIn("EXE_NOT_SAME_PACKAGED_BINARY", errors)
        self.assertIn("RUN_ID_MISMATCH", errors)

    def test_rejects_dpi_or_ui_approval_forgery(self):
        self.probe["sale_ready"] = True
        self.probe["text_clipping"] = "PASS"
        errors = self.probe_errors()
        self.assertIn("FORBIDDEN_SALE_READY", errors)
        self.assertIn("FALSE_TEXT_CLIPPING_PASS", errors)

    def test_rejects_english_image_tamper(self):
        (self.images / bilingual.EN_IMAGES["en_exhausted_window_sha256"]).write_bytes(b"tampered")
        self.assertTrue(any(e.startswith("EN_IMAGE_TAMPER_") for e in self.en_errors()))

    def test_rejects_english_image_dimension_mismatch(self):
        path = self.images / bilingual.EN_IMAGES["en_exhausted_window_sha256"]
        data = png(900, 600, (1, 2, 3))
        path.write_bytes(data)
        self.receipt["en_exhausted_window_sha256"] = hashlib.sha256(data).hexdigest()
        self.assertTrue(any(e.startswith("EN_IMAGE_DIMENSIONS_NOT_WINDOW_") for e in self.en_errors()))

    def test_rejects_forged_english_replay_and_move_count(self):
        self.receipt["en_exhaustion_move_count"] = 29
        self.receipt["en_replay_window_sha256"] = "f" * 64
        errors = self.en_errors()
        self.assertIn("EN_MOVE_COUNT_WRONG", errors)
        self.assertIn("EN_REPLAY_NOT_EQUAL", errors)

    def test_rejects_claim_that_glyph_clipping_is_proven(self):
        self.receipt["jp_en_text_clipping"] = "PASS"
        self.assertIn("GLYPH_CLIPPING_FALSE_PASS", self.en_errors())


if __name__ == "__main__":
    unittest.main()
