"""Synthetic negative fixtures: no CAS, SDK, MSIXVC2, or physical QA is performed."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
from signal_sprint_gdk_post_identity_preflight import (
    IMMUTABLE, PINNED_REQUEST, PR53_SHA, ROUTE, _json, assess,
)


class GdkPostIdentityPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contract = {
            "provisioner_head_sha": PR53_SHA, "source_sha": IMMUTABLE,
            "pinned_request_id": PINNED_REQUEST, "routing": ROUTE, "registration": "GDK_GAME",
        }
        self.identity = {
            "store_id": "9N21MJM7S57P",
            "name": "OkinawaDesktopTools.SignalSprint",
            "publisher": "CN=46263F21-A700-41DB-8C9B-114C22FB82FC",
            "publisher_display_name": "Okinawa Desktop Tools",
            "package_family_name": "OkinawaDesktopTools.SignalSprint_j8yefg9jgfh58",
            "package_sid": "S-1-15-2-1437967488-3265478925-1925977903-994526844-2895000717-1943620661-378024715",
            "xbox_title_id": "68721417",
            "xbox_scid": "00000000-0000-0000-0000-000068721417",
            "msa_app_id": "39852fc3-fa46-4bda-88aa-b35385488ced",
        }
        first = patch("signal_sprint_gdk_post_identity_preflight.load_pr53_contract",
                      return_value=self.contract)
        second = patch("signal_sprint_gdk_post_identity_preflight._identity_expected",
                       return_value=self.identity)
        first.start()
        second.start()
        self.addCleanup(first.stop)
        self.addCleanup(second.stop)

    def write(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def gate(self, **kwargs):
        return assess(self.root, **kwargs)

    def test_baseline_returns_specific_hold_not_ready(self):
        report = self.gate()
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["gates"]["source_request_route"]["status"], "CHECK_ONLY")
        for name in ("identity", "cas", "version", "assets_and_staging", "sdk_toolchain",
                     "sdk_validation", "signing", "msixvc2", "physical_human_qa"):
            self.assertEqual(report["gates"][name]["status"], "HOLD", name)
        self.assertFalse(report["sale_ready"])
        self.assertFalse(report["msixvc2_built"])

    def test_source_request_drift_rejected(self):
        self.contract["pinned_request_id"] = "other"
        self.assertEqual(self.gate()["gates"]["source_request_route"]["status"], "HOLD")

    def test_exact_identity_is_only_check_not_cas(self):
        path = self.write("identity.json", {
            **self.identity, "source_sha": IMMUTABLE, "request_id": PINNED_REQUEST,
            "packaging_family": "GDK", "source": "partner_center_user_provided",
        })
        result = self.gate(identity_json=path)
        self.assertEqual(result["gates"]["identity"]["status"], "CHECK_ONLY")
        self.assertEqual(result["gates"]["cas"]["status"], "HOLD")
        self.assertFalse(result["cas_return_pass"])
        bad = json.loads(path.read_text(encoding="utf-8"))
        bad["store_id"] = "9NFAKE000000"
        self.write("identity.json", bad)
        self.assertEqual(self.gate(identity_json=path)["gates"]["identity"]["status"], "HOLD")
        bad["store_id"] = self.identity["store_id"]
        bad["packaging_family"] = "MSIX"
        self.write("identity.json", bad)
        self.assertEqual(self.gate(identity_json=path)["gates"]["identity"]["status"], "HOLD")

    def test_reviewed_version_record_never_authorizes_build(self):
        version = self.write("version.json", {
            "package_version": "1.2.3.0", "reviewed": True,
            "request_id": PINNED_REQUEST, "source_sha": IMMUTABLE,
        })
        result = self.gate(version_json=version, cas_sha="a" * 40, build_sha="b" * 40)
        self.assertEqual(result["gates"]["version"]["status"], "CHECK_ONLY")
        self.assertEqual(result["gates"]["cas"]["status"], "HOLD")
        self.assertEqual(result["gates"]["msixvc2"]["status"], "HOLD")
        self.write("version.json", {
            "package_version": "1.2.3.1", "reviewed": True,
            "request_id": PINNED_REQUEST, "source_sha": IMMUTABLE,
        })
        self.assertEqual(self.gate(version_json=version)["gates"]["version"]["status"], "HOLD")

    def test_gui_exe_or_extra_file_cannot_be_gdk_staging(self):
        folder = self.root / "staging"
        folder.mkdir()
        for name in ("SignalSprint.exe", "MicrosoftGame.config", "StoreLogo.png",
                     "Logo.png", "SmallLogo.png", "SplashScreen.png"):
            (folder / name).write_bytes(b"not-the-pinned-GDK-payload")
        self.assertEqual(self.gate(staging_dir=folder)["gates"]["assets_and_staging"]["status"], "HOLD")
        (folder / "unreviewed.dll").write_bytes(b"x")
        result = self.gate(staging_dir=folder)
        self.assertIn("GDK_SIX_FILE_INVENTORY_INCOMPLETE_OR_EXTRA",
                      result["gates"]["assets_and_staging"]["detail"])

    def test_forged_sdk_and_signing_pass_rejected(self):
        sdk = self.write("sdk.json", {"gdk_sdk_validated": True, "real_msixvc_built": True})
        signing = self.write("signing.json", {"signed": True, "signature_valid": True})
        result = self.gate(sdk_result_json=sdk, signing_json=signing)
        self.assertEqual(result["gates"]["sdk_validation"]["reason"],
                         "UNTRUSTED_SDK_RESULT_CANNOT_CLAIM_PASS")
        self.assertEqual(result["gates"]["signing"]["reason"],
                         "UNTRUSTED_SIGNING_JSON_NOT_SIGNATURE_VERIFICATION")
        self.assertFalse(result["gdk_sdk_validated"])

    def test_duplicate_json_keys_and_symlink_rejected(self):
        path = self.root / "duplicate.json"
        path.write_text('{"status":"GOOD","status":"FORGED"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            _json(path)
        link = self.root / "linked.json"
        try:
            link.symlink_to(path)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaisesRegex(ValueError, "LINKED_EVIDENCE_PATH"):
            _json(link)


if __name__ == "__main__":
    unittest.main()
