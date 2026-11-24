"""Read-only GDK current-source intake and route evidence for Signal Sprint.

This module verifies the exact frozen Factory checkout and discovers whether a
live Factory branch points to that exact commit. Only then does it call the
existing package_intake_request.build_request logic with the existing
game-signal-sprint-{SOURCE_SHA} request-id convention. It never submits a
request, writes a Git ref, invokes Provisioner, performs CAS, runs GDK tools,
or modifies the central ledger.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

FACTORY_REPOSITORY = "shihuiarenjinba-png/AI-Game-Factory"
FACTORY_URL = "https://github.com/shihuiarenjinba-png/AI-Game-Factory.git"
SOURCE_SHA = "1a349faa41663c417c40710140a4d50c79b62b78"
PR30_SOURCE_SHA = "a377043d3c9ab0c71d9a100cdb841dd7000313b9"
REQUIRED_WIN_LOSE_SHA = "9ccd7ff4389b3ca0e45c8407d7369a00f4302cf2"
LEGACY_SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
LEGACY_REQUEST_ID = "game-signal-sprint-" + LEGACY_SOURCE_SHA
REQUEST_PREFIX = "game-signal-sprint-"
SLUG = "signal-sprint"
OWNER = "shihuiarenjinba-png"
REQUEST_ACTIONS = [
    "BUILD_WINDOWS", "INSPECT_PACKAGE",
    "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN",
]
ROUTE = {
    "product_type": "GAME",
    "partner_center_selection": "GDK_GAME",
    "packaging_family": "GDK",
    "package_format": "MSIXVC_OR_MSIXVC2",
    "next_stage": "GDK_SDK_VALIDATE_THEN_MAKEPKG_PC",
    "ordinary_msix_allowed": False,
}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
VERSION = re.compile(r"(0|[1-9][0-9]{0,4})(?:\.(0|[1-9][0-9]{0,4})){2}\.0\Z")
MICROSOFT_SIGNER = re.compile(r"(?:^|,\s*)CN=Microsoft Corporation(?:,|$)", re.I)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _read_json(path: Path):
    if path is None or path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("JSON_MISSING_LINKED_OR_OVERSIZED")
    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
    if type(value) is not dict:
        raise ValueError("JSON_NOT_OBJECT")
    return value


def _git(root: Path, *args: str):
    command = ["git", "-C", str(root), *args]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(command, 127, "", "GIT_COMMAND_UNAVAILABLE")


def _normalise_origin(value: str):
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("git@github.com:"):
        path = raw.split(":", 1)[1]
    else:
        parsed = urlparse(raw)
        if parsed.scheme not in ("https", "ssh") or parsed.hostname != "github.com":
            return None
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    path = path.strip("/")
    return path if path == FACTORY_REPOSITORY else None


def parse_remote_heads(text: str):
    """Parse git ls-remote --heads output and reject malformed/duplicate refs."""
    if not isinstance(text, str):
        raise ValueError("REMOTE_REF_OUTPUT_NOT_TEXT")
    refs = {}
    for line in text.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            raise ValueError("REMOTE_REF_LINE_INVALID")
        sha, ref = parts
        if not SHA40.fullmatch(sha):
            raise ValueError("REMOTE_REF_SHA_INVALID")
        if not ref.startswith("refs/heads/"):
            raise ValueError("REMOTE_REF_NOT_HEAD")
        name = ref[len("refs/heads/"):]
        if not name or name.startswith("/") or ".." in name.split("/") or name.endswith(("/", ".")):
            raise ValueError("REMOTE_BRANCH_NAME_INVALID")
        if name in refs and refs[name] != sha:
            raise ValueError("REMOTE_BRANCH_DUPLICATE")
        refs[name] = sha
    return refs


def _load_factory_builder(factory_root: Path):
    module_path = factory_root / "package_intake_request.py"
    if module_path.is_symlink() or not module_path.is_file():
        raise ValueError("FACTORY_PACKAGE_INTAKE_MODULE_MISSING_OR_LINKED")
    spec = importlib.util.spec_from_file_location(
        "_signal_sprint_frozen_package_intake_request", module_path
    )
    if spec is None or spec.loader is None:
        raise ValueError("FACTORY_PACKAGE_INTAKE_MODULE_UNLOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = getattr(module, "build_request", None)
    if not callable(builder):
        raise ValueError("FACTORY_PACKAGE_INTAKE_BUILDER_MISSING")
    return builder


def _validate_request(payload, branch: str, request_id: str):
    expected_keys = {
        "schema_version", "request_id", "product_type", "source_factory",
        "source_repository", "source_branch", "source_sha", "slug",
        "display_name", "target_owner", "dry_run", "requested_actions",
    }
    if type(payload) is not dict or set(payload) != expected_keys:
        raise ValueError("FACTORY_REQUEST_FIELD_SET_MISMATCH")
    expected = {
        "schema_version": "1.0",
        "request_id": request_id,
        "product_type": "GAME",
        "source_factory": "AI-Game-Factory",
        "source_repository": FACTORY_REPOSITORY,
        "source_branch": branch,
        "source_sha": SOURCE_SHA,
        "slug": SLUG,
        "target_owner": OWNER,
        "dry_run": True,
        "requested_actions": REQUEST_ACTIONS,
    }
    for key, wanted in expected.items():
        if payload.get(key) != wanted:
            raise ValueError("FACTORY_REQUEST_FIELD_MISMATCH_" + key.upper())
    title = payload.get("display_name")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("FACTORY_REQUEST_DISPLAY_NAME_INVALID")


def _validate_build_attestation(value, workflow_head_sha: str):
    if not isinstance(value, dict):
        return {"status": "HOLD_COMPLETED_BUILD_ATTESTATION_UNAVAILABLE", "verified": False,
                "errors": ["BUILD_ATTESTATION_NOT_SUPPLIED"]}
    errors = []
    expected = {
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "product_source": SOURCE_SHA,
        "pr30_source_commit": PR30_SOURCE_SHA,
        "workflow_head_sha": workflow_head_sha,
        "run_status_at_verification": "completed",
        "run_conclusion": "success",
        "completed_run_required": True,
        "artifact_kind": "EXE_QA_UNSIGNED",
        "msix_status": "NOT_BUILT",
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "product_acceptance": False,
        "pr30_ancestry_verified": True,
        "build_provenance_verified": True,
        "independent_build_verified": True,
        "build_proof_artifact_verified": True,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            errors.append("BUILD_ATTESTATION_" + key.upper() + "_MISMATCH")
    for key in ("run_id", "artifact_id", "exe_size_bytes", "artifact_zip_size_bytes"):
        item = value.get(key)
        if type(item) is not int or item <= 0:
            errors.append("BUILD_ATTESTATION_" + key.upper() + "_INVALID")
    for key in ("exe_sha256", "artifact_zip_sha256"):
        item = value.get(key)
        if not isinstance(item, str) or not SHA256.fullmatch(item):
            errors.append("BUILD_ATTESTATION_" + key.upper() + "_INVALID")
    if value.get("artifact_exe_size_bytes") != value.get("exe_size_bytes"):
        errors.append("BUILD_ATTESTATION_ARTIFACT_EXE_SIZE_MISMATCH")
    proof_id = value.get("build_proof_artifact_id")
    if type(proof_id) is not int or proof_id <= 0:
        errors.append("BUILD_ATTESTATION_PROOF_ARTIFACT_ID_INVALID")
    if value.get("build_proof_artifact_run_id") != value.get("run_id"):
        errors.append("BUILD_ATTESTATION_PROOF_ARTIFACT_RUN_MISMATCH")
    if value.get("build_proof_artifact_workflow_head_sha") != workflow_head_sha:
        errors.append("BUILD_ATTESTATION_PROOF_ARTIFACT_HEAD_MISMATCH")
    proof_sha = value.get("build_proof_artifact_zip_sha256")
    if not isinstance(proof_sha, str) or not SHA256.fullmatch(proof_sha):
        errors.append("BUILD_ATTESTATION_PROOF_ARTIFACT_ZIP_SHA_INVALID")
    if value.get("build_proof_artifact_digest") != ("sha256:" + proof_sha if isinstance(proof_sha, str) else None):
        errors.append("BUILD_ATTESTATION_PROOF_ARTIFACT_DIGEST_MISMATCH")
    proof_size = value.get("build_proof_artifact_zip_size_bytes")
    if type(proof_size) is not int or proof_size <= 0:
        errors.append("BUILD_ATTESTATION_PROOF_ARTIFACT_ZIP_SIZE_INVALID")
    if value.get("expected_run_id") != str(value.get("run_id")):
        errors.append("BUILD_ATTESTATION_EXPECTED_RUN_ID_MISMATCH")
    if value.get("expected_workflow_head") != workflow_head_sha:
        errors.append("BUILD_ATTESTATION_EXPECTED_WORKFLOW_HEAD_MISMATCH")
    expected_url = "https://github.com/" + FACTORY_REPOSITORY + "/actions/runs/" + str(value.get("run_id"))
    if value.get("build_run_url") != expected_url:
        errors.append("BUILD_ATTESTATION_BUILD_RUN_URL_MISMATCH")
    if errors:
        return {"status": "HOLD_COMPLETED_BUILD_ATTESTATION_MISMATCH",
                "verified": False, "errors": sorted(set(errors))}
    return {
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "verified": True,
        "run_id": value["run_id"],
        "artifact_id": value["artifact_id"],
        "workflow_head_sha": value["workflow_head_sha"],
        "product_source_sha": value["product_source"],
        "pr30_source_sha": value["pr30_source_commit"],
        "exe_sha256": value["exe_sha256"],
        "exe_size_bytes": value["exe_size_bytes"],
        "artifact_zip_sha256": value["artifact_zip_sha256"],
        "artifact_zip_size_bytes": value["artifact_zip_size_bytes"],
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "msix_status": "NOT_BUILT",
        "product_acceptance": False,
        "pr30_ancestry_verified": True,
        "build_proof_artifact_id": value["build_proof_artifact_id"],
        "build_proof_artifact_digest": value["build_proof_artifact_digest"],
        "build_proof_artifact_run_id": value["build_proof_artifact_run_id"],
        "build_proof_artifact_workflow_head_sha": value["build_proof_artifact_workflow_head_sha"],
        "build_proof_artifact_zip_sha256": value["build_proof_artifact_zip_sha256"],
        "build_proof_artifact_zip_size_bytes": value["build_proof_artifact_zip_size_bytes"],
        "build_run_url": value["build_run_url"],
        "errors": [],
    }


def _validate_sdk_capability(value, build, workflow_head_sha: str):
    if not isinstance(value, dict):
        return {"status": "HOLD_GDK_SDK_CAPABILITY_ARTIFACT_UNAVAILABLE",
                "receipt_verified": False, "toolchain_capability_verified": False,
                "errors": ["SDK_CAPABILITY_RECEIPT_NOT_SUPPLIED"]}
    errors = []
    expected = {
        "schema": "signal-sprint-gdk-sdk-capability-v1",
        "read_only": True,
        "host_os": "Windows",
        "runner_scope": "WINDOWS_HOST_ONLY_NOT_PHYSICAL_GUI",
        "workflow_head_sha": workflow_head_sha,
        "build_run_id": build.get("run_id") if build.get("verified") else None,
    }
    for key, wanted in expected.items():
        if wanted is None or value.get(key) != wanted:
            errors.append("SDK_CAPABILITY_" + key.upper() + "_MISMATCH")
    forbidden = (
        "makepkg_executed", "submission_validator_executed", "sdk_validation_executed",
        "package_built", "msixvc2_built", "signing_performed", "store_submitted",
        "physical_gui_verified", "gdk_package_verified", "ordinary_msix_allowed",
    )
    for key in forbidden:
        if value.get(key) is not False:
            errors.append("SDK_CAPABILITY_FORBIDDEN_FLAG_" + key.upper())
    status = value.get("status")
    if not isinstance(status, str) or not (
        status == "PASS_TOOLCHAIN_CAPABILITY_ONLY" or status.startswith("HOLD_")
    ):
        errors.append("SDK_CAPABILITY_STATUS_INVALID")
    if status == "PASS_TOOLCHAIN_CAPABILITY_ONLY":
        version = value.get("expected_sdk_version")
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            errors.append("SDK_CAPABILITY_APPROVED_VERSION_INVALID")
        for name in ("makepkg", "submission_validator"):
            item = value.get(name)
            if not isinstance(item, dict):
                errors.append("SDK_CAPABILITY_COMPONENT_MISSING_" + name.upper())
                continue
            if type(item.get("size_bytes")) is not int or item["size_bytes"] <= 0:
                errors.append("SDK_CAPABILITY_COMPONENT_SIZE_INVALID_" + name.upper())
            if not isinstance(item.get("sha256"), str) or not SHA256.fullmatch(item["sha256"]):
                errors.append("SDK_CAPABILITY_COMPONENT_SHA_INVALID_" + name.upper())
            if item.get("signature_status") != "Valid":
                errors.append("SDK_CAPABILITY_COMPONENT_SIGNATURE_INVALID_" + name.upper())
            signer = item.get("signer_subject")
            if not isinstance(signer, str) or MICROSOFT_SIGNER.search(signer) is None:
                errors.append("SDK_CAPABILITY_COMPONENT_SIGNER_INVALID_" + name.upper())
    if errors:
        return {"status": "HOLD_GDK_SDK_CAPABILITY_PROOF_MISMATCH",
                "receipt_verified": False, "toolchain_capability_verified": False,
                "errors": sorted(set(errors))}
    return {
        "status": status,
        "receipt_verified": True,
        "toolchain_capability_verified": status == "PASS_TOOLCHAIN_CAPABILITY_ONLY",
        "build_run_id": value.get("build_run_id"),
        "workflow_head_sha": value.get("workflow_head_sha"),
        "sdk_root": value.get("sdk_root"),
        "expected_sdk_version": value.get("expected_sdk_version"),
        "makepkg": value.get("makepkg"),
        "submission_validator": value.get("submission_validator"),
        "read_only": True,
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
        "errors": [],
    }


def assess(factory_root: Path, *, checkout_head: str, origin_url: str,
           remote_refs_text: str = "", remote_lookup_ok: bool = True,
           workflow_head_sha: str = "", build_attestation=None,
           sdk_capability=None):
    holds = []
    if factory_root.is_symlink() or not factory_root.is_dir():
        checkout_status = "HOLD_FACTORY_SOURCE_CHECKOUT_MISSING_OR_LINKED"
        holds.append(checkout_status)
    elif checkout_head != SOURCE_SHA:
        checkout_status = "HOLD_FACTORY_SOURCE_CHECKOUT_HEAD_MISMATCH"
        holds.append(checkout_status)
    elif _normalise_origin(origin_url) != FACTORY_REPOSITORY:
        checkout_status = "HOLD_FACTORY_SOURCE_REPOSITORY_MISMATCH"
        holds.append(checkout_status)
    else:
        checkout_status = "PASS_EXACT_FROZEN_SOURCE_CHECKOUT"

    candidate_request_id = REQUEST_PREFIX + SOURCE_SHA
    request_payload = None
    source_branch = None
    matching_refs = []
    related_refs = []
    ref_status = "HOLD_FACTORY_REMOTE_REF_LOOKUP_FAILED"
    if checkout_status == "PASS_EXACT_FROZEN_SOURCE_CHECKOUT":
        if not remote_lookup_ok:
            holds.append(ref_status)
        else:
            try:
                refs = parse_remote_heads(remote_refs_text)
                matching_refs = sorted(name for name, sha in refs.items() if sha == SOURCE_SHA)
                related_refs = [
                    {"branch": name, "sha": sha}
                    for name, sha in sorted(refs.items())
                    if "signal-sprint" in name
                ]
                if not matching_refs:
                    ref_status = "HOLD_FACTORY_SOURCE_REF_NOT_EXACT_FROZEN_SOURCE"
                elif len(matching_refs) != 1:
                    ref_status = "HOLD_FACTORY_SOURCE_REF_AMBIGUOUS"
                elif not matching_refs[0].startswith("codex/"):
                    ref_status = "HOLD_FACTORY_SOURCE_REF_NOT_GAME_WORK_BRANCH"
                else:
                    source_branch = matching_refs[0]
                    builder = _load_factory_builder(factory_root)
                    request_payload = builder(
                        factory_root, SLUG, candidate_request_id, SOURCE_SHA,
                        source_branch=source_branch,
                    )
                    _validate_request(request_payload, source_branch, candidate_request_id)
                    ref_status = "CHECK_ONLY_REQUEST_DERIVED_NOT_SUBMITTED"
            except (ValueError, OSError, TypeError, KeyError, ImportError) as exc:
                ref_status = "HOLD_FACTORY_REQUEST_DERIVATION_FAILED"
                holds.append(str(exc) or type(exc).__name__)
        if ref_status.startswith("HOLD_"):
            holds.append(ref_status)
    else:
        ref_status = "HOLD_FACTORY_CHECKOUT_INVALID"
        holds.append("FACTORY_REMOTE_REF_CHECK_NOT_ATTEMPTED_CHECKOUT_INVALID")

    request_generated = request_payload is not None
    build = _validate_build_attestation(build_attestation, workflow_head_sha)
    if not build["verified"]:
        holds.extend(build.get("errors", []) or [build["status"]])
    sdk = _validate_sdk_capability(sdk_capability, build, workflow_head_sha)
    if not sdk["receipt_verified"]:
        holds.extend(sdk.get("errors", []) or [sdk["status"]])

    gates = {
        "source_request_route": {
            "status": "CHECK_ONLY" if request_generated else "HOLD",
            "reason": ref_status,
        },
        "identity": {
            "status": "HOLD",
            "reason": "CURRENT_SOURCE_IDENTITY_ONLY_RETURN_NOT_VERIFIED",
        },
        "cas": {
            "status": "HOLD",
            "reason": "CURRENT_SOURCE_IDENTITY_ONLY_CAS_AND_POST_CAS_BUILD_NOT_VERIFIED",
        },
        "version": {
            "status": "HOLD",
            "reason": "EXPLICIT_APPROVED_GDK_PACKAGE_VERSION_MISSING",
        },
        "assets_and_staging": {
            "status": "HOLD",
            "reason": "CURRENT_SOURCE_APPROVED_ASSET_HASHES_AND_SIX_FILE_STAGING_MISSING",
        },
        "sdk_toolchain": {
            "status": "CHECK_ONLY" if sdk["toolchain_capability_verified"] else "HOLD",
            "reason": sdk["status"],
        },
        "sdk_validation": {
            "status": "HOLD",
            "reason": "OFFICIAL_GDK_SDK_VALIDATION_NOT_EXECUTED",
        },
        "signing": {
            "status": "HOLD",
            "reason": "GDK_SIGNING_REVIEW_OR_VALID_SIGNATURE_EVIDENCE_MISSING",
        },
        "msixvc2": {
            "status": "HOLD",
            "reason": "REAL_GDK_MSIXVC2_BUILD_AND_BYTES_NOT_VERIFIED",
        },
        "physical_human_qa": {
            "status": "HOLD",
            "reason": "PHYSICAL_GDK_GUI_AND_HUMAN_QA_NOT_VERIFIED",
        },
    }
    for name, gate in gates.items():
        if gate["status"] == "HOLD":
            holds.append(name.upper() + ":" + gate["reason"])

    return {
        "schema": "signal-sprint-gdk-current-source-readiness-v1",
        "status": "HOLD_GDK_PACKAGE_PREREQUISITES",
        "receipt_generation": "PASS_CHECK_ONLY",
        "read_only": True,
        "workflow_head_sha": workflow_head_sha if SHA40.fullmatch(str(workflow_head_sha)) else None,
        "product": "Signal Sprint",
        "source_checkout": {
            "repository": FACTORY_REPOSITORY,
            "head_sha": checkout_head,
            "origin_url": origin_url,
            "exact_frozen_source_verified": checkout_status == "PASS_EXACT_FROZEN_SOURCE_CHECKOUT",
            "status": checkout_status,
        },
        "source_lineage": {
            "frozen_product_source_sha": SOURCE_SHA,
            "pr30_fixed_source_sha": PR30_SOURCE_SHA,
            "required_win_lose_revision_sha": REQUIRED_WIN_LOSE_SHA,
            "legacy_identity_source_sha": LEGACY_SOURCE_SHA,
            "legacy_identity_request_id": LEGACY_REQUEST_ID,
            "legacy_identity_reusable": False,
        },
        "remote_factory_refs": {
            "lookup_status": "PASS_READ_ONLY" if remote_lookup_ok else "FAILED",
            "matching_exact_source_branches": matching_refs,
            "related_signal_sprint_branches": related_refs,
            "matching_ref_count": len(matching_refs),
            "status": ref_status,
        },
        "request": {
            "candidate_request_id": candidate_request_id,
            "request_id": candidate_request_id if request_generated else None,
            "source_branch": source_branch,
            "request_generated": request_generated,
            "request_submitted": False,
            "request_payload": request_payload,
            "generation_method": "existing game-signal-sprint-{SOURCE_SHA} convention + frozen package_intake_request.build_request",
            "status": ref_status,
            "dry_run_only": True,
        },
        "route": {
            **ROUTE,
            "route_source": "Factory GAME intake plus explicit Signal Sprint GDK-only packaging policy",
        },
        "legacy_identity": {
            "source_sha": LEGACY_SOURCE_SHA,
            "request_id": LEGACY_REQUEST_ID,
            "status": "HISTORICAL_NOT_REBOUND",
            "reusable": False,
            "identity_fields_reused": False,
            "official_identity_verified": False,
            "cas_return_verified": False,
        },
        "completed_build_attestation": build,
        "sdk_capability": sdk,
        "gates": gates,
        "identity": {
            "status": "HOLD_CURRENT_SOURCE_IDENTITY_ONLY_RETURN_NOT_VERIFIED",
            "official_identity_evidence_verified": False,
            "approved_identity_cas_commit_verified": False,
            "legacy_identity_reused": False,
        },
        "cas": {
            "status": "HOLD_CURRENT_SOURCE_CAS_RETURN_NOT_VERIFIED",
            "cas_write_performed": False,
            "post_cas_build_verified": False,
        },
        "version": {
            "status": "HOLD_EXPLICIT_REVIEWED_GDK_VERSION_MISSING",
            "approved_package_version": None,
        },
        "assets_and_staging": {
            "status": "HOLD_CURRENT_SOURCE_APPROVED_ASSET_BYTES_AND_STAGING_MISSING",
            "approved_asset_hash_manifest_supplied": False,
            "staging_directory_supplied": False,
        },
        "sdk_validation": {
            "status": "HOLD_OFFICIAL_GDK_SDK_VALIDATION_NOT_EXECUTED",
            "executed": False,
        },
        "signing": {"status": "HOLD_GDK_SIGNING_NOT_VERIFIED", "verified": False},
        "msixvc2": {"status": "HOLD_REAL_GDK_MSIXVC2_NOT_BUILT", "built": False, "sha256": None},
        "physical_gui_and_human_qa": {
            "status": "HOLD_PHYSICAL_GDK_GUI_AND_HUMAN_QA_NOT_VERIFIED",
            "physical_gui_verified": False,
            "ja_en_uia_verified": False,
            "human_qa_verified": False,
            "ci_pass_is_gui_pass": False,
        },
        "authorization": {
            "gdk_package_authorized": False,
            "request_submitted": False,
            "cas_write_performed": False,
            "sdk_executed": False,
            "makepkg_executed": False,
            "signing_performed": False,
            "msixvc2_built": False,
            "ordinary_msix_allowed": False,
            "store_submitted": False,
            "central_ledger_modified": False,
            "product_source_modified": False,
            "pr30_source_modified": False,
        },
        "central_ledger_handoff": {
            "target": "36 central ledger",
            "source_request_route_evidence_included": True,
            "ledger_write_performed": False,
        },
        "missing_or_rejected": sorted(set(holds)),
        "limitations": [
            "EXACT_FACTORY_BRANCH_REF_REQUIRED_BEFORE_REQUEST_PAYLOAD_GENERATION",
            "CURRENT_REQUEST_IS_DRY_RUN_ONLY_AND_NOT_SUBMITTED",
            "LEGACY_C058_IDENTITY_IS_HISTORICAL_AND_NOT_REBOUND",
            "NO_CAS_OR_GDK_SDK_EXECUTION_OR_MAKEPKG",
            "NO_VERSION_OR_ASSET_APPROVAL_OR_MSIXVC2_BUILD",
            "NO_ORDINARY_MSIX_SUBSTITUTION",
            "CI_PASS_IS_NOT_PHYSICAL_GUI_PASS",
            "CENTRAL_LEDGER_36_NOT_MODIFIED",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-root", type=Path, required=True,
                        help="Checkout of the exact frozen Factory source commit.")
    parser.add_argument("--workflow-head", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--build-attestation", type=Path)
    parser.add_argument("--sdk-capability-receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    head_result = _git(args.factory_root, "rev-parse", "HEAD")
    origin_result = _git(args.factory_root, "remote", "get-url", "origin")
    checkout_head = head_result.stdout.strip() if head_result.returncode == 0 else ""
    origin_url = origin_result.stdout.strip() if origin_result.returncode == 0 else ""
    try:
        remote = subprocess.run(
            ["git", "ls-remote", "--heads", FACTORY_URL],
            capture_output=True, text=True, timeout=45, check=False,
        )
        remote_ok = remote.returncode == 0
    except (OSError, subprocess.SubprocessError):
        remote = subprocess.CompletedProcess(
            ["git", "ls-remote", "--heads", FACTORY_URL], 127, "", "FACTORY_REMOTE_REF_LOOKUP_FAILED"
        )
        remote_ok = False
    try:
        build = _read_json(args.build_attestation) if args.build_attestation else None
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        build = {"_read_error": str(exc)}
    try:
        sdk = _read_json(args.sdk_capability_receipt) if args.sdk_capability_receipt else None
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        sdk = {"_read_error": str(exc)}

    report = assess(
        args.factory_root,
        checkout_head=checkout_head,
        origin_url=origin_url,
        remote_refs_text=remote.stdout if remote_ok else "",
        remote_lookup_ok=remote_ok,
        workflow_head_sha=args.workflow_head,
        build_attestation=build,
        sdk_capability=sdk,
    )
    if not remote_ok:
        report["remote_factory_refs"]["error"] = "FACTORY_REMOTE_REF_LOOKUP_FAILED"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "receipt_generation": report["receipt_generation"],
        "status": report["status"],
        "source_request_status": report["request"]["status"],
        "request_generated": report["request"]["request_generated"],
        "hold_count": len(report["missing_or_rejected"]),
        "gdk_package_authorized": report["authorization"]["gdk_package_authorized"],
    }))
    # A specific HOLD is an expected check-only result, not a CI failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
