"""Synthetic contract tests for the GDK package-readiness HOLD receipt."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "qa"))

from signal_sprint_gdk_package_readiness import (
    GDK_SOURCE_SHA,
    PINNED_EXE,
    PINNED_ZIP,
    QA_SOURCE_SHA,
    REQUIRED_WIN_LOSE_SHA,
    compose_receipt,
    _validate_build_proof,
)


def good_build():
    return {
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "independent_build_verified": True,
        "build_provenance_verified": True,
        "run_id": 45213585866,
        "run_status_at_verification": "completed",
        "run_conclusion": "success",
        "completed_run_required": True,
        "workflow_head_sha": "5" * 40,
        "product_source_sha": QA_SOURCE_SHA,
        "pr30_source_sha": "a377043d3c9ab0c71d9a100cdb841dd7000313b9",
        "artifact_id": 14836513477,
        "artifact_zip_sha256": "4d" * 32,
        "artifact_zip_size_bytes": 11203405,
        "exe_sha256": "18" * 32,
        "exe_size_bytes": 11453526,
        "artifact_kind": "EXE_QA_UNSIGNED",
        "msix_status": "NOT_BUILT",
        "gdk_package_verified": False,
        "physical_gui_verified": False,
    }


def good_build_proof():
    return {
        "schema": "signal-sprint-independent-build-v1",
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "product_source": QA_SOURCE_SHA,
        "pr30_source_commit": "a377043d3c9ab0c71d9a100cdb841dd7000313b9",
        "build_job_name": "windows-frozen-source-exe",
        "artifact_kind": "EXE_QA_UNSIGNED",
        "msix_status": "NOT_BUILT",
        "pr30_ancestry_verified": True,
        "build_provenance_verified": True,
        "independent_build_verified": True,
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "completed_run_required": True,
        "run_status_at_verification": "completed",
        "run_conclusion": "success",
        "run_id": 45257822887,
        "artifact_id": 14857858227,
        "exe_size_bytes": 11452658,
        "artifact_exe_size_bytes": 11452658,
        "artifact_zip_size_bytes": 11202558,
        "exe_sha256": "76c87c301ff50700f96879dc30121f9b1d3ad738837a7965831f53cc41fe92a3",
        "artifact_zip_sha256": "72a48a02691cefcbca14a131474d01064ed2e9f0d6bb25a15ed7077f63b6054b",
        "workflow_head_sha": "5" * 40,
    }


def good_build_env():
    return {
        "WINDOWS_BUILD_RESULT": "success",
        "INDEPENDENT_BUILD_RESULT": "success",
        "BUILD_RUN_ID": "45257822887",
        "BUILD_ARTIFACT_ID": "14857858227",
        "WORKFLOW_HEAD_SHA": "5" * 40,
        "PRODUCT_SOURCE_SHA": QA_SOURCE_SHA,
        "PR30_SOURCE_SHA": "a377043d3c9ab0c71d9a100cdb841dd7000313b9",
        "BUILD_EXE_SHA256": "76c87c301ff50700f96879dc30121f9b1d3ad738837a7965831f53cc41fe92a3",
    }


def validate_build_proof(proof):
    import json
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "completed-build-attestation.json"
        path.write_text(json.dumps(proof), encoding="utf-8")
        return _validate_build_proof(path, good_build_env())


def good_contract():
    return {
        "provisioner_pr": 53,
        "provisioner_head_sha": "ac4bd6d4fed975dae139a6638b0b7f78e09e6d71",
        "source_sha": GDK_SOURCE_SHA,
        "pinned_request_id": "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e",
        "pinned_exe_sha256": PINNED_EXE,
        "pinned_artifact_zip_sha256": PINNED_ZIP,
        "registration": "GDK_GAME",
        "routing": {
            "schema_version": 1,
            "packaging_family": "GDK",
            "package_format": "MSIXVC_OR_MSIXVC2",
            "next_stage": "GDK_SDK_VALIDATE_THEN_MAKEPKG_PC",
        },
        "asset_filenames": ["Logo.png", "SmallLogo.png", "SplashScreen.png", "StoreLogo.png"],
        "expected_staging_payload_files": [
            "Logo.png", "SignalSprint.exe", "SmallLogo.png",
            "SplashScreen.png", "StoreLogo.png",
        ],
        "config_filename": "MicrosoftGame.config",
    }


def good_preflight():
    return {
        "status": "HOLD",
        "gates": {
            "identity": {"status": "HOLD", "reason": "APPROVED_IDENTITY_FILE_NOT_SUPPLIED_CAS_UNVERIFIED"},
            "cas": {"status": "HOLD", "reason": "ACTUAL_IDENTITY_ONLY_CAS_AND_POST_CAS_BUILD_NOT_VERIFIED"},
            "version": {"status": "HOLD", "reason": "EXPLICIT_APPROVED_GDK_PACKAGE_VERSION_MISSING"},
            "assets_and_staging": {"status": "HOLD", "reason": "SIX_REAL_GDK_STAGING_FILES_NOT_SUPPLIED"},
            "sdk_toolchain": {"status": "HOLD", "reason": "GDK_SDK_WINDOWS_HOST_REQUIRED"},
            "sdk_validation": {"status": "HOLD", "reason": "OFFICIAL_GDK_SDK_VALIDATION_NOT_EXECUTED_OR_EVIDENCED"},
            "signing": {"status": "HOLD", "reason": "GDK_SIGNING_REVIEW_OR_VALID_SIGNATURE_EVIDENCE_MISSING"},
            "msixvc2": {"status": "HOLD", "reason": "REAL_MSIXVC2_BUILD_AND_BYTES_NOT_VERIFIED"},
            "physical_human_qa": {"status": "HOLD", "reason": "JA_EN_DPI_125_150_AND_FIRST30_PHYSICAL_HUMAN_QA_NOT_VERIFIED"},
        },
    }


class GdkPackageReadinessTests(unittest.TestCase):
    def compose(self, **overrides):
        values = {
            "contract": good_contract(),
            "identity_fields": {
                "store_id": "not-emitted",
                "name": "not-emitted",
                "publisher": "not-emitted",
                "publisher_display_name": "not-emitted",
                "package_family_name": "not-emitted",
                "package_sid": "not-emitted",
                "xbox_title_id": "not-emitted",
                "xbox_scid": "not-emitted",
                "msa_app_id": "not-emitted",
            },
            "preflight": good_preflight(),
            "build": good_build(),
            "ancestry": {
                "pr30_source_is_ancestor_of_qa_source": True,
                "gdk_source_is_ancestor_of_qa_source": True,
                "required_revision_is_ancestor_of_qa_source": False,
            },
            "refs": {
                "lookup_status": "PASS_READ_ONLY",
                "cas_ref": "codex/game-signal-sprint-gdk-cas-c058cbf7fe38",
                "cas_ref_sha": None,
                "build_refs": [],
            },
            "workflow_head_sha": "5" * 40,
            "build_run_id": "45213585866",
        }
        values.update(overrides)
        return compose_receipt(**values)

    def test_receipt_keeps_old_gdk_and_current_qa_lineages_separate(self):
        report = self.compose()
        self.assertEqual(report["status"], "HOLD_GDK_PACKAGE_PREREQUISITES")
        lineage = report["source_lineage"]
        self.assertEqual(lineage["gdk_identity_request_source_sha"], GDK_SOURCE_SHA)
        self.assertEqual(lineage["qa_product_source_sha"], QA_SOURCE_SHA)
        self.assertFalse(lineage["same_exact_source"])
        self.assertTrue(lineage["gdk_source_is_ancestor_of_qa_source"])
        self.assertFalse(lineage["required_revision_is_in_qa_product_source"])
        self.assertEqual(lineage["required_win_lose_revision_sha"], REQUIRED_WIN_LOSE_SHA)

    def test_completed_build_attestation_is_accepted(self):
        result = validate_build_proof(good_build_proof())
        self.assertEqual(result["status"], "PASS_INDEPENDENT_BUILD_ONLY")
        self.assertTrue(result["completed_run_required"])
        self.assertEqual(result["run_status_at_verification"], "completed")
        self.assertEqual(result["run_conclusion"], "success")

    def test_incomplete_or_failed_build_attestation_is_rejected(self):
        cases = (
            ("completed_run_required", False, "COMPLETED_BUILD_ATTESTATION_REQUIRED"),
            ("run_status_at_verification", "in_progress", "BUILD_RUN_NOT_COMPLETED_SUCCESS"),
            ("run_conclusion", "failure", "BUILD_RUN_NOT_COMPLETED_SUCCESS"),
        )
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                proof = good_build_proof()
                proof[field] = value
                result = validate_build_proof(proof)
                self.assertEqual(result["status"], "HOLD_BUILD_PROOF_MISMATCH")
                self.assertIn(expected_error, result["errors"])

    def test_compose_receipt_marks_missing_completed_attestation_as_hold(self):
        build = dict(good_build())
        build["completed_run_required"] = False
        report = self.compose(build=build)
        self.assertFalse(report["completed_build_attestation"]["verified"])
        self.assertIn("COMPLETED_BUILD_ATTESTATION_NOT_VERIFIED", report["missing_or_rejected"])

    def test_current_qa_exe_and_zip_are_not_substituted_for_original_gdk_bytes(self):
        report = self.compose()
        original = report["pinned_original_gdk_artifact"]
        self.assertFalse(original["matches_current_qa_exe_sha256"])
        self.assertFalse(original["matches_current_qa_artifact_zip_sha256"])
        self.assertFalse(original["substitution_allowed"])
        self.assertEqual(report["current_qa_build"]["artifact_kind"], "EXE_QA_UNSIGNED")

    def test_source_code_identity_claim_is_not_official_identity_or_cas_proof(self):
        report = self.compose()
        self.assertEqual(report["identity"]["pinned_code_contract_field_names"],
                         sorted(("store_id", "name", "publisher", "publisher_display_name",
                                 "package_family_name", "package_sid", "xbox_title_id",
                                 "xbox_scid", "msa_app_id")))
        self.assertFalse(report["identity"]["official_identity_evidence_verified"])
        self.assertFalse(report["identity"]["approved_identity_cas_commit_verified"])
        self.assertNotIn("not-emitted", str(report))

    def test_no_cas_version_assets_sdk_signing_or_msixvc_is_authorized(self):
        report = self.compose()
        self.assertFalse(report["authorization"]["gdk_package_authorized"])
        self.assertFalse(report["authorization"]["cas_write_performed"])
        self.assertFalse(report["authorization"]["sdk_executed"])
        self.assertFalse(report["authorization"]["msixvc2_built"])
        self.assertFalse(report["authorization"]["store_submitted"])
        self.assertFalse(report["ordinary_msix_allowed"])
        self.assertIsNone(report["version"]["approved_package_version"])
        self.assertFalse(report["assets_and_staging"]["approved_asset_hash_manifest_supplied"])
        self.assertFalse(report["sdk_validation"]["executed"])
        self.assertFalse(report["signing"]["verified"])
        self.assertFalse(report["msixvc2"]["built"])

    def test_ci_receipt_does_not_claim_physical_gui(self):
        report = self.compose()
        self.assertFalse(report["physical_gui_and_human_qa"]["physical_gui_verified"])
        self.assertFalse(report["physical_gui_and_human_qa"]["ja_en_uia_verified"])
        self.assertFalse(report["physical_gui_and_human_qa"]["ci_pass_is_gui_pass"])

    def test_missing_build_proof_is_a_hold_not_a_package_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            result = _validate_build_proof(missing, {
                "WINDOWS_BUILD_RESULT": "success",
                "INDEPENDENT_BUILD_RESULT": "success",
            })
        self.assertEqual(result["status"], "HOLD_BUILD_PROOF_UNAVAILABLE")
        self.assertFalse(result["independent_build_verified"])

    def test_forged_physical_gui_claim_is_rejected_from_build_proof(self):
        proof = good_build_proof()
        proof["physical_gui_verified"] = True
        result = validate_build_proof(proof)
        self.assertEqual(result["status"], "HOLD_BUILD_PROOF_MISMATCH")
        self.assertIn("BUILD_PROOF_MUST_NOT_CLAIM_PHYSICAL_GUI", result["errors"])


if __name__ == "__main__":
    unittest.main()
