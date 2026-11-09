"""Regression fixture for Windows UIA failure #42560278359.

This is a diagnostic contract, NOT a UIA PASS. The real Windows GUI job
remains the only authority for ControlType/Name/Invoke/Focus and LOST text.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "products" / "signal-sprint" / "main.py"
GUI = ROOT / "qa" / "signal_sprint_ui_revision_gui.ps1"

class SignalSprintUIABlockerFixture(unittest.TestCase):
    def test_original_step10_gate_is_fail_closed(self):
        script = GUI.read_text(encoding="utf-8")
        for token in ("en_buttons", "jp_buttons", "jp_lost_text", "en_lost_text",
                      "HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED",
                      "REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY",
                      "exit 4"):
            with self.subTest(token=token):
                self.assertIn(token, script)
        self.assertIn("ControlType]::Button", script)

    def test_tk_controls_are_not_automatically_uia_evidence(self):
        tree = ast.parse(PRODUCT.read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)]
        widget_names = [n.func.attr for n in calls if isinstance(n.func.value, ast.Name)
                        and n.func.value.id == "tk"]
        self.assertIn("Button", widget_names)
        self.assertIn("Label", widget_names)
        # A Tk widget's presence does not establish a native UIA Button/Text
        # or support for InvokePattern, Name and keyboard focus.

    def test_windows_gate_must_not_be_replaced_by_pixel_assertions(self):
        script = GUI.read_text(encoding="utf-8")
        self.assertIn("uia_gate_failed_checks", script)
        self.assertIn("exit 4", script)
        self.assertIn("Capture-UIATree 'jp-lost'", script)
        self.assertIn("Capture-UIATree 'en-lost'", script)

if __name__ == "__main__":
    unittest.main()
