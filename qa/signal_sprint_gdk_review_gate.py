"""Read-only cross-repo gate: UI revision evidence is NOT an approved GDK package.

The external Provisioner checkout is pinned to Draft PR #53's exact commit.
This tool never imports or executes its code, never edits staging, and never
returns a GDK READY status. Synthetic tests are not actual GUI evidence.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import subprocess

from signal_sprint_visibility_receipt import verify as verify_visibility

PR53_SHA = "ac4bd6d4fed975dae139a6638b0b7f78e09e6d71"
IMMUTABLE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
PINNED_REQUEST = "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e"
PINNED_EXE = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
PINNED_ZIP = "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412"
ASSETS = {
    "StoreLogo": ("StoreLogo.png", (100, 100)),
    "Square150x150Logo": ("Logo.png", (150, 150)),
    "Square44x44Logo": ("SmallLogo.png", (44, 44)),
    "SplashScreenImage": ("SplashScreen.png", (1920, 1080)),
}
ROUTE = {
    "schema_version": 1,
    "packaging_family": "GDK",
    "package_format": "MSIXVC_OR_MSIXVC2",
    "next_stage": "GDK_SDK_VALIDATE_THEN_MAKEPKG_PC",
}


def _assigned(tree, key, scope=None):
    nodes = tree.body if scope is None else scope.body
    for node in nodes:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == key for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("EXTERNAL_CONTRACT_FIELD_MISSING_" + key)


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def load_pr53_contract(root):
    """Inspect exact committed PR53 sources as DATA, never import them."""
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    if head != PR53_SHA:
        raise ValueError("PROVISIONER_PR53_HEAD_DRIFT")
    intake = _parse(root / "gdk_build_intake.py")
    identity = _parse(root / "package_identity_provisioner.py")
    config = _parse(root / "gdk_microsoft_game_config.py")
    job = _assigned(identity, "PINNED_SIGNAL_SPRINT_JOB")
    if job.get("source_sha") != IMMUTABLE or job.get("request_id") != PINNED_REQUEST:
        raise ValueError("PROVISIONER_PINNED_JOB_MISMATCH")
    if _assigned(intake, "EXE_SHA256") != PINNED_EXE:
        raise ValueError("PROVISIONER_PINNED_EXE_CHANGED")
    if _assigned(intake, "ARTIFACT_SHA256") != PINNED_ZIP:
        raise ValueError("PROVISIONER_PINNED_ZIP_CHANGED")
    if _assigned(config, "ASSETS") != ASSETS:
        raise ValueError("PROVISIONER_GDK_ASSET_CONTRACT_CHANGED")
    funcs = [n for n in config.body if isinstance(n, ast.FunctionDef)
             and n.name == "verify_staging_inputs"]
    if len(funcs) != 1 or _assigned(config, "routing", funcs[0]) != ROUTE:
        raise ValueError("PROVISIONER_STAGING_ROUTE_CHANGED")
    return {
        "provisioner_pr": 53,
        "provisioner_head_sha": head,
        "source_sha": job["source_sha"],
        "pinned_request_id": job["request_id"],
        "pinned_exe_sha256": PINNED_EXE,
        "pinned_artifact_zip_sha256": PINNED_ZIP,
        "registration": "GDK_GAME",
        "routing": ROUTE,
        "asset_filenames": sorted(name for name, _ in ASSETS.values()),
        "expected_staging_payload_files": sorted(["SignalSprint.exe", *(name for name, _ in ASSETS.values())]),
        "config_filename": "MicrosoftGame.config",
    }


def lineage_errors(receipt, contract, expected_revision, visibility_errors=()):
    """Independent fail-closed checks, in addition to screenshot/EXE-byte audit."""
    errors = list(visibility_errors)
    def reject(condition, code):
        if condition:
            errors.append(code)
    reject(contract.get("provisioner_head_sha") != PR53_SHA, "PR53_CONTRACT_HEAD_MISMATCH")
    reject(contract.get("source_sha") != IMMUTABLE, "PR53_SOURCE_MISMATCH")
    reject(contract.get("pinned_request_id") != PINNED_REQUEST, "PR53_REQUEST_MISMATCH")
    reject(contract.get("pinned_exe_sha256") != PINNED_EXE, "PR53_PINNED_EXE_MISMATCH")
    reject(contract.get("pinned_artifact_zip_sha256") != PINNED_ZIP, "PR53_ZIP_MISMATCH")
    reject(contract.get("routing") != ROUTE or contract.get("registration") != "GDK_GAME",
           "GDK_ROUTE_MISMATCH")
    reject(contract.get("asset_filenames") != sorted(name for name, _ in ASSETS.values()),
           "GDK_ASSET_INVENTORY_MISMATCH")
    reject(contract.get("expected_staging_payload_files") !=
           sorted(["SignalSprint.exe", *(name for name, _ in ASSETS.values())]),
           "GDK_STAGING_INVENTORY_MISMATCH")
    reject(contract.get("config_filename") != "MicrosoftGame.config", "GDK_CONFIG_NAME_MISMATCH")
    reject(receipt.get("registration") != "GDK_GAME", "REVIEW_REGISTRATION_MISMATCH")
    reject(receipt.get("immutable_source_sha") != IMMUTABLE, "REVIEW_IMMUTABLE_SOURCE_MISMATCH")
    reject(receipt.get("revision_sha") != expected_revision or
           not re.fullmatch(r"[0-9a-f]{40}", str(expected_revision)) or
           expected_revision == IMMUTABLE, "REVIEW_REVISION_HEAD_MISMATCH")
    review_exe = receipt.get("exe_sha256")
    reject(not isinstance(review_exe, str) or
           not re.fullmatch(r"[0-9a-f]{64}", review_exe), "REVIEW_EXE_SHA_INVALID")
    reject(review_exe == PINNED_EXE, "REVIEW_EXE_MISBOUND_TO_IMMUTABLE_GDK_ARTIFACT")
    reject(receipt.get("work_area_bounds") != [0, 0, 1024, 720],
           "REVIEW_WORKAREA_NOT_MEASURED")
    window = receipt.get("window_bounds")
    if not (isinstance(window, list) and len(window) == 4 and
            all(type(x) is int for x in window) and
            0 <= window[0] < window[2] <= 1024 and
            0 <= window[1] < window[3] <= 720):
        errors.append("REVIEW_GUI_OUTSIDE_WORKAREA")
    reject(receipt.get("status") != "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY",
           "REVIEW_GUI_STATUS_NOT_CHECK_ONLY")
    for key in ("human_qa_pass", "sale_ready", "cas_return_pass",
                "gdk_sdk_executed", "msixvc2_built", "store_submitted"):
        reject(receipt.get(key) is not False, "REVIEW_FALSE_DOWNSTREAM_CLAIM_" + key)
    for key in ("gdk_staging_ready", "msixvc_ready", "gdk_sdk_validated",
                "real_msixvc_built", "package_version", "approved_assets"):
        reject(receipt.get(key) is not None and receipt.get(key) is not False,
               "REVIEW_UNAPPROVED_STAGING_CLAIM_" + key)
    return sorted(set(errors))


def audit(receipt, screenshots, exe, revision, run_id, contract):
    visual_errors, visual = verify_visibility(receipt, screenshots, revision, run_id, exe)
    errors = lineage_errors(receipt, contract, revision, visual_errors)
    return {
        "status": "HOLD" if errors else "REVIEW_GUI_CHECK_ONLY_GDK_STAGING_HOLD",
        "errors": errors,
        "review_exe_sha256": receipt.get("exe_sha256"),
        "review_revision_sha": revision,
        "review_workflow_run_id": str(run_id),
        "pr53_head_sha": contract["provisioner_head_sha"],
        "immutable_source_sha": IMMUTABLE,
        "immutable_gdk_exe_sha256": PINNED_EXE,
        "immutable_gdk_artifact_zip_sha256": PINNED_ZIP,
        "review_exe_is_approved_gdk_staging_exe": False,
        "real_staging_files_verified": False,
        "approved_version_and_four_assets_verified": False,
        "approved_cas_for_review_revision": False,
        "gdk_sdk_validated": False,
        "real_msixvc_built": False,
        "sale_ready": False,
        "old_artifact_sha_discrepancy": "HOLD_NOT_RECONCILED",
        "visual_audit_status": visual.get("status"),
        "limitations": ["PR53_PINNED_SOURCE_INSPECTED_READ_ONLY",
                        "NO_EXTERNAL_REVIEWED_STAGING_RECEIPT_OR_LIVE_FILES",
                        "NO_APPROVED_CAS_VERSION_OR_FOUR_ASSETS",
                        "OS_DPI_125_150_AND_HUMAN_QA_HOLD",
                        "CHECK_ONLY_IS_NOT_GDK_SDK_OR_MSIXVC"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provisioner-checkout", type=Path, required=True)
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        contract = load_pr53_contract(args.provisioner_checkout)
        if args.contract_only:
            report = {"status": "PR53_SOURCE_CONTRACT_CHECK_ONLY_STAGING_HOLD",
                      "errors": [], "contract": contract,
                      "gdk_sdk_validated": False, "real_msixvc_built": False,
                      "sale_ready": False}
        else:
            if any(value is None for value in
                   (args.receipt, args.screenshots, args.exe, args.revision, args.run_id)):
                raise ValueError("GUI_EVIDENCE_ARGUMENTS_MISSING")
            receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
            report = audit(receipt, args.screenshots, args.exe, args.revision, args.run_id, contract)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        report = {"status": "HOLD", "errors": [type(exc).__name__ + ": " + str(exc)],
                  "gdk_sdk_validated": False, "real_msixvc_built": False,
                  "sale_ready": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2),
                           encoding="utf-8")
    print(json.dumps({"status": report["status"], "errors": report["errors"]}))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
