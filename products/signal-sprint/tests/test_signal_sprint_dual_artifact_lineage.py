"""Synthetic fixtures only: these NEVER constitute physical Windows evidence."""
import copy
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))
import signal_sprint_dual_artifact_lineage as qa


def fixture(root, label, exe=b"synthetic-EXE", change=None):
    profile = dict(artifact=11 if label == "pinned" else 22,
                   gui_artifact=33 if label == "pinned" else 44,
                   run="100" if label == "pinned" else "200",
                   head="a" * 40 if label == "pinned" else "b" * 40,
                   exe_sha=qa.sha(exe), exe_size=len(exe))
    shots = []
    for name in qa.PHASES.values():
        if name not in [s["path"] for s in shots]:
            data = b"\x89PNG\r\n\x1a\nsynthetic-" + name.encode()
            shots.append(dict(path=name, sha256=qa.sha(data), size_bytes=len(data)))
    receipt = dict(revision_sha=profile["head"], workflow_run_id=profile["run"],
                   immutable_source_sha=qa.SOURCE, registration="GDK_GAME",
                   exe_sha256=profile["exe_sha"], exe_size_bytes=profile["exe_size"],
                   dpi_percent=100, target_dpi_percent=100, human_qa_pass=False,
                   sale_ready=False, msixvc2_built=False, gdk_sdk_executed=False,
                   ui_automation_controls="HOLD_UNVERIFIED",
                   dpi_125="HOLD_UNMEASURED", dpi_150="HOLD_UNMEASURED",
                   lost_text_semantics="HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED",
                   en_lost_text_semantics="HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED")
    for key, name in qa.PHASES.items():
        receipt[key] = next(s["sha256"] for s in shots if s["path"] == name)
    manifest = dict(build_head_sha=profile["head"], workflow_run_id=profile["run"],
                    immutable_source_sha=qa.SOURCE, original_request_id=qa.REQUEST,
                    registration="GDK_GAME", partner_center_route="GDK game",
                    package_format="NOT_A_GDK_PACKAGE",
                    exe_sha256=profile["exe_sha"], exe_size_bytes=profile["exe_size"],
                    consumer_human_qa="HOLD", real_os_dpi_125_150="HOLD",
                    gdk_sdk_status="HOLD_NOT_EXECUTED",
                    release_gates={k: False for k in qa.RELEASE}, screenshots=shots)
    if change:
        change(manifest, receipt, profile)
    receipt_bytes = json.dumps(receipt).encode()
    manifest["gui_receipt_sha256"] = qa.sha(receipt_bytes)
    inner_file = io.BytesIO()
    with zipfile.ZipFile(inner_file, "w", zipfile.ZIP_STORED) as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("ui-revision-receipt.json", receipt_bytes)
        z.writestr("SignalSprint.exe", exe)
        for shot in shots:
            z.writestr(shot["path"], b"\x89PNG\r\n\x1a\nsynthetic-" + shot["path"].encode())
    inner_bytes = inner_file.getvalue()
    profile["inner_sha"] = qa.sha(inner_bytes)
    outer_file = root / (label + ".zip")
    with zipfile.ZipFile(outer_file, "w", zipfile.ZIP_STORED) as z:
        z.writestr("SignalSprint-physical-qa.zip", inner_bytes)
    profile["outer_sha"] = qa.sha(outer_file.read_bytes())
    return outer_file, profile


class DualLineageTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.pinned, self.p = fixture(self.root, "pinned", b"first-revision")
        self.new, self.n = fixture(self.root, "candidate", b"second-revision")

    def compare(self, p=None, n=None, pinned=None, candidate=None):
        return qa.compare(pinned or self.pinned, candidate or self.new,
                          {"pinned": p or self.p, "candidate": n or self.n})

    def test_real_metadata_is_pinned_to_two_different_exe_hashes(self):
        self.assertEqual(qa.PROFILES["pinned"]["artifact"], 13180405918)
        self.assertEqual(qa.PROFILES["candidate"]["artifact"], 13185196046)
        self.assertNotEqual(qa.PROFILES["pinned"]["exe_sha"], qa.PROFILES["candidate"]["exe_sha"])
        self.assertNotEqual(qa.PROFILES["pinned"]["head"], qa.SOURCE)
        self.assertNotEqual(qa.PROFILES["candidate"]["head"], qa.SOURCE)

    def test_distinct_valid_synthetic_lineages_never_physical_pass(self):
        report = self.compare()
        self.assertEqual(report["status"], "DISTINCT_EXE_REVISIONS_VERIFIED")
        self.assertEqual(report["physical_qa_status"], "PHYSICAL_HOLD")
        self.assertFalse(report["sale_ready"])
        self.assertFalse(report["gdk_package_ready"])

    def test_same_bytes_different_run_is_reported_not_assumed(self):
        new, n = fixture(self.root, "candidate", b"first-revision")
        report = self.compare(n=n, candidate=new)
        self.assertEqual(report["status"], "SAME_EXE_BYTES_VERIFIED_DIFFERENT_RUNS")
        self.assertEqual(report["physical_qa_status"], "PHYSICAL_HOLD")

    def test_old_bundle_substituted_as_new_is_rejected(self):
        self.assertEqual(self.compare(candidate=self.pinned)["status"], "LINEAGE_HOLD")

    def test_new_bundle_substituted_as_pinned_is_rejected(self):
        self.assertEqual(self.compare(pinned=self.new)["status"], "LINEAGE_HOLD")

    def test_missing_artifact_is_hold(self):
        self.assertEqual(self.compare(candidate=self.root / "absent.zip")["status"], "LINEAGE_HOLD")

    def test_original_source_change_is_rejected(self):
        f, n = fixture(self.root, "candidate", change=lambda m, r, p: m.update(immutable_source_sha="f" * 40))
        self.assertIn("CANDIDATE_MANIFEST_BINDING_immutable_source_sha", self.compare(n=n)["errors"])

    def test_request_change_is_rejected(self):
        f, n = fixture(self.root, "candidate", change=lambda m, r, p: m.update(original_request_id="forged"))
        self.assertIn("CANDIDATE_MANIFEST_BINDING_original_request_id", self.compare(n=n)["errors"])

    def test_revision_head_mislabel_is_rejected(self):
        f, n = fixture(self.root, "candidate", change=lambda m, r, p: m.update(build_head_sha=qa.SOURCE))
        self.assertIn("CANDIDATE_MANIFEST_BINDING_build_head_sha", self.compare(n=n)["errors"])

    def test_gui_receipt_wrong_exe_is_rejected(self):
        f, n = fixture(self.root, "candidate", change=lambda m, r, p: r.update(exe_sha256="0" * 64))
        self.assertIn("CANDIDATE_GUI_RECEIPT_BINDING_exe_sha256", self.compare(n=n)["errors"])

    def test_fake_dpi_and_uia_pass_are_rejected(self):
        def forge(m, r, p):
            r["dpi_125"] = "PASS"
            r["ui_automation_controls"] = "PASS"
        f, n = fixture(self.root, "candidate", change=forge)
        self.assertIn("CANDIDATE_PHYSICAL_DPI_FALSE_PASS", self.compare(n=n)["errors"])
        self.assertIn("CANDIDATE_UIA_FALSE_PASS", self.compare(n=n)["errors"])

    def test_fake_gdk_ready_is_rejected(self):
        f, n = fixture(self.root, "candidate", change=lambda m, r, p: m["release_gates"].update(msixvc2_built=True))
        self.assertIn("CANDIDATE_RELEASE_GATE_FALSE_PASS", self.compare(n=n)["errors"])

    def test_screenshot_receipt_swap_is_rejected(self):
        f, n = fixture(self.root, "candidate", change=lambda m, r, p: r.update(en_window_sha256="f" * 64))
        self.assertIn("CANDIDATE_GUI_PHASE_RECEIPT_MISMATCH_en_window_sha256", self.compare(n=n)["errors"])

    def test_missing_screenshot_is_rejected(self):
        def remove(m, r, p):
            m["screenshots"] = m["screenshots"][:-1]
        f, n = fixture(self.root, "candidate", change=remove)
        self.assertEqual(self.compare(n=n)["status"], "LINEAGE_HOLD")

    def test_old_gdk_sha_cannot_be_approved(self):
        n = dict(self.n, exe_sha=qa.OLD_GDK_EXE)
        self.assertIn("CANDIDATE_OLD_GDK_OR_SOURCE_MISLABELED_AS_REVIEW_EXE",
                      self.compare(n=n)["errors"])

    def test_outer_crc_corruption_rejected_even_with_rehashed_outer_digest(self):
        raw = bytearray(self.new.read_bytes())
        i = raw.find(b"second-revision")
        self.assertGreater(i, 0)
        raw[i] ^= 1
        self.new.write_bytes(raw)
        n = dict(self.n, outer_sha=qa.sha(raw))
        self.assertIn("CANDIDATE_ZIP_CRC_INVALID", self.compare(n=n)["errors"])

    def test_outer_digest_mutation_is_rejected(self):
        raw = self.new.read_bytes() + b"trailer"
        self.new.write_bytes(raw)
        self.assertIn("CANDIDATE_OUTER_ARTIFACT_DIGEST_MISMATCH", self.compare()["errors"])


if __name__ == "__main__":
    unittest.main()
