"""Synthetic negative fixtures only; never represent actual Windows GUI or human QA."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
from signal_sprint_visibility_receipt import REGIONS, SCREENS, verify, IMMUTABLE


class VisibilityReceiptContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images = self.root / "screenshots"
        self.images.mkdir()
        self.exe = self.root / "SignalSprint.exe"
        self.exe.write_bytes(b"MZ" + b"test-exe-not-a-real-build" * 6000)
        self.revision = "a" * 40
        self.run = "123456"
        self.receipt = {
            "product": "Signal Sprint", "registration": "GDK_GAME",
            "immutable_source_sha": IMMUTABLE,
            "evidence_kind": "NEW_REVISION_REAL_WINDOWS_GUI_CHECK_ONLY",
            "revision_sha": self.revision, "workflow_run_id": self.run,
            "exe_sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
            "exe_size_bytes": self.exe.stat().st_size,
            "monitor_bounds": [0, 0, 1024, 768],
            "work_area_bounds": [0, 0, 1024, 720],
            "window_bounds": [16, 16, 932, 675],
            "dpi_percent": 100, "target_dpi_percent": 100,
            "dpi_125": "HOLD_UNMEASURED", "dpi_150": "HOLD_UNMEASURED",
            "jp_en_text_clipping": "HOLD_UNMEASURED",
            "language_matrix_status": "REAL_JP_AND_EN_SAME_EXE_CHECK_ONLY",
            "status": "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
            "human_qa_pass": False, "sale_ready": False,
            "cas_return_pass": False, "gdk_sdk_executed": False,
            "msixvc2_built": False, "store_submitted": False,
        }
        for key, (filename, field) in SCREENS.items():
            image = Image.new("RGB", (916, 659), (16, 24, 39))
            draw = ImageDraw.Draw(image)
            for rect, minimum in REGIONS.values():
                x0, y0, _, _ = rect
                draw.rectangle((x0 + 20, y0 + 8, x0 + 74, y0 + 22), fill="white")
            if key.startswith("jp"):
                draw.point((400, 55), fill=(240, 240, 240))
            image.save(self.images / filename)
            self.receipt[field] = hashlib.sha256((self.images / filename).read_bytes()).hexdigest()
            if key.endswith("initial"):
                lang = key.split("_")[0]
                monitor = Image.new("RGB", (1024, 768), (0, 0, 0))
                monitor.paste(image, (16, 16))
                path = self.images / ("signal-sprint-" + lang + ".png")
                monitor.save(path)
                self.receipt[lang + "_screenshot_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    def errors(self):
        return verify(self.receipt, self.images, self.revision, self.run, self.exe)[0]

    def test_positive_is_check_only_not_semantics(self):
        errors, report = verify(self.receipt, self.images, self.revision, self.run, self.exe)
        self.assertEqual(errors, [])
        self.assertEqual(report["status"], "CHECK_ONLY")
        self.assertIn("GLYPH_CLIPPING_AND_UIAUTOMATION_TEXT_HOLD", report["limitations"])

    def test_rejects_wrong_run_and_head(self):
        self.receipt["workflow_run_id"] = "other"
        self.receipt["revision_sha"] = "b" * 40
        self.assertIn("RUN_ID_MISMATCH", self.errors())
        self.assertIn("REVISION_HEAD_MISMATCH", self.errors())

    def test_rejects_exe_bytes_change(self):
        self.exe.write_bytes(self.exe.read_bytes() + b"tamper")
        self.assertIn("EXE_BYTES_MISMATCH", self.errors())

    def test_rejects_screenshot_tamper(self):
        path = self.images / "signal-sprint-jp-window-initial.png"
        with Image.open(path) as image:
            rgb = image.convert("RGB")
        rgb.putpixel((400, 55), (255, 0, 0))
        rgb.save(path)
        self.assertIn("SCREENSHOT_SHA_MISMATCH_jp_initial", self.errors())

    def test_rejects_blank_instructions_even_with_rehashed_png(self):
        path = self.images / "signal-sprint-en-window-initial.png"
        with Image.open(path) as image:
            rgb = image.convert("RGB")
        draw = ImageDraw.Draw(rgb)
        draw.rectangle(REGIONS["instructions"][0], fill=(16, 24, 39))
        rgb.save(path)
        self.receipt["en_window_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertIn("REGION_EMPTY_en_initial_instructions", self.errors())

    def test_rejects_edge_clipped_bright_pixels(self):
        path = self.images / "signal-sprint-jp-turn-30-expected-lost.png"
        with Image.open(path) as image:
            rgb = image.convert("RGB")
        x0, y0, _, _ = REGIONS["status"][0]
        rgb.putpixel((x0 + 1, y0 + 10), (255, 255, 255))
        rgb.save(path)
        self.receipt["exhausted_window_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertIn("REGION_EDGE_CLIP_RISK_jp_lost_status", self.errors())

    def test_rejects_wrong_work_area(self):
        self.receipt["work_area_bounds"] = [0, 0, 1024, 768]
        self.assertIn("WORK_AREA_NOT_1024x720", self.errors())

    def test_rejects_forged_dpi_and_sale_ready(self):
        self.receipt["dpi_125"] = "PASS"
        self.receipt["sale_ready"] = True
        self.assertIn("DPI_125_150_FALSE_PASS", self.errors())
        self.assertIn("FORBIDDEN_PASS_sale_ready", self.errors())

    def test_rejects_monitor_crop_mismatch(self):
        path = self.images / "signal-sprint-en.png"
        with Image.open(path) as image:
            rgb = image.convert("RGB")
        rgb.putpixel((400, 200), (255, 255, 255))
        rgb.save(path)
        self.receipt["en_screenshot_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertIn("MONITOR_WINDOW_CROP_MISMATCH_en", self.errors())

    def test_rejects_forged_clipping_pass(self):
        self.receipt["jp_en_text_clipping"] = "PASS"
        self.assertIn("GLYPH_CLIPPING_FALSE_PASS", self.errors())


if __name__ == "__main__":
    unittest.main()
