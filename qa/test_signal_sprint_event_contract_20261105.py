"""Negative contract tests: no duplicated, missing, reordered, or mislabeled inputs."""
import copy
import unittest
from qa.signal_sprint_strict_uia_receipt import expected_inputs, validate

HEX = "a" * 64
BASE = {
    "immutable_source_sha": "c058cbf7fe38e02d929c67d047d717ff74bd522e",
    "exe_sha256": HEX, "revision_sha": "b" * 40,
    "workflow_run_id": "123", "status": "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
    "en_buttons_in_workarea": "REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY",
    "jp_buttons_in_workarea": "REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY",
    "lost_text_semantics": "UIAUTOMATION_JP_LOST_TEXT_OBSERVED",
    "en_lost_text_semantics": "UIAUTOMATION_EN_LOST_TEXT_OBSERVED",
    "en_screenshot_sha256": HEX, "jp_screenshot_sha256": HEX,
    "human_qa_pass": False, "sale_ready": False,
}


def valid():
    receipt = copy.deepcopy(BASE)
    receipt["focus_evidence"] = [
        dict(event, expected_pid=123, foreground_pid=123,
             foreground_handle=456, owned_before_input=True)
        for event in expected_inputs()
    ]
    return receipt


class StrictInputContract(unittest.TestCase):
    def test_valid_sequence(self):
        self.assertEqual([], validate(valid()))

    def test_missing(self):
        r = valid()
        r["focus_evidence"].pop()
        self.assertIn("FOCUS_EVIDENCE_MISSING", validate(r))

    def test_duplicate(self):
        r = valid()
        r["focus_evidence"][1] = dict(r["focus_evidence"][0])
        self.assertTrue(any("INPUT_SEQUENCE_MISMATCH" in e for e in validate(r)))

    def test_wrong_order(self):
        r = valid()
        r["focus_evidence"][1], r["focus_evidence"][2] = r["focus_evidence"][2], r["focus_evidence"][1]
        self.assertTrue(any("INPUT_SEQUENCE_MISMATCH" in e for e in validate(r)))

    def test_wrong_language(self):
        r = valid()
        r["focus_evidence"][1]["language"] = "EN"
        self.assertTrue(any("INPUT_SEQUENCE_MISMATCH" in e for e in validate(r)))

    def test_wrong_phase(self):
        r = valid()
        r["focus_evidence"][1]["phase"] = "JP_TOGGLE"
        self.assertTrue(any("INPUT_SEQUENCE_MISMATCH" in e for e in validate(r)))

    def test_wrong_key(self):
        r = valid()
        r["focus_evidence"][1]["key"] = "{LEFT}"
        self.assertTrue(any("INPUT_SEQUENCE_MISMATCH" in e for e in validate(r)))

    def test_wrong_focus(self):
        r = valid()
        r["focus_evidence"][1]["foreground_pid"] = 999
        self.assertTrue(any("FOCUS_MISMATCH" in e for e in validate(r)))

    def test_malformed(self):
        r = valid()
        r["focus_evidence"][1] = None
        self.assertTrue(validate(r))


if __name__ == "__main__":
    unittest.main()
