import unittest
from qa.signal_sprint_revision_gate import verify_revision, FROZEN_SOURCE, REQUIRED_REVISION


class RevisionGateTests(unittest.TestCase):
    def test_valid_ancestor(self):
        result = verify_revision(lambda rev, src: {
            "status": "ahead", "merge_base_commit": {"sha": rev}})
        self.assertEqual(result["status"], "PASS_REVISION_ANCESTRY_ONLY")
        self.assertFalse(result["physical_gui_verified"])

    def test_frozen_source_is_behind_revision(self):
        with self.assertRaisesRegex(ValueError, "REVISION_NOT_IN_PRODUCT_SOURCE"):
            verify_revision(lambda rev, src: {
                "status": "behind", "merge_base_commit": {"sha": src}})

    def test_missing_comparison(self):
        with self.assertRaisesRegex(ValueError, "REVISION_NOT_IN_PRODUCT_SOURCE"):
            verify_revision(lambda rev, src: {})

    def test_wrong_merge_base(self):
        with self.assertRaisesRegex(ValueError, "REVISION_NOT_IN_PRODUCT_SOURCE"):
            verify_revision(lambda rev, src: {
                "status": "ahead", "merge_base_commit": {"sha": FROZEN_SOURCE}})

    def test_source_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "FROZEN_SOURCE_MISMATCH"):
            verify_revision(lambda rev, src: {}, source=REQUIRED_REVISION)


if __name__ == "__main__":
    unittest.main()
