"""Synthetic positive/negative archive fixtures; NOT real Windows GUI evidence."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
from signal_sprint_physical_qa_bundle import (
    IMMUTABLE, OLD_GDK_EXE, REQUEST, _expected_manifest, digest,
    validate_archive_structure,
)

HEAD = "a" * 40
RUN = "123456789"
EXE = b"MZ" + b"Q" * 131072
PNG = b"\x89PNG\r\n\x1a\n" + b"PNG-SENTINEL-TEST-ONLY"


class PhysicalQaArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "qa.zip"
        self.receipt = {
            "product": "Signal Sprint", "registration": "GDK_GAME",
            "immutable_source_sha": IMMUTABLE, "revision_sha": HEAD,
            "workflow_run_id": RUN, "exe_sha256": digest(EXE),
            "exe_size_bytes": len(EXE),
            "status": "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
            "sale_ready": False, "human_qa_pass": False, "cas_return_pass": False,
            "gdk_sdk_executed": False, "msixvc2_built": False, "store_submitted": False,
        }
        self.shots = [{"path": "screenshots/synthetic.png",
                       "sha256": digest(PNG), "size_bytes": len(PNG)}]
        self.manifest = _expected_manifest(self.receipt, HEAD, RUN, self.shots)
        self.write()

    def write(self, exe=EXE, png=PNG, omit=(), extra=None):
        receipt_bytes = json.dumps(self.receipt, sort_keys=True).encode()
        self.manifest["gui_receipt_sha256"] = digest(receipt_bytes)
        entries = {
            "manifest.json": json.dumps(self.manifest, sort_keys=True).encode(),
            "ui-revision-receipt.json": receipt_bytes,
            "SignalSprint.exe": exe,
            "screenshots/synthetic.png": png,
        }
        for key in omit:
            del entries[key]
        if extra:
            entries.update(extra)
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_STORED) as z:
            for name, data in entries.items():
                z.writestr(name, data)

    def errors(self, revision=HEAD):
        return validate_archive_structure(self.path, revision, RUN)[0]

    def test_synthetic_integrity_only_never_human_or_gdk_pass(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.manifest["original_request_id"], REQUEST)
        self.assertEqual(self.manifest["package_format"], "NOT_A_GDK_PACKAGE")
        self.assertTrue(all(value is False for value in self.manifest["release_gates"].values()))

    def test_rejects_modified_exe_with_valid_zip_crc(self):
        self.write(exe=EXE[:-1] + b"X")
        self.assertIn("EXE_SHA_OR_SIZE_MISMATCH", self.errors())

    def test_rejects_old_gdk_exe_sha_promotion(self):
        self.manifest["exe_sha256"] = OLD_GDK_EXE
        self.receipt["exe_sha256"] = OLD_GDK_EXE
        self.write()
        self.assertIn("OLD_GDK_EXE_SUBSTITUTION", self.errors())

    def test_rejects_manifest_revision_drift(self):
        self.manifest["build_head_sha"] = "f" * 40
        self.write()
        self.assertIn("MANIFEST_LINEAGE_build_head_sha", self.errors())

    def test_rejects_receipt_and_screenshot_tamper(self):
        self.receipt["exe_size_bytes"] += 1
        self.write()
        self.assertIn("GUI_RECEIPT_BINDING_exe_size_bytes", self.errors())
        self.receipt["exe_size_bytes"] -= 1
        self.write(png=PNG + b"modified")
        self.assertIn("SCREENSHOT_BYTES_MISMATCH", self.errors())

    def test_rejects_crc_corruption_not_just_manifest_sha(self):
        raw = self.path.read_bytes()
        self.assertIn(b"PNG-SENTINEL-TEST-ONLY", raw)
        self.path.write_bytes(raw.replace(b"PNG-SENTINEL-TEST-ONLY", b"PNG-SENTINEL-TEST-FAIL", 1))
        self.assertIn("ZIP_CRC_FAILED", self.errors())

    def test_rejects_missing_exe_and_unsafe_member(self):
        self.write(omit=("SignalSprint.exe",))
        self.assertIn("REQUIRED_BUNDLE_MEMBER_MISSING", self.errors())
        self.write(extra={"../escape.txt": b"evil"})
        self.assertIn("UNSAFE_ZIP_ENTRY", self.errors())

    def test_rejects_false_release_gate_and_route(self):
        self.manifest["release_gates"]["msixvc2_built"] = True
        self.manifest["package_format"] = "MSIX"
        self.write()
        self.assertIn("FORBIDDEN_RELEASE_GATE", self.errors())
        self.assertIn("MANIFEST_LINEAGE_package_format", self.errors())

    def test_rejects_wrong_expected_head_and_run(self):
        self.assertIn("GUI_RECEIPT_BINDING_revision_sha", self.errors("f" * 40))
        self.manifest["workflow_run_id"] = "999"
        self.write()
        self.assertIn("MANIFEST_LINEAGE_workflow_run_id", self.errors())


    def test_pinned_and_new_run_bundles_reject_swapped_lineage(self):
        # Structural-only synthetic ZIPs; real Artifact #13164091404 and
        # #13167801977 contain DIFFERENT executed EXEs. Do not swap labels.
        pinned = ("6f072dcf5369f7e56e235f7641d602e4fafc3417", "41489911241")
        newer = ("f5bc1e0d495bdcd65bf25fa370d7e68ef415d323", "41498959569")
        for actual, mislabeled_as in ((pinned, newer), (newer, pinned)):
            with self.subTest(actual=actual, mislabeled_as=mislabeled_as):
                self.manifest["build_head_sha"], self.manifest["workflow_run_id"] = actual
                self.receipt["revision_sha"], self.receipt["workflow_run_id"] = actual
                self.write()
                self.assertEqual(validate_archive_structure(self.path, *actual)[0], [])
                errors = validate_archive_structure(self.path, *mislabeled_as)[0]
                self.assertIn("MANIFEST_LINEAGE_build_head_sha", errors)
                self.assertIn("MANIFEST_LINEAGE_workflow_run_id", errors)
                self.assertIn("GUI_RECEIPT_BINDING_revision_sha", errors)
                self.assertIn("GUI_RECEIPT_BINDING_workflow_run_id", errors)

if __name__ == "__main__":
    unittest.main()
