"""Work-area-aware Signal Sprint UI regression fixtures; no synthetic physical PASS."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "main.py"
spec = importlib.util.spec_from_file_location("signal_sprint_workarea_ui", MODULE)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class WorkAreaAwareUIFixtures(unittest.TestCase):
    def test_original_100_percent_geometry_stays_stable(self):
        self.assertEqual(ui.ui_window_size(1024, 720), (900, 620))
        self.assertEqual(ui.ui_board_side(900, 620), 480)
        self.assertEqual(ui.ui_fit_client_size(
            900, 620, (16, 16, 932, 675), (0, 0, 1024, 720)),
            (900, 620))

    def test_hosted_1040x788_outer_window_is_not_mistaken_for_client(self):
        width, height = ui.ui_fit_client_size(
            900, 620, (16, 16, 1056, 804), (0, 0, 1024, 720))
        self.assertLess(width, 900)
        self.assertLess(height, 620)
        self.assertGreaterEqual(width, 640)
        self.assertGreaterEqual(height, 420)
        self.assertLess(ui.ui_board_side(width, height), 480)
        self.assertGreaterEqual(ui.ui_board_side(width, height), 280)
        # Physical correction uses measured outer/client ratios, not
        # an unmeasured DPI or a forged 125/150 percent PASS.
        self.assertLess(width * 1040 / 900, 1024 - 16)
        self.assertLess(height * 788 / 620, 720 - 16)

    def test_window_inside_monitor_but_over_taskbar_must_shrink(self):
        width, height = ui.ui_fit_client_size(
            900, 620, (16, 16, 932, 750), (0, 0, 1024, 720))
        self.assertEqual(width, 900)
        self.assertLess(height, 620)

    def test_rejects_invalid_physical_bounds(self):
        for bounds, work in (
            ((0, 0, 0, 100), (0, 0, 1024, 720)),
            ((0, 0, 900, 620), (0, 0, 0, 720)),
            ((0, 0, 900), (0, 0, 1024, 720)),
        ):
            with self.subTest(bounds=bounds, work=work):
                with self.assertRaises(ValueError):
                    ui.ui_fit_client_size(900, 620, bounds, work)

    def test_compact_board_never_hides_controls_under_480(self):
        self.assertEqual(ui.ui_board_side(850, 535), 399)
        self.assertEqual(ui.ui_board_side(640, 420), 280)

    def test_start_retry_and_language_switch_are_bilingual(self):
        source = MODULE.read_text(encoding="utf-8")
        for required in ("Start / Retry (R)", "開始 / 再挑戦 (R)",
                         "日本語 (J)", "English (J)",
                         "SetProcessDpiAwarenessContext",
                         "GetWindowRect", "root.after_idle(fit_actual_window)"):
            self.assertIn(required, source)
        self.assertEqual(ui.UI_STATUS_JP["LOST"], "失敗")
        self.assertIn("Rで再挑戦", ui.ui_message(
            "Out of moves. Press R to retry.", "JP"))


if __name__ == "__main__":
    unittest.main()
