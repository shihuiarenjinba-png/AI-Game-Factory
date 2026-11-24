"""Synthetic tests for the read-only GDK current-source intake contract."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))

from signal_sprint_gdk_current_source_intake import (
    FACTORY_REPOSITORY,
    LEGACY_REQUEST_ID,
    LEGACY_SOURCE_SHA,
    PR30_SOURCE_SHA,
    REQUIRED_WIN_LOSE_SHA,
    SOURCE_SHA,
    assess,
)

WORKFLOW_HEAD = "b" * 40


def ref(branch, sha=SOURCE_SHA):
    return sha + "\trefs/heads/" + branch + "\n"


def good_build():
    return {
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "product_source": SOURCE_SHA,
        "pr30_source_commit": PR30_SOURCE_SHA,
        "pr30_ancestry_verified": True,
        "build_provenance_verified": True,
        "independent_build_verified": True,
        "workflow_head_sha": WORKFLOW_HEAD,
        "run_status_at_verification": "completed",
        "run_conclusion": "success",
        "completed_run_required": True,
        "artifact_kind": "EXE_QA_UNSIGNED",
        "msix_status": "NOT_BUILT",
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "product_acceptance": False,
        "run_id": 45355246020,
        "artifact_id": 14901373959,
        "exe_size_bytes": 11453747,
        "artifact_exe_size_bytes": 11453747,
        "build_run_url": "https://github.com/" + FACTORY_REPOSITORY + "/actions/runs/45355246020",
        "expected_run_id": "45355246020",
        "expected_workflow_head": WORKFLOW_HEAD,
        "build_proof_artifact_id": 14904564932,
        "build_proof_artifact_digest": "sha256:1c72b4bd0efd49afad6c5f96fd1c50a29d2ac2139b642232c7279b64ae39a626",
        "build_proof_artifact_run_id": 45355246020,
        "build_proof_artifact_workflow_head_sha": WORKFLOW_HEAD,
        "build_proof_artifact_verified": True,
        "build_proof_artifact_zip_sha256": "1c72b4bd0efd49afad6c5f96fd1c50a29d2ac2139b642232c7279b64ae39a626",
        "build_proof_artifact_zip_size_bytes": 2171,
        "artifact_zip_size_bytes": 11203473,
        "exe_sha256": "35df3f636d9d5d8a3ee08b76e0a307ad0b01b1b4a2da8c1d503d300eef8fde83",
        "artifact_zip_sha256": "610711cb410a309dc12affb077246cfda17737bffa56103c50f2a6756cfa7b5d",
    }


def good_sdk():
    return {
        "schema": "signal-sprint-gdk-sdk-capability-v1",
        "status": "HOLD_GDK_SDK_ROOT_NOT_FOUND",
        "host_os": "Windows",
        "runner_scope": "WINDOWS_HOST_ONLY_NOT_PHYSICAL_GUI",
        "read_only": True,
        "workflow_head_sha": WORKFLOW_HEAD,
        "build_run_id": 45355246020,
        "makepkg_executed": False,
        "submission_validator_executed": False,
        "sdk_validation_executed": False,
        "package_built": False,
        "msixvc2_built": False,
        "signing_performed": False,
        "store_submitted": False,
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "ordinary_msix_allowed": False,
        "makepkg": None,
        "submission_validator": None,
    }


class GdkCurrentSourceIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "products" / "signal-sprint").mkdir(parents=True)
        (self.root / "proposals").mkdir()
        (self.root / "products" / "signal-sprint" / "manifest.json").write_text(
            json.dumps({"slug": "signal-sprint", "kind": "game", "entry": "main.py"}),
            encoding="utf-8",
        )
        (self.root / "products" / "signal-sprint" / "main.py").write_text(
            "print('Signal Sprint')\n", encoding="utf-8"
        )
        (self.root / "proposals" / "signal-sprint.json").write_text(
            json.dumps({"slug": "signal-sprint", "title": "Signal Sprint - Offline Route Puzzle"}),
            encoding="utf-8",
        )
        shutil.copyfile(ROOT / "package_intake_request.py", self.root / "package_intake_request.py")

    def run_assess(self, refs_text, **kwargs):
        values = {
            "checkout_head": SOURCE_SHA,
            "origin_url": "https://github.com/" + FACTORY_REPOSITORY + ".git",
            "remote_refs_text": refs_text,
            "remote_lookup_ok": True,
            "workflow_head_sha": WORKFLOW_HEAD,
            "build_attestation": good_build(),
            "sdk_capability": good_sdk(),
        }
        values.update(kwargs)
        return assess(self.root, **values)

    def test_no_exact_factory_branch_holds_without_generating_request(self):
        report = self.run_assess(ref("codex/signal-sprint-uia-fixture-20261110", "e" * 40))
        self.assertEqual(report["request"]["status"], "HOLD_FACTORY_SOURCE_REF_NOT_EXACT_FROZEN_SOURCE")
        self.assertFalse(report["request"]["request_generated"])
        self.assertIsNone(report["request"]["request_id"])
        self.assertEqual(
            report["request"]["candidate_request_id"],
            "game-signal-sprint-" + SOURCE_SHA,
        )
        self.assertEqual(report["remote_factory_refs"]["matching_exact_source_branches"], [])

    def test_exact_single_codex_ref_uses_existing_factory_builder(self):
        branch = "codex/signal-sprint-frozen-source-1a349faa"
        report = self.run_assess(ref(branch))
        self.assertEqual(report["request"]["status"], "CHECK_ONLY_REQUEST_DERIVED_NOT_SUBMITTED")
        self.assertTrue(report["request"]["request_generated"])
        self.assertFalse(report["request"]["request_submitted"])
        payload = report["request"]["request_payload"]
        self.assertEqual(payload["request_id"], "game-signal-sprint-" + SOURCE_SHA)
        self.assertEqual(payload["source_sha"], SOURCE_SHA)
        self.assertEqual(payload["source_branch"], branch)
        self.assertEqual(payload["product_type"], "GAME")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["source_repository"], FACTORY_REPOSITORY)

    def test_multiple_exact_refs_are_ambiguous_and_fail_closed(self):
        report = self.run_assess(
            ref("codex/signal-sprint-source-a") + ref("codex/signal-sprint-source-b")
        )
        self.assertEqual(report["request"]["status"], "HOLD_FACTORY_SOURCE_REF_AMBIGUOUS")
        self.assertFalse(report["request"]["request_generated"])

    def test_non_codex_exact_ref_is_not_accepted_as_game_work_branch(self):
        report = self.run_assess(ref("main"))
        self.assertEqual(report["request"]["status"], "HOLD_FACTORY_SOURCE_REF_NOT_GAME_WORK_BRANCH")
        self.assertFalse(report["request"]["request_generated"])

    def test_wrong_checkout_head_and_origin_are_rejected(self):
        report = self.run_assess(ref("codex/signal-sprint-source"),
                                 checkout_head="c" * 40)
        self.assertEqual(report["source_checkout"]["status"],
                         "HOLD_FACTORY_SOURCE_CHECKOUT_HEAD_MISMATCH")
        self.assertFalse(report["request"]["request_generated"])

        report = self.run_assess(ref("codex/signal-sprint-source"),
                                 origin_url="https://github.com/example/other.git")
        self.assertEqual(report["source_checkout"]["status"],
                         "HOLD_FACTORY_SOURCE_REPOSITORY_MISMATCH")
        self.assertFalse(report["request"]["request_generated"])

    def test_remote_lookup_failure_is_specific_hold(self):
        report = self.run_assess("", remote_lookup_ok=False)
        self.assertEqual(report["request"]["status"], "HOLD_FACTORY_REMOTE_REF_LOOKUP_FAILED")
        self.assertFalse(report["request"]["request_generated"])

    def test_malformed_remote_refs_fail_closed(self):
        report = self.run_assess("not-a-valid-ref\n")
        self.assertEqual(report["request"]["status"], "HOLD_FACTORY_REQUEST_DERIVATION_FAILED")
        self.assertFalse(report["request"]["request_generated"])

    def test_build_attestation_wrong_source_is_rejected(self):
        build = good_build()
        build["product_source"] = LEGACY_SOURCE_SHA
        report = self.run_assess(ref("codex/signal-sprint-source"),
                                 build_attestation=build)
        self.assertFalse(report["completed_build_attestation"]["verified"])
        self.assertIn("BUILD_ATTESTATION_PRODUCT_SOURCE_MISMATCH",
                      report["completed_build_attestation"]["errors"])

    def test_build_attestation_requires_proof_artifact_bindings(self):
        build = good_build()
        build["build_proof_artifact_run_id"] = 1
        report = self.run_assess(ref("codex/signal-sprint-source"),
                                 build_attestation=build)
        self.assertFalse(report["completed_build_attestation"]["verified"])
        self.assertIn("BUILD_ATTESTATION_PROOF_ARTIFACT_RUN_MISMATCH",
                      report["completed_build_attestation"]["errors"])

    def test_build_attestation_rejects_unverified_provenance_and_size_drift(self):
        build = good_build()
        build["independent_build_verified"] = False
        build["artifact_exe_size_bytes"] += 1
        report = self.run_assess(ref("codex/signal-sprint-source"),
                                 build_attestation=build)
        self.assertFalse(report["completed_build_attestation"]["verified"])
        self.assertIn("BUILD_ATTESTATION_INDEPENDENT_BUILD_VERIFIED_MISMATCH",
                      report["completed_build_attestation"]["errors"])
        self.assertIn("BUILD_ATTESTATION_ARTIFACT_EXE_SIZE_MISMATCH",
                      report["completed_build_attestation"]["errors"])

    def test_invalid_checkout_has_explicit_request_hold(self):
        report = self.run_assess(ref("codex/signal-sprint-source"),
                                 checkout_head="c" * 40)
        self.assertEqual(report["request"]["status"], "HOLD_FACTORY_CHECKOUT_INVALID")
        self.assertIsNone(report["request"]["source_branch"])

    def test_sdk_capability_wrong_run_is_rejected(self):
        sdk = good_sdk()
        sdk["build_run_id"] = 1
        report = self.run_assess(ref("codex/signal-sprint-source"),
                                 sdk_capability=sdk)
        self.assertFalse(report["sdk_capability"]["receipt_verified"])
        self.assertIn("SDK_CAPABILITY_BUILD_RUN_ID_MISMATCH",
                      report["sdk_capability"]["errors"])

    def test_legacy_identity_is_historical_and_never_rebound(self):
        report = self.run_assess("")
        self.assertEqual(report["legacy_identity"]["source_sha"], LEGACY_SOURCE_SHA)
        self.assertEqual(report["legacy_identity"]["request_id"], LEGACY_REQUEST_ID)
        self.assertEqual(report["legacy_identity"]["status"], "HISTORICAL_NOT_REBOUND")
        self.assertFalse(report["legacy_identity"]["reusable"])
        self.assertFalse(report["identity"]["legacy_identity_reused"])

    def test_route_is_gdk_only_and_no_side_effects_are_authorized(self):
        report = self.run_assess("")
        self.assertEqual(report["route"]["partner_center_selection"], "GDK_GAME")
        self.assertEqual(report["route"]["packaging_family"], "GDK")
        self.assertFalse(report["route"]["ordinary_msix_allowed"])
        self.assertFalse(report["authorization"]["gdk_package_authorized"])
        self.assertFalse(report["authorization"]["cas_write_performed"])
        self.assertFalse(report["authorization"]["sdk_executed"])
        self.assertFalse(report["authorization"]["msixvc2_built"])
        self.assertFalse(report["authorization"]["central_ledger_modified"])
        self.assertFalse(report["physical_gui_and_human_qa"]["physical_gui_verified"])
        self.assertFalse(report["physical_gui_and_human_qa"]["ci_pass_is_gui_pass"])

    def test_all_source_and_ledger_mutation_flags_remain_false(self):
        report = self.run_assess("")
        self.assertEqual(report["source_lineage"]["frozen_product_source_sha"], SOURCE_SHA)
        self.assertEqual(report["source_lineage"]["pr30_fixed_source_sha"], PR30_SOURCE_SHA)
        self.assertEqual(report["source_lineage"]["required_win_lose_revision_sha"],
                         REQUIRED_WIN_LOSE_SHA)
        self.assertFalse(report["authorization"]["product_source_modified"])
        self.assertFalse(report["authorization"]["pr30_source_modified"])
        self.assertFalse(report["central_ledger_handoff"]["ledger_write_performed"])


if __name__ == "__main__":
    unittest.main()
