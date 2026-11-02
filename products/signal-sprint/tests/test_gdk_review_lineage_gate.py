"""Synthetic negative fixtures: never stand in for actual GDK or Windows GUI QA."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
from signal_sprint_gdk_review_gate import (
    ASSETS, IMMUTABLE, PINNED_EXE, PINNED_REQUEST, PINNED_ZIP,
    PR53_SHA, ROUTE, lineage_errors,
)


class GdkReviewLineageTests(unittest.TestCase):
    def setUp(self):
        self.revision = "a" * 40
        self.contract = {
            "provisioner_head_sha": PR53_SHA,
            "source_sha": IMMUTABLE,
            "pinned_request_id": PINNED_REQUEST,
            "pinned_exe_sha256": PINNED_EXE,
            "pinned_artifact_zip_sha256": PINNED_ZIP,
            "registration": "GDK_GAME",
            "routing": ROUTE.copy(),
            "asset_filenames": sorted(name for name, _ in ASSETS.values()),
            "expected_staging_payload_files": sorted(
                ["SignalSprint.exe", *(name for name, _ in ASSETS.values())]),
            "config_filename": "MicrosoftGame.config",
        }
        self.receipt = {
            "registration": "GDK_GAME",
            "immutable_source_sha": IMMUTABLE,
            "revision_sha": self.revision,
            "exe_sha256": "b" * 64,
            "work_area_bounds": [0, 0, 1024, 720],
            "window_bounds": [16, 16, 932, 675],
            "status": "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
            "human_qa_pass": False, "sale_ready": False,
            "cas_return_pass": False, "gdk_sdk_executed": False,
            "msixvc2_built": False, "store_submitted": False,
        }

    def errors(self, visual=()):
        return lineage_errors(self.receipt, self.contract, self.revision, visual)

    def test_synthetic_baseline_only_accepts_lineage_not_gdk_package(self):
        self.assertEqual(self.errors(), [])
        self.assertNotIn("gdk_staging_ready", self.receipt)
        self.assertNotIn("package_version", self.receipt)

    def test_rejects_review_exe_substituted_with_immutable_gdk_exe(self):
        self.receipt["exe_sha256"] = PINNED_EXE
        self.assertIn("REVIEW_EXE_MISBOUND_TO_IMMUTABLE_GDK_ARTIFACT", self.errors())

    def test_rejects_ordinary_msix_route(self):
        self.contract["routing"]["packaging_family"] = "MSIX"
        self.assertIn("GDK_ROUTE_MISMATCH", self.errors())

    def test_rejects_missing_asset_or_config_contract(self):
        self.contract["asset_filenames"].remove("SplashScreen.png")
        self.contract["config_filename"] = "AppxManifest.xml"
        self.assertIn("GDK_ASSET_INVENTORY_MISMATCH", self.errors())
        self.assertIn("GDK_CONFIG_NAME_MISMATCH", self.errors())

    def test_rejects_unapproved_version_assets_and_false_msixvc_ready(self):
        self.receipt.update(package_version="1.0.0.0", approved_assets=True,
                            msixvc_ready=True, gdk_sdk_validated=True)
        errors = self.errors()
        for field in ("package_version", "approved_assets", "msixvc_ready", "gdk_sdk_validated"):
            self.assertIn("REVIEW_UNAPPROVED_STAGING_CLAIM_" + field, errors)

    def test_rejects_workarea_overflow_even_if_gui_status_claims_success(self):
        self.receipt["window_bounds"] = [16, 16, 932, 745]
        self.assertIn("REVIEW_GUI_OUTSIDE_WORKAREA", self.errors())
        self.receipt["work_area_bounds"] = [0, 0, 1024, 768]
        self.assertIn("REVIEW_WORKAREA_NOT_MEASURED", self.errors())

    def test_rejects_wrong_pr53_head_and_source_request(self):
        self.contract["provisioner_head_sha"] = "f" * 40
        self.contract["source_sha"] = "f" * 40
        self.contract["pinned_request_id"] = "another-request"
        self.assertIn("PR53_CONTRACT_HEAD_MISMATCH", self.errors())
        self.assertIn("PR53_SOURCE_MISMATCH", self.errors())
        self.assertIn("PR53_REQUEST_MISMATCH", self.errors())

    def test_rejects_review_head_or_source_drift(self):
        self.receipt["revision_sha"] = IMMUTABLE
        self.receipt["immutable_source_sha"] = "f" * 40
        self.assertIn("REVIEW_REVISION_HEAD_MISMATCH", self.errors())
        self.assertIn("REVIEW_IMMUTABLE_SOURCE_MISMATCH", self.errors())

    def test_rejects_forged_sale_ready_and_sdk(self):
        self.receipt["sale_ready"] = True
        self.receipt["gdk_sdk_executed"] = True
        self.assertIn("REVIEW_FALSE_DOWNSTREAM_CLAIM_sale_ready", self.errors())
        self.assertIn("REVIEW_FALSE_DOWNSTREAM_CLAIM_gdk_sdk_executed", self.errors())

    def test_propagates_actual_gui_screenshot_sha_or_exe_mismatch(self):
        self.assertIn("SCREENSHOT_SHA_MISMATCH", self.errors(["SCREENSHOT_SHA_MISMATCH"]))
        self.assertIn("EXE_BYTES_MISMATCH", self.errors(["EXE_BYTES_MISMATCH"]))


if __name__ == "__main__":
    unittest.main()
