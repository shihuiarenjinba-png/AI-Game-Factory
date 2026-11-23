#!/usr/bin/env python3
"""Deterministic tests for the read-only GDK SDK capability probe."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))

from signal_sprint_gdk_sdk_capability_probe import probe


def valid_version(_path):
    return {"file_version": "10.0.26100.1", "product_version": "10.0.26100.1"}


def valid_signature(_path):
    return {
        "status": "Valid",
        "signer_subject": "CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, S=Washington, C=US",
        "signer_thumbprint": "A" * 40,
    }


class GdkSdkCapabilityProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sdk"
        self.bin = self.root / "bin"
        self.bin.mkdir(parents=True)
        self.makepkg = self.bin / "makepkg.exe"
        self.validator = self.bin / "SubmissionValidator.dll"
        self.makepkg.write_bytes(b"synthetic makepkg bytes")
        self.validator.write_bytes(b"synthetic validator bytes")

    def tearDown(self):
        self.tmp.cleanup()

    def run_probe(self, **overrides):
        values = {
            "sdk_root": self.root,
            "makepkg_path": self.makepkg,
            "expected_version": "10.0.26100.1",
            "version_reader": valid_version,
            "signature_reader": valid_signature,
            "host_os": "Windows",
            "workflow_head_sha": "b" * 40,
            "build_run_id": 12345,
        }
        values.update(overrides)
        return probe(**values)

    def test_missing_sdk_root_is_hold(self):
        missing = self.root / "not-installed"
        result = self.run_probe(sdk_root=missing, makepkg_path=None)
        self.assertEqual(result["status"], "HOLD_GDK_SDK_ROOT_NOT_FOUND")

    def test_missing_makepkg_is_hold(self):
        self.makepkg.unlink()
        result = self.run_probe(makepkg_path=None)
        self.assertEqual(result["status"], "HOLD_MAKEPKG_NOT_FOUND")

    def test_malformed_makepkg_path_outside_sdk_root_is_rejected(self):
        outside = Path(self.tmp.name) / "outside" / "makepkg.exe"
        outside.parent.mkdir()
        outside.write_bytes(b"outside")
        result = self.run_probe(makepkg_path=outside)
        self.assertEqual(result["status"], "HOLD_MAKEPKG_PATH_UNTRUSTED")

    def test_sdk_version_mismatch_is_hold(self):
        result = self.run_probe(expected_version="10.0.9999.9")
        self.assertEqual(result["status"], "HOLD_GDK_SDK_VERSION_MISMATCH")

    def test_missing_expected_version_is_not_implicitly_approved(self):
        result = self.run_probe(expected_version="")
        self.assertEqual(result["status"], "HOLD_GDK_SDK_VERSION_NOT_APPROVED")

    def test_missing_submission_validator_is_hold(self):
        self.validator.unlink()
        result = self.run_probe()
        self.assertEqual(result["status"], "HOLD_SUBMISSION_VALIDATOR_MISSING")

    def test_non_microsoft_signature_is_rejected(self):
        result = self.run_probe(
            signature_reader=lambda _path: {
                "status": "Valid",
                "signer_subject": "CN=Untrusted Publisher",
            }
        )
        self.assertEqual(result["status"], "HOLD_MAKEPKG_SIGNATURE_NOT_MICROSOFT_VALID")

    def test_complete_fixture_is_capability_only_and_has_no_side_effects(self):
        result = self.run_probe()
        self.assertEqual(result["status"], "PASS_TOOLCHAIN_CAPABILITY_ONLY")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["makepkg_executed"])
        self.assertFalse(result["submission_validator_executed"])
        self.assertFalse(result["sdk_validation_executed"])
        self.assertFalse(result["package_built"])
        self.assertFalse(result["msixvc2_built"])
        self.assertFalse(result["signing_performed"])
        self.assertFalse(result["store_submitted"])
        self.assertFalse(result["physical_gui_verified"])
        self.assertFalse(result["gdk_package_verified"])
        self.assertFalse(result["ordinary_msix_allowed"])
        self.assertEqual(result["makepkg"]["sha256"], result["makepkg"]["sha256"])
        self.assertEqual(result["build_run_id"], 12345)


if __name__ == "__main__":
    unittest.main(verbosity=2)
