"""Offline synthetic Git/ZIP regression tests for the GDK Factory check-only gate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import gdk_post_cas_gate as gate


class GdkFactoryPostCasTests(unittest.TestCase):
    def cmd(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def commit(self, message):
        self.cmd("add", "-A")
        self.cmd("commit", "-m", message)
        return self.cmd("rev-parse", "HEAD")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "factory"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", gate.SOURCE_BRANCH, str(self.repo)], check=True)
        self.cmd("config", "user.email", "ci@example.invalid")
        self.cmd("config", "user.name", "CI")
        product = self.repo / "products/signal-sprint"
        product.mkdir(parents=True)
        (product / "main.py").write_text("print('pinned')\n")
        self.source = self.commit("immutable source")
        # CAS belongs on a separate branch: the immutable source ref must
        # remain at the original source SHA throughout the fixture.
        self.cmd("checkout", "-q", "-b",
                 "codex/game-signal-sprint-gdk-cas-" + self.source[:12])
        self.exe = b"pinned executable fixture"
        self.exe_sha = hashlib.sha256(self.exe).hexdigest()
        self.approved = {
            "schema_version": "1.0", "reviewed": True,
            "request_id": "game-signal-sprint-" + self.source,
            "product_type": "GAME", "slug": "signal-sprint",
            "source_factory": "AI-Game-Factory", "source_repository": gate.SOURCE_REPO,
            "source_branch": gate.SOURCE_BRANCH, "source_sha": self.source,
            "verified_source_sha": self.source, "package_sha256": self.exe_sha,
            "source": "partner_center_user_provided",
            "identity_source": "USER_PROVIDED_PARTNER_CENTER", "packaging_family": "GDK",
            "signature_status": "QA_UNSIGNED", "provided_at": "2026-10-28T12:00:00Z",
            **gate.IDENTITY,
        }
        store = product / "store"
        store.mkdir()
        (store / "approved-identity.json").write_text(json.dumps(self.approved))
        self.cas = self.commit("approved GDK Identity CAS")
        self.cmd("checkout", "-q", "-b", "codex/game-signal-sprint-gdk-build-fixture")
        docs = self.repo / "docs"
        docs.mkdir()
        (docs / "SIGNAL_SPRINT_GDK_BUILD.md").write_text("post-CAS GDK packaging\n")
        self.build = self.commit("GDK build branch preparation")
        self.artifact = self.root / "pinned.zip"
        self.make_artifact()
        self.artifact_sha = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        self.intake = {
            "schema_version": 1, "status": "GDK_BUILD_INPUT_CHECK_ONLY",
            "next_stage": "BUILD_GDK_MSIXVC_FROM_PINNED_EXE",
            "packaging_family": "GDK", "package_format": "MSIXVC_OR_MSIXVC2",
            "request_id": "game-signal-sprint-" + self.source,
            "source_repository": gate.SOURCE_REPO,
            "source_branch": gate.SOURCE_BRANCH, "source_sha": self.source,
            "cas_commit_sha": self.cas, "factory_head_sha": self.build,
            "identity": dict(gate.IDENTITY),
            "pinned_exe": {"artifact_zip_sha256": self.artifact_sha,
                           "executable_sha256": self.exe_sha,
                           "executable_bytes": len(self.exe), "executable": "SignalSprint.exe"},
            "package_version": None, "real_msixvc_built": False,
            "store_submitted": False,
        }
        self.intake_path = self.root / "intake.json"
        self.save_intake()
        self.patches = [patch.object(gate, "SOURCE_SHA", self.source),
                        patch.object(gate, "REQUEST_ID", "game-signal-sprint-" + self.source),
                        patch.object(gate, "EXE_SHA", self.exe_sha),
                        patch.object(gate, "ARTIFACT_SHA", self.artifact_sha)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def make_artifact(self):
        provenance = {"request_id": "game-signal-sprint-" + self.source,
                      "source_sha": self.source, "source_repository": gate.SOURCE_REPO,
                      "source_branch": gate.SOURCE_BRANCH, "product_type": "GAME",
                      "slug": "signal-sprint", "artifact_kind": "EXE_QA_UNSIGNED",
                      "executable": "SignalSprint.exe", "executable_sha256": self.exe_sha}
        request = {"request_id": "game-signal-sprint-" + self.source,
                   "source_sha": self.source, "source_repository": gate.SOURCE_REPO,
                   "source_branch": gate.SOURCE_BRANCH, "product_type": "GAME",
                   "slug": "signal-sprint", "dry_run": True}
        with zipfile.ZipFile(self.artifact, "w") as archive:
            archive.writestr("SignalSprint.exe", self.exe)
            archive.writestr("provenance.json", json.dumps(provenance))
            archive.writestr("provisioner-request.json", json.dumps(request))

    def save_intake(self):
        self.intake_path.write_text(json.dumps(self.intake))

    def run_gate(self):
        return gate.verify(self.repo, self.intake_path, self.artifact)

    def test_pass_is_check_only_not_real_package(self):
        result = self.run_gate()
        self.assertEqual(result["status"], "GDK_FACTORY_POST_CAS_CHECK_ONLY")
        self.assertEqual(result["source_sha"], self.source)
        self.assertEqual(result["factory_head_sha"], self.build)
        self.assertFalse(result["real_msixvc_built"])
        self.assertFalse(result["windows_e2e_pass"])

    def test_forged_intake_head_rejected(self):
        self.intake["factory_head_sha"] = "b" * 40
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "build HEAD"):
            self.run_gate()

    def test_forged_identity_rejected(self):
        self.intake["identity"]["store_id"] = "9PFAKE"
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "intake mismatch"):
            self.run_gate()

    def test_untrusted_success_status_rejected(self):
        self.intake["real_msixvc_built"] = True
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "intake mismatch"):
            self.run_gate()

    def test_pinned_zip_byte_change_rejected(self):
        self.artifact.write_bytes(self.artifact.read_bytes() + b"x")
        with self.assertRaisesRegex(gate.GateHold, "ZIP SHA"):
            self.run_gate()

    def test_no_unexpected_intake_fields(self):
        self.intake["store_submitted_by_ai"] = True
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "schema"):
            self.run_gate()

    def test_post_cas_change_and_revert_is_rejected(self):
        main = self.repo / "products/signal-sprint/main.py"
        main.write_text("print('changed')\n")
        self.commit("tamper with product")
        main.write_text("print('pinned')\n")
        self.build = self.commit("revert product change")
        self.intake["factory_head_sha"] = self.build
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "product change in history"):
            self.run_gate()

    def test_post_cas_unicode_product_edit_then_revert_rejected(self):
        # Git's default non-NUL diff output C-quotes non-ASCII paths.
        # A quoted path begins with a double quote, not 'products/'.
        unexpected = self.repo / "products/signal-sprint/日本語.txt"
        unexpected.write_text("unreviewed product change", encoding="utf-8")
        self.commit("tamper with non-ASCII product path")
        unexpected.unlink()
        self.build = self.commit("revert non-ASCII product path")
        self.intake["factory_head_sha"] = self.build
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "product change in history"):
            self.run_gate()

    def test_moved_immutable_source_branch_rejected(self):
        # A valid CAS parent is insufficient if the mutable source ref moved.
        self.cmd("branch", "-f", gate.SOURCE_BRANCH, self.cas)
        with self.assertRaisesRegex(gate.GateHold, "immutable source branch moved"):
            self.run_gate()

    def test_dedicated_cas_ref_mismatch_rejected(self):
        self.cmd("branch", "-f",
                 "codex/game-signal-sprint-gdk-cas-" + self.source[:12], self.source)
        with self.assertRaisesRegex(gate.GateHold, "dedicated CAS branch ref mismatch"):
            self.run_gate()

    def test_untracked_build_file_rejected(self):
        (self.repo / "unreviewed-output.bin").write_bytes(b"unreviewed")
        with self.assertRaisesRegex(gate.GateHold, "checkout is dirty"):
            self.run_gate()

    def test_post_cas_identity_byte_reformat_rejected(self):
        approved_path = self.repo / gate.APPROVED_PATH
        approved_path.write_text(json.dumps(self.approved, indent=2))
        self.build = self.commit("reformat approved identity without value change")
        self.intake["factory_head_sha"] = self.build
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "Identity bytes changed"):
            self.run_gate()

    def test_artifact_swap_during_zip_parse_rejected(self):
        original_zipfile = zipfile.ZipFile
        def swap_during_parse(*args, **kwargs):
            self.artifact.write_bytes(self.artifact.read_bytes() + b"changed")
            return original_zipfile(*args, **kwargs)
        with patch.object(gate.zipfile, "ZipFile", side_effect=swap_during_parse):
            with self.assertRaisesRegex(gate.GateHold, "ZIP changed during verification"):
                gate.check_artifact(self.artifact)

    def test_signed_claim_for_unsigned_exe_rejected(self):
        # Rebuild a clean synthetic CAS chain with a false signed claim.
        self.cmd("checkout", "-q", "-b",
                 "codex/game-signal-sprint-gdk-build-signature-fixture", self.source)
        approved_path = self.repo / gate.APPROVED_PATH
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        approved_path.write_text(json.dumps(dict(self.approved, signature_status="SIGNED")))
        self.cas = self.commit("CAS with false signed provenance")
        self.cmd("branch", "-f",
                 "codex/game-signal-sprint-gdk-cas-" + self.source[:12], self.cas)
        (self.repo / "docs").mkdir(exist_ok=True)
        (self.repo / "docs" / "SIGNAL_SPRINT_GDK_BUILD.md").write_text("GDK build plan\\n")
        self.build = self.commit("GDK build branch preparation")
        self.intake["cas_commit_sha"] = self.cas
        self.intake["factory_head_sha"] = self.build
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "QA_UNSIGNED"):
            self.run_gate()

    def test_legacy_factory_only_branch_name_rejected(self):
        # Provisioner requires codex/game-signal-sprint-gdk-build-*.
        # A branch accepted by the old Factory regex must fail closed.
        self.cmd("branch", "-m", "codex/game-gdk-signal-sprint-build-legacy")
        with self.assertRaisesRegex(gate.GateHold, "dedicated GDK"):
            self.run_gate()

    def test_malformed_canonical_build_branch_rejected(self):
        self.cmd("branch", "-m", "codex/game-signal-sprint-gdk-build-")
        with self.assertRaisesRegex(gate.GateHold, "dedicated GDK"):
            self.run_gate()

    def test_non_gdk_branch_rejected(self):
        self.cmd("branch", "-m", "codex/game-msix-build")
        with self.assertRaisesRegex(gate.GateHold, "dedicated GDK"):
            self.run_gate()

    def test_duplicate_json_keys_rejected(self):
        self.intake_path.write_text('{"status":"good","status":"bad"}')
        with self.assertRaisesRegex(gate.GateHold, "invalid JSON"):
            self.run_gate()

    def test_approved_identity_mutation_rejected(self):
        approved_path = self.repo / gate.APPROVED_PATH
        changed = dict(self.approved, store_id="9PFAKE")
        approved_path.write_text(json.dumps(changed))
        self.build = self.commit("change Identity")
        self.intake["factory_head_sha"] = self.build
        self.save_intake()
        with self.assertRaisesRegex(gate.GateHold, "Identity bytes changed"):
            self.run_gate()


if __name__ == "__main__":
    unittest.main()
