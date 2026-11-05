import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).with_name("signal_sprint_strict_uia_receipt.py")
spec = importlib.util.spec_from_file_location("strict_uia", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def valid():
    r = dict(module.REQUIRED)
    r.update(immutable_source_sha=module.SOURCE, exe_sha256="a"*64,
             revision_sha="b"*40, workflow_run_id="123",
             status="GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
             en_screenshot_sha256="c"*64, jp_screenshot_sha256="d"*64,
             human_qa_pass=False, sale_ready=False,
             focus_evidence=[dict(event, expected_pid=123, foreground_pid=123,
                                  foreground_handle=456, owned_before_input=True)
                             for event in module.expected_inputs()])
    return r

class TestFailClosed(unittest.TestCase):
    def test_complete_check_only(self):
        self.assertEqual(module.validate(valid()), [])
    def test_missing_uia(self):
        r=valid(); r["en_buttons_in_workarea"]="HOLD_UIA_BUTTONS_UNAVAILABLE"
        self.assertIn("UIA_EN_BUTTONS_IN_WORKAREA_HOLD", module.validate(r))
    def test_missing_japanese_lost_text(self):
        r=valid(); r["lost_text_semantics"]="HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED"
        self.assertTrue(module.validate(r))
    def test_focus_unbound(self):
        r=valid(); r.pop("focus_evidence")
        self.assertIn("FOCUS_EVIDENCE_MISSING",module.validate(r))
    def test_wrong_foreground(self):
        r=valid(); r["focus_evidence"][10]["foreground_pid"]=999
        self.assertIn("FOCUS_MISMATCH_AT_10",module.validate(r))
    def test_old_exe_unbound(self):
        r=valid(); r["exe_sha256"]=""
        self.assertIn("EXE_SHA_UNBOUND",module.validate(r))
    def test_ci_unbound(self):
        r=valid(); r["workflow_run_id"]=None
        self.assertIn("CI_RUN_UNBOUND",module.validate(r))
    def test_fake_physical_pass(self):
        r=valid(); r["human_qa_pass"]=True
        self.assertIn("UNAUTHORIZED_PHYSICAL_OR_SALE_PASS",module.validate(r))
    def test_fake_sale_ready(self):
        r=valid(); r["sale_ready"]=True
        self.assertTrue(module.validate(r))
    def test_missing_screenshot(self):
        r=valid(); r["jp_screenshot_sha256"]=None
        self.assertIn("JP_SCREENSHOT_UNBOUND",module.validate(r))
    def test_source_mismatch(self):
        r=valid(); r["immutable_source_sha"]="0"*40
        self.assertIn("SOURCE_BINDING_MISMATCH",module.validate(r))

if __name__=="__main__":
    unittest.main()
