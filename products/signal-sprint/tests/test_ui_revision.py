"""UI-only revision gates. The immutable source commit must remain unchanged."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "main.py"
spec = importlib.util.spec_from_file_location("signal_sprint_ui_revision", MODULE)
game_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game_module)


class UIRevisionTests(unittest.TestCase):
    def test_1024x720_work_area_has_chrome_margin(self):
        w, h = game_module.ui_window_size(1024, 720)
        self.assertEqual((w, h), (900, 620))
        self.assertLessEqual(w + 64, 1024)
        self.assertLessEqual(h + 80, 720)

    def test_rejects_unsupported_work_area(self):
        for area in ((800, 600), (1024, 599), (839, 720), (840, 600)):
            with self.subTest(area=area), self.assertRaises(ValueError):
                game_module.ui_window_size(*area)

    def test_japanese_all_gameplay_messages_and_errors(self):
        messages = [
            "Collect three cells, then reach EXIT.",
            "Blocked. Choose another route.",
            "Circuit complete! Press R to restart.",
            "Out of moves. Press R to retry.",
            "EXIT locked: collect all three cells first.",
            "Find the shortest safe route.",
            "No move to undo.",
            "Move undone. Choose your next step.",
            "Saved round loaded. Press R to restart after game over.",
            "Saved on this computer.",
        ]
        for message in messages:
            with self.subTest(message=message):
                jp = game_module.ui_message(message, "JP")
                self.assertNotEqual(jp, message)
                self.assertEqual(game_module.ui_message(message, "EN"), message)
        self.assertIn("保存", game_module.ui_message("Save failed: OSError", "JP"))
        self.assertIn("読み込", game_module.ui_message("Load failed: ValueError", "JP"))
        self.assertEqual(set(game_module.UI_STATUS_JP), {"PLAYING", "WON", "LOST"})

    def test_gameplay_state_machine_not_changed(self):
        game = game_module.Game()
        self.assertEqual((game.position, game.turns, game.status), ((0, 0), 0, "PLAYING"))
        self.assertTrue(game.move(1, 0))
        self.assertEqual((game.position, game.turns), ((1, 0), 1))
        self.assertTrue(game.undo())
        self.assertEqual((game.position, game.turns), ((0, 0), 0))


if __name__ == "__main__":
    unittest.main()
