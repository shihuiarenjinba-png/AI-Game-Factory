"""Regression fixture for Signal Sprint Windows step10 UIA gate.

Run: python -m unittest qa.test_signal_sprint_step10_fixture
This tests receipt classification, not Windows UIA or product accessibility.
"""
import unittest

FAILED_CHECKS = ("en_buttons", "jp_buttons", "jp_lost_text", "en_lost_text")
GOOD = {
    "en_buttons_in_workarea": "REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY",
    "jp_buttons_in_workarea": "REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY",
    "en_lost_text_semantics": "UIAUTOMATION_EN_LOST_TEXT_OBSERVED",
    "lost_text_semantics": "UIAUTOMATION_JP_LOST_TEXT_OBSERVED",
}
FIELDS = dict(zip(FAILED_CHECKS, GOOD.keys()))


def classify(receipt):
    """Fail closed on absent fields, HOLD values, and non-exact success markers."""
    return [name for name, field in FIELDS.items()
            if receipt.get(field) != GOOD[field]]


class Step10RegressionFixture(unittest.TestCase):
    def test_old_step10_four_failures(self):
        old = {field: "HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED"
               for field in FIELDS.values()}
        old["en_buttons_in_workarea"] = "HOLD_UIA_FIVE_BUTTONS_NOT_EXPOSED"
        old["jp_buttons_in_workarea"] = "HOLD_UIA_FIVE_BUTTONS_NOT_EXPOSED"
        self.assertEqual(classify(old), list(FAILED_CHECKS))

    def test_clean_receipt(self):
        self.assertEqual(classify(dict(GOOD)), [])

    def test_each_failure_is_independent(self):
        for name, field in FIELDS.items():
            with self.subTest(name=name):
                receipt = dict(GOOD)
                receipt[field] = "HOLD_UNVERIFIED"
                self.assertEqual(classify(receipt), [name])

    def test_missing_fields_fail_closed(self):
        self.assertEqual(classify({}), list(FAILED_CHECKS))

    def test_weak_claim_does_not_pass(self):
        receipt = dict(GOOD)
        receipt["en_buttons_in_workarea"] = "OBSERVED_NOT_CONSUMER_CERTIFIED"
        self.assertEqual(classify(receipt), ["en_buttons"])


if __name__ == "__main__":
    unittest.main()
