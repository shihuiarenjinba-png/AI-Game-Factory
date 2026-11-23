"""Read-only Signal Sprint GDK package-readiness receipt.

This check correlates the current QA build with the older, source-pinned GDK
contract. It parses the exact Provisioner PR53 source as data; it never imports
or executes Provisioner code. It never authorizes or performs CAS, SDK, MakePkg,
signing, MSIXVC, ordinary MSIX, Store, or central-ledger operations. A
successful CI job means only that this HOLD receipt was generated.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import platform
import re
import subprocess

QA_SOURCE_SHA = "1a349faa41663c417c40710140a4d50c79b62b78"
PR30_SOURCE_SHA = "a377043d3c9ab0c71d9a100cdb841dd7000313b9"
REQUIRED_WIN_LOSE_SHA = "9ccd7ff4389b3ca0e45c8407d7369a00f4302cf2"
PR53_SHA = "ac4bd6d4fed975dae139a6638b0b7f78e09e6d71"
GDK_SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
PINNED_REQUEST = "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e"
PINNED_EXE = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
PINNED_ZIP = "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412"
PROVISIONER_REPO = "https://github.com/shihuiarenjinba-png/Repository-Provisioner-game.git"
CAS_BRANCH = "codex/game-signal-sprint-gdk-cas-c058cbf7fe38"
BUILD_BRANCH_PREFIX = "codex/game-signal-sprint-gdk-build-"
IDENTITY_FIELDS = {
    "store_id", "name", "publisher", "publisher_display_name",
    "package_family_name", "package_sid", "xbox_title_id", "xbox_scid",
    "msa_app_id",
}
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
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _assigned(tree, key, scope=None):
    nodes = tree.body if scope is None else scope.body
    for node in nodes:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == key for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("EXTERNAL_CONTRACT_FIELD_MISSING_" + key)


def _parse(path: Path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def load_pr53_contract(root: Path):
    """Verify exact PR53 contract by AST/literal inspection only; never import it."""
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    if head != PR53_SHA:
        raise ValueError("PROVISIONER_PR53_HEAD_DRIFT")

    identity_tree = _parse(root / "package_identity_provisioner.py")
    intake_tree = _parse(root / "gdk_build_intake.py")
    config_tree = _parse(root / "gdk_microsoft_game_config.py")
    job = _assigned(identity_tree, "PINNED_SIGNAL_SPRINT_JOB")
    identity = _assigned(identity_tree, "PINNED_SIGNAL_SPRINT_GDK_IDENTITY")
    if job.get("source_sha") != GDK_SOURCE_SHA or job.get("request_id") != PINNED_REQUEST:
        raise ValueError("PROVISIONER_PINNED_SOURCE_REQUEST_MISMATCH")
    if set(identity) != IDENTITY_FIELDS or any(type(value) is not str for value in identity.values()):
        raise ValueError("PROVISIONER_PINNED_IDENTITY_FIELD_SET_MISMATCH")
    if _assigned(intake_tree, "EXE_SHA256") != PINNED_EXE:
        raise ValueError("PROVISIONER_PINNED_EXE_CHANGED")
    if _assigned(intake_tree, "ARTIFACT_SHA256") != PINNED_ZIP:
        raise ValueError("PROVISIONER_PINNED_ZIP_CHANGED")
    if _assigned(config_tree, "ASSETS") != ASSETS:
        raise ValueError("PROVISIONER_GDK_ASSET_CONTRACT_CHANGED")
    verify_funcs = [
        node for node in config_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "verify_staging_inputs"
    ]
    if len(verify_funcs) != 1 or _assigned(config_tree, "routing", verify_funcs[0]) != ROUTE:
        raise ValueError("PROVISIONER_GDK_ROUTE_CHANGED")
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
        "identity_field_names": sorted(identity),
        "expected_staging_payload_files": sorted(
            ["SignalSprint.exe", *(name for name, _ in ASSETS.values())]
        ),
        "config_filename": "MicrosoftGame.config",
    }


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _read_json(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("BUILD_PROOF_MISSING_LINKED_OR_OVERSIZED")
    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
    if type(value) is not dict:
        raise ValueError("BUILD_PROOF_NOT_OBJECT")
    return value


def _git(repo: Path, *args: str):
    command = ["git", "-C", str(repo), *args]
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(command, 127, "", "GIT_COMMAND_UNAVAILABLE")


def _commit_exists(repo: Path, sha: str) -> bool:
    return _git(repo, "cat-file", "-e", sha + "^{commit}").returncode == 0


def _ensure_commit(repo: Path, sha: str) -> bool:
    if _commit_exists(repo, sha):
        return True
    fetched = _git(repo, "fetch", "--no-tags", "origin", sha)
    return fetched.returncode == 0 and _commit_exists(repo, sha)


def _is_ancestor(repo: Path, ancestor: str, descendant: str):
    if not _ensure_commit(repo, ancestor) or not _ensure_commit(repo, descendant):
        return None
    result = _git(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def _remote_refs():
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", PROVISIONER_REPO],
            capture_output=True, text=True, timeout=45, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {"lookup_status": "FAILED", "error": "GDK_REMOTE_REF_LOOKUP_FAILED",
                "cas_ref_sha": None, "build_refs": []}
    if result.returncode != 0:
        return {"lookup_status": "FAILED", "error": "GDK_REMOTE_REF_LOOKUP_FAILED",
                "cas_ref_sha": None, "build_refs": []}
    refs = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and SHA40.fullmatch(parts[0]):
            refs[parts[1]] = parts[0]
    cas_ref = "refs/heads/" + CAS_BRANCH
    build_refs = sorted(
        (ref, sha) for ref, sha in refs.items()
        if ref.startswith("refs/heads/" + BUILD_BRANCH_PREFIX)
    )
    return {
        "lookup_status": "PASS_READ_ONLY",
        "cas_ref": CAS_BRANCH,
        "cas_ref_sha": refs.get(cas_ref),
        "build_refs": [{"branch": ref.removeprefix("refs/heads/"), "sha": sha}
                       for ref, sha in build_refs],
    }


def _validate_build_proof(proof_path: Path, env: dict):
    errors = []
    if env.get("WINDOWS_BUILD_RESULT") != "success":
        errors.append("WINDOWS_FROZEN_SOURCE_BUILD_NOT_SUCCESS")
    if env.get("INDEPENDENT_BUILD_RESULT") != "success":
        errors.append("INDEPENDENT_BUILD_JOB_NOT_SUCCESS")
    try:
        proof = _read_json(proof_path)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "status": "HOLD_BUILD_PROOF_UNAVAILABLE",
            "independent_build_verified": False,
            "errors": errors + [str(exc) or type(exc).__name__],
        }

    expected = {
        "schema": "signal-sprint-independent-build-v1",
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "product_source": QA_SOURCE_SHA,
        "pr30_source_commit": PR30_SOURCE_SHA,
        "build_job_name": "windows-frozen-source-exe",
        "artifact_kind": "EXE_QA_UNSIGNED",
        "msix_status": "NOT_BUILT",
    }
    for key, value in expected.items():
        if proof.get(key) != value:
            errors.append("BUILD_PROOF_" + key.upper() + "_MISMATCH")

    if proof.get("pr30_ancestry_verified") is not True:
        errors.append("PR30_ANCESTRY_NOT_VERIFIED")
    if proof.get("build_provenance_verified") is not True:
        errors.append("BUILD_PROVENANCE_NOT_VERIFIED")
    if proof.get("independent_build_verified") is not True:
        errors.append("INDEPENDENT_BUILD_NOT_VERIFIED")
    if proof.get("physical_gui_verified") is not False:
        errors.append("BUILD_PROOF_MUST_NOT_CLAIM_PHYSICAL_GUI")
    if proof.get("gdk_package_verified") is not False:
        errors.append("BUILD_PROOF_MUST_NOT_CLAIM_GDK_PACKAGE")
    if proof.get("completed_run_required") is not False:
        errors.append("SELF_CHECK_COMPLETION_MODE_UNEXPECTED")
    if proof.get("run_status_at_verification") not in ("in_progress", "completed"):
        errors.append("BUILD_RUN_STATUS_INVALID")
    if proof.get("run_status_at_verification") == "completed" and proof.get("run_conclusion") != "success":
        errors.append("BUILD_RUN_COMPLETION_NOT_SUCCESS")

    run_id = proof.get("run_id")
    artifact_id = proof.get("artifact_id")
    exe_size = proof.get("exe_size_bytes")
    artifact_exe_size = proof.get("artifact_exe_size_bytes")
    zip_size = proof.get("artifact_zip_size_bytes")
    if type(run_id) is not int or run_id <= 0:
        errors.append("BUILD_RUN_ID_INVALID")
    if type(artifact_id) is not int or artifact_id <= 0:
        errors.append("BUILD_ARTIFACT_ID_INVALID")
    if type(exe_size) is not int or exe_size <= 0 or artifact_exe_size != exe_size:
        errors.append("BUILD_EXE_SIZE_INVALID_OR_MISMATCH")
    if type(zip_size) is not int or zip_size <= 0:
        errors.append("BUILD_ARTIFACT_ZIP_SIZE_INVALID")
    if not isinstance(proof.get("exe_sha256"), str) or not SHA256.fullmatch(proof["exe_sha256"]):
        errors.append("BUILD_EXE_SHA256_INVALID")
    if not isinstance(proof.get("artifact_zip_sha256"), str) or not SHA256.fullmatch(proof["artifact_zip_sha256"]):
        errors.append("BUILD_ARTIFACT_ZIP_SHA256_INVALID")
    if not isinstance(proof.get("workflow_head_sha"), str) or not SHA40.fullmatch(proof["workflow_head_sha"]):
        errors.append("BUILD_WORKFLOW_HEAD_INVALID")

    env_checks = (
        ("run_id", "BUILD_RUN_ID", int),
        ("artifact_id", "BUILD_ARTIFACT_ID", int),
        ("workflow_head_sha", "WORKFLOW_HEAD_SHA", str),
        ("product_source", "PRODUCT_SOURCE_SHA", str),
        ("pr30_source_commit", "PR30_SOURCE_SHA", str),
        ("exe_sha256", "BUILD_EXE_SHA256", str),
    )
    for proof_key, env_key, cast in env_checks:
        raw = env.get(env_key, "")
        try:
            wanted = cast(raw) if raw != "" else None
        except (TypeError, ValueError):
            wanted = None
        if wanted is None or proof.get(proof_key) != wanted:
            errors.append("BUILD_PROOF_ENV_BINDING_MISMATCH_" + proof_key.upper())

    if errors:
        return {
            "status": "HOLD_BUILD_PROOF_MISMATCH",
            "independent_build_verified": False,
            "errors": sorted(set(errors)),
        }

    return {
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "independent_build_verified": True,
        "build_provenance_verified": True,
        "run_id": run_id,
        "run_url": f"https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/{run_id}",
        "artifact_url": f"https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/{run_id}/artifacts/{artifact_id}",
        "run_status_at_verification": proof.get("run_status_at_verification"),
        "workflow_head_sha": proof["workflow_head_sha"],
        "product_source_sha": proof["product_source"],
        "pr30_source_sha": proof["pr30_source_commit"],
        "artifact_id": artifact_id,
        "artifact_zip_sha256": proof["artifact_zip_sha256"],
        "artifact_zip_size_bytes": zip_size,
        "exe_sha256": proof["exe_sha256"],
        "exe_size_bytes": exe_size,
        "artifact_kind": proof["artifact_kind"],
        "msix_status": proof["msix_status"],
        "gdk_package_verified": False,
        "physical_gui_verified": False,
        "evidence_file": proof_path.name,
        "artifact_digest_was_independently_compared_to_downloaded_zip": True,
    }


def _default_preflight(contract_verified: bool):
    reasons = {
        "identity": "APPROVED_IDENTITY_FILE_NOT_SUPPLIED_CAS_UNVERIFIED",
        "cas": "ACTUAL_IDENTITY_ONLY_CAS_AND_POST_CAS_BUILD_NOT_VERIFIED",
        "version": "EXPLICIT_APPROVED_GDK_PACKAGE_VERSION_MISSING",
        "assets_and_staging": "SIX_REAL_GDK_STAGING_FILES_NOT_SUPPLIED",
        "sdk_toolchain": "GDK_SDK_WINDOWS_HOST_REQUIRED",
        "sdk_validation": "OFFICIAL_GDK_SDK_VALIDATION_NOT_EXECUTED_OR_EVIDENCED",
        "signing": "GDK_SIGNING_REVIEW_OR_VALID_SIGNATURE_EVIDENCE_MISSING",
        "msixvc2": "REAL_MSIXVC2_BUILD_AND_BYTES_NOT_VERIFIED",
        "physical_human_qa": "JA_EN_DPI_125_150_AND_FIRST30_PHYSICAL_HUMAN_QA_NOT_VERIFIED",
    }
    gates = {
        "source_request_route": {
            "status": "CHECK_ONLY" if contract_verified else "HOLD",
            "reason": "PR53_PINNED_CONTRACT_READ_ONLY" if contract_verified else "PROVISIONER_CONTRACT_INVALID",
        }
    }
    gates.update({name: {"status": "HOLD", "reason": reason}
                  for name, reason in reasons.items()})
    return {"schema_version": 1, "status": "HOLD", "gates": gates}


def _hold_gates(preflight):
    gates = preflight.get("gates", {}) if isinstance(preflight, dict) else {}
    return {
        name: {"status": gate.get("status"),
               "reason": gate.get("reason") or gate.get("detail")}
        for name, gate in gates.items()
        if isinstance(gate, dict)
    }


def compose_receipt(*, contract, identity_fields, preflight, build, ancestry, refs,
                    workflow_head_sha, build_run_id):
    holds = []
    if not contract:
        holds.append("PROVISIONER_PR53_CONTRACT_NOT_VERIFIED")
    if not build.get("independent_build_verified"):
        holds.extend(build.get("errors", []) or ["CURRENT_QA_BUILD_NOT_INDEPENDENTLY_VERIFIED"])
    if contract:
        if contract.get("source_sha") != QA_SOURCE_SHA:
            holds.append("GDK_IDENTITY_REQUEST_IS_BOUND_TO_OLDER_SOURCE")
        if contract.get("pinned_request_id") != PINNED_REQUEST:
            holds.append("GDK_REQUEST_ID_MISMATCH")
        if contract.get("registration") != "GDK_GAME" or contract.get("routing") != ROUTE:
            holds.append("GDK_ROUTE_CONTRACT_MISMATCH")
    if ancestry.get("pr30_source_is_ancestor_of_qa_source") is not True:
        holds.append("PR30_SOURCE_ANCESTRY_NOT_VERIFIED")
    if ancestry.get("gdk_source_is_ancestor_of_qa_source") is not True:
        holds.append("GDK_SOURCE_ANCESTRY_NOT_VERIFIED")
    if ancestry.get("required_revision_is_ancestor_of_qa_source") is not True:
        holds.append("HOLD_REVISION_NOT_IN_FROZEN_SOURCE")
    if refs.get("lookup_status") != "PASS_READ_ONLY":
        holds.append("GDK_REMOTE_REF_LOOKUP_FAILED")
    if not refs.get("cas_ref_sha"):
        holds.append("GDK_CAS_RETURN_REF_NOT_FOUND")
    if not refs.get("build_refs"):
        holds.append("GDK_POST_CAS_BUILD_BRANCH_NOT_FOUND")

    gate_summary = _hold_gates(preflight)
    for name, gate in gate_summary.items():
        if gate["status"] == "HOLD":
            holds.append(name.upper() + ":" + str(gate["reason"]))

    gdk_source = contract.get("source_sha") if contract else GDK_SOURCE_SHA
    gdk_request = contract.get("pinned_request_id") if contract else PINNED_REQUEST
    gdk_exe = contract.get("pinned_exe_sha256") if contract else PINNED_EXE
    gdk_zip = contract.get("pinned_artifact_zip_sha256") if contract else PINNED_ZIP
    gdk_assets = []
    for key, (filename, dimensions) in sorted(ASSETS.items()):
        gdk_assets.append({"logical_name": key, "filename": filename,
                           "expected_dimensions": list(dimensions),
                           "approved_sha256": None, "file_supplied": False})

    current_exe = build.get("exe_sha256")
    current_zip = build.get("artifact_zip_sha256")
    return {
        "schema": "signal-sprint-gdk-package-readiness-v1",
        "status": "HOLD_GDK_PACKAGE_PREREQUISITES",
        "receipt_generation": "PASS_CHECK_ONLY",
        "workflow_head_sha": workflow_head_sha if SHA40.fullmatch(str(workflow_head_sha)) else None,
        "build_workflow_run_id": int(build_run_id) if str(build_run_id).isdigit() else None,
        "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME",
        "packaging_family": "GDK",
        "package_format": "MSIXVC_OR_MSIXVC2",
        "ordinary_msix_allowed": False,
        "source_lineage": {
            "qa_product_source_sha": QA_SOURCE_SHA,
            "pr30_fixed_source_sha": PR30_SOURCE_SHA,
            "gdk_identity_request_source_sha": gdk_source,
            "gdk_identity_request_id": gdk_request,
            "same_exact_source": gdk_source == QA_SOURCE_SHA,
            "gdk_source_is_ancestor_of_qa_source": ancestry.get("gdk_source_is_ancestor_of_qa_source"),
            "pr30_source_is_ancestor_of_qa_source": ancestry.get("pr30_source_is_ancestor_of_qa_source"),
            "required_win_lose_revision_sha": REQUIRED_WIN_LOSE_SHA,
            "required_revision_is_in_qa_product_source": ancestry.get("required_revision_is_ancestor_of_qa_source"),
            "status": (
                "HOLD_GDK_IDENTITY_BOUND_TO_OLDER_SOURCE"
                if gdk_source != QA_SOURCE_SHA
                else ("HOLD_REQUIRED_REVISION_NOT_IN_SOURCE"
                      if ancestry.get("required_revision_is_ancestor_of_qa_source") is not True
                      else "CHECK_ONLY_SOURCE_ALIGNMENT")
            ),
        },
        "current_qa_build": build,
        "pinned_original_gdk_artifact": {
            "source_sha": gdk_source,
            "request_id": gdk_request,
            "exe_sha256_source_code_pin": gdk_exe,
            "artifact_zip_sha256_source_code_pin": gdk_zip,
            "bytes_rehashed_in_this_run": False,
            "matches_current_qa_exe_sha256": bool(current_exe and current_exe == gdk_exe),
            "matches_current_qa_artifact_zip_sha256": bool(current_zip and current_zip == gdk_zip),
            "substitution_allowed": False,
        },
        "identity": {
            "provisioner_pr53_head_sha": PR53_SHA,
            "pinned_code_contract_present": bool(identity_fields),
            "pinned_code_contract_field_names": sorted(identity_fields) if identity_fields else [],
            "official_identity_evidence_verified": False,
            "approved_identity_cas_commit_verified": False,
            "status": "HOLD_NO_VERIFIED_IDENTITY_ONLY_CAS_RETURN",
        },
        "cas": {
            "dedicated_branch": CAS_BRANCH,
            "branch_ref_sha": refs.get("cas_ref_sha"),
            "ref_lookup_status": refs.get("lookup_status"),
            "post_cas_build_branches": refs.get("build_refs", []),
            "status": "HOLD" if not refs.get("cas_ref_sha") else "HOLD_REQUIRES_INDEPENDENT_CAS_CONTENT_VERIFICATION",
        },
        "version": {
            "review_record_supplied": False,
            "approved_package_version": None,
            "status": "HOLD_EXPLICIT_REVIEWED_GDK_VERSION_MISSING",
        },
        "assets_and_staging": {
            "expected_assets": gdk_assets,
            "approved_asset_hash_manifest_supplied": False,
            "staging_directory_supplied": False,
            "status": "HOLD_FOUR_APPROVED_GDK_ASSET_BYTES_AND_HASHES_MISSING",
        },
        "sdk_toolchain": {
            "preflight_host": platform.system(),
            "makepkg_bytes_independently_verified": False,
            "status": "HOLD_WINDOWS_GDK_SDK_AND_TRUSTED_MAKEPKG_NOT_VERIFIED",
        },
        "sdk_validation": {"executed": False, "status": "HOLD_GDK_SDK_VALIDATION_NOT_EXECUTED"},
        "signing": {"verified": False, "status": "HOLD_GDK_SIGNING_NOT_VERIFIED"},
        "msixvc2": {"built": False, "sha256": None, "status": "HOLD_REAL_MSIXVC2_NOT_BUILT"},
        "physical_gui_and_human_qa": {
            "physical_gui_verified": False,
            "ja_en_uia_verified": False,
            "human_qa_verified": False,
            "ci_pass_is_gui_pass": False,
            "status": "HOLD_PHYSICAL_GDK_GUI_AND_HUMAN_QA_NOT_VERIFIED",
        },
        "preflight_gate_summary": gate_summary,
        "missing_or_rejected": sorted(set(holds)),
        "authorization": {
            "gdk_package_authorized": False,
            "cas_write_performed": False,
            "sdk_executed": False,
            "makepkg_executed": False,
            "signing_performed": False,
            "msixvc2_built": False,
            "store_submitted": False,
            "central_ledger_modified": False,
            "product_source_modified": False,
        },
        "limitations": [
            "SOURCE_CONTROLLED_IDENTITY_CONSTANT_IS_NOT_AN_APPROVED_CAS_RETURN",
            "CURRENT_QA_UNSIGNED_EXE_IS_NOT_THE_PINNED_ORIGINAL_GDK_EXE",
            "CHECK_ONLY_RECEIPT_NEVER_AUTHORIZES_GDK_PACKAGE_OR_STORE",
            "PHYSICAL_GUI_EVIDENCE_REMAINS_A_SEPARATE_GATE",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provisioner-checkout", type=Path, required=True)
    parser.add_argument("--factory-checkout", type=Path, required=True)
    parser.add_argument("--build-proof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    contract = None
    identity_fields = {}
    contract_error = None
    try:
        contract = load_pr53_contract(args.provisioner_checkout)
        identity_fields = {name: None for name in contract["identity_field_names"]}
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        contract_error = type(exc).__name__ + ":" + str(exc)

    preflight = _default_preflight(contract is not None)
    ancestry = {
        "pr30_source_is_ancestor_of_qa_source": _is_ancestor(
            args.factory_checkout, PR30_SOURCE_SHA, QA_SOURCE_SHA),
        "gdk_source_is_ancestor_of_qa_source": _is_ancestor(
            args.factory_checkout, GDK_SOURCE_SHA, QA_SOURCE_SHA),
        "required_revision_is_ancestor_of_qa_source": _is_ancestor(
            args.factory_checkout, REQUIRED_WIN_LOSE_SHA, QA_SOURCE_SHA),
    }
    refs = _remote_refs()
    build = _validate_build_proof(args.build_proof, dict(os.environ))
    report = compose_receipt(
        contract=contract,
        identity_fields=identity_fields,
        preflight=preflight,
        build=build,
        ancestry=ancestry,
        refs=refs,
        workflow_head_sha=os.environ.get("WORKFLOW_HEAD_SHA", ""),
        build_run_id=os.environ.get("BUILD_RUN_ID", ""),
    )
    if contract_error:
        report["provisioner_contract_error"] = contract_error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "receipt_generation": report["receipt_generation"],
        "status": report["status"],
        "hold_count": len(report["missing_or_rejected"]),
        "gdk_package_authorized": report["authorization"]["gdk_package_authorized"],
    }))
    # A generated HOLD is a successful check-only CI result, not package readiness.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
