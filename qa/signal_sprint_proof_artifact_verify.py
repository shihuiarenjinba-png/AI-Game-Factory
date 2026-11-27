"""Verify the exact GitHub Actions proof-artifact ZIP bytes before using its receipt.

This is cloud provenance only. It never verifies a physical GUI, GDK package,
ordinary MSIX, or product acceptance.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

from signal_sprint_independent_build_verify import get, safe_zip_member

REPO = "shihuiarenjinba-png/AI-Game-Factory"
API = "https://api.github.com/repos/" + REPO
SOURCE = "1a349faa41663c417c40710140a4d50c79b62b78"
PR30_SOURCE = "a377043d3c9ab0c71d9a100cdb841dd7000313b9"
ARTIFACT_NAME = "signal-sprint-independent-cloud-build-proof"
ARTIFACT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_MEMBERS = {
    "build-receipt.json",
    "cloud-build-proof.json",
    "independent-build-receipt.json",
}
MAX_PROOF_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_PROOF_JSON_BYTES = 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _json_object(raw, reason):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError(reason) from exc
    require(isinstance(value, dict), reason)
    return value


def _positive_int(value, reason):
    require(type(value) is int and value > 0, reason)
    return value


def verify(
    artifact_id,
    expected_digest,
    expected_run_id,
    expected_repository_id,
    expected_workflow_head,
    token,
    fetch=get,
):
    """Verify metadata, downloaded ZIP bytes, and all three embedded JSON receipts."""
    _positive_int(artifact_id, "PROOF_ARTIFACT_ID_INVALID")
    _positive_int(expected_repository_id, "EXPECTED_REPOSITORY_ID_INVALID")
    require(
        isinstance(expected_run_id, str)
        and re.fullmatch(r"[1-9][0-9]*", expected_run_id) is not None,
        "EXPECTED_BUILD_RUN_ID_INVALID",
    )
    run_id = int(expected_run_id)
    require(
        isinstance(expected_workflow_head, str)
        and SHA40.fullmatch(expected_workflow_head) is not None,
        "EXPECTED_WORKFLOW_HEAD_INVALID",
    )
    require(
        isinstance(expected_digest, str)
        and ARTIFACT_DIGEST.fullmatch(expected_digest) is not None,
        "EXPECTED_PROOF_ARTIFACT_DIGEST_INVALID",
    )
    require(isinstance(token, str) and bool(token), "GITHUB_TOKEN_MISSING")

    metadata = _json_object(
        fetch(f"{API}/actions/artifacts/{artifact_id}", token),
        "PROOF_ARTIFACT_METADATA_INVALID",
    )
    require(metadata.get("id") == artifact_id, "PROOF_ARTIFACT_ID_MISMATCH")
    require(metadata.get("name") == ARTIFACT_NAME, "PROOF_ARTIFACT_NAME_MISMATCH")
    require(metadata.get("expired") is False, "PROOF_ARTIFACT_EXPIRED_OR_UNVERIFIED")
    metadata_size = _positive_int(
        metadata.get("size_in_bytes"), "PROOF_ARTIFACT_SIZE_INVALID"
    )
    require(metadata_size <= MAX_PROOF_ARTIFACT_BYTES, "PROOF_ARTIFACT_TOO_LARGE")
    metadata_digest = metadata.get("digest")
    require(
        isinstance(metadata_digest, str)
        and ARTIFACT_DIGEST.fullmatch(metadata_digest) is not None,
        "PROOF_ARTIFACT_METADATA_DIGEST_INVALID",
    )
    require(
        metadata_digest == expected_digest,
        "PROOF_ARTIFACT_EXPECTED_DIGEST_MISMATCH",
    )

    workflow_run = metadata.get("workflow_run")
    require(isinstance(workflow_run, dict), "PROOF_ARTIFACT_RUN_MISSING")
    require(workflow_run.get("id") == run_id, "PROOF_ARTIFACT_RUN_MISMATCH")
    require(
        workflow_run.get("head_sha") == expected_workflow_head,
        "PROOF_ARTIFACT_HEAD_MISMATCH",
    )
    require(
        workflow_run.get("repository_id") == expected_repository_id,
        "PROOF_ARTIFACT_REPOSITORY_MISMATCH",
    )
    require(
        workflow_run.get("head_repository_id") == expected_repository_id,
        "PROOF_ARTIFACT_HEAD_REPOSITORY_MISMATCH",
    )

    archive = fetch(f"{API}/actions/artifacts/{artifact_id}/zip", token)
    require(
        isinstance(archive, (bytes, bytearray)),
        "PROOF_ARTIFACT_DOWNLOAD_NOT_BYTES",
    )
    require(
        0 < len(archive) <= MAX_PROOF_ARTIFACT_BYTES,
        "PROOF_ARTIFACT_DOWNLOAD_SIZE_INVALID",
    )
    require(
        len(archive) == metadata_size,
        "PROOF_ARTIFACT_ZIP_SIZE_MISMATCH",
    )
    archive_sha256 = hashlib.sha256(archive).hexdigest()
    require(
        "sha256:" + archive_sha256 == metadata_digest,
        "ARTIFACT_ZIP_DIGEST_MISMATCH",
    )

    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        infos = bundle.infolist()
        names = [item.filename for item in infos]
        require(
            len(names) == len(set(names)),
            "PROOF_ARTIFACT_DUPLICATE_MEMBER",
        )
        require(
            all(safe_zip_member(name) and not name.endswith("/") for name in names),
            "PROOF_ARTIFACT_UNSAFE_MEMBER_PATH",
        )
        require(
            set(names) == EXPECTED_MEMBERS and len(names) == len(EXPECTED_MEMBERS),
            "PROOF_ARTIFACT_MEMBERS_MISMATCH",
        )
        total_size = sum(item.file_size for item in infos)
        require(
            total_size <= MAX_PROOF_JSON_BYTES,
            "PROOF_ARTIFACT_UNCOMPRESSED_SIZE_LIMIT",
        )
        for item in infos:
            mode = (item.external_attr >> 16) & 0o170000
            require(
                not item.is_dir() and mode in (0, stat.S_IFREG),
                "PROOF_ARTIFACT_MEMBER_NOT_REGULAR_FILE",
            )
            require(
                item.file_size <= MAX_PROOF_JSON_BYTES,
                "PROOF_ARTIFACT_MEMBER_TOO_LARGE",
            )

        parsed = {}
        for name in EXPECTED_MEMBERS:
            parsed[name] = _json_object(
                bundle.read(name), "PROOF_ARTIFACT_JSON_INVALID:" + name
            )

    receipt = parsed["build-receipt.json"]
    cloud_proof = parsed["cloud-build-proof.json"]
    independent_receipt = parsed["independent-build-receipt.json"]
    require(
        cloud_proof == independent_receipt,
        "PROOF_ARTIFACT_INDEPENDENT_RECEIPTS_DISAGREE",
    )

    run_url = f"https://github.com/{REPO}/actions/runs/{run_id}"
    require(receipt.get("source_commit") == SOURCE, "PROOF_RECEIPT_SOURCE_MISMATCH")
    require(
        receipt.get("pr30_source_commit") == PR30_SOURCE,
        "PROOF_RECEIPT_PR30_SOURCE_MISMATCH",
    )
    require(
        receipt.get("workflow_head_sha") == expected_workflow_head,
        "PROOF_RECEIPT_WORKFLOW_HEAD_MISMATCH",
    )
    require(receipt.get("build_run_url") == run_url, "PROOF_RECEIPT_RUN_URL_MISMATCH")
    _positive_int(receipt.get("artifact_id"), "PROOF_RECEIPT_EXE_ARTIFACT_ID_INVALID")
    exe_size = _positive_int(
        receipt.get("exe_size_bytes"), "PROOF_RECEIPT_EXE_SIZE_INVALID"
    )
    exe_sha = receipt.get("exe_sha256")
    require(
        isinstance(exe_sha, str) and SHA256.fullmatch(exe_sha) is not None,
        "PROOF_RECEIPT_EXE_SHA_INVALID",
    )
    require(
        receipt.get("artifact_exe_path") == "SignalSprint.exe",
        "PROOF_RECEIPT_EXE_PATH_MISMATCH",
    )
    require(
        receipt.get("artifact_provenance_path") == "build-provenance.json",
        "PROOF_RECEIPT_PROVENANCE_PATH_MISMATCH",
    )

    require(
        cloud_proof.get("schema") == "signal-sprint-independent-build-v1",
        "PROOF_BUILD_SCHEMA_MISMATCH",
    )
    require(
        cloud_proof.get("status") == "PASS_INDEPENDENT_BUILD_ONLY",
        "PROOF_BUILD_STATUS_NOT_PASS",
    )
    require(cloud_proof.get("product_source") == SOURCE, "PROOF_BUILD_SOURCE_MISMATCH")
    require(
        cloud_proof.get("pr30_source_commit") == PR30_SOURCE,
        "PROOF_BUILD_PR30_SOURCE_MISMATCH",
    )
    require(cloud_proof.get("run_id") == run_id, "PROOF_BUILD_RUN_ID_MISMATCH")
    require(
        cloud_proof.get("artifact_id") == receipt.get("artifact_id"),
        "PROOF_BUILD_EXE_ARTIFACT_ID_MISMATCH",
    )
    require(
        cloud_proof.get("build_run_url") == run_url,
        "PROOF_BUILD_RUN_URL_MISMATCH",
    )
    require(
        cloud_proof.get("workflow_head_sha") == expected_workflow_head,
        "PROOF_BUILD_WORKFLOW_HEAD_MISMATCH",
    )
    require(
        cloud_proof.get("exe_sha256") == exe_sha,
        "PROOF_BUILD_EXE_SHA_MISMATCH",
    )
    require(
        cloud_proof.get("exe_size_bytes") == exe_size
        and cloud_proof.get("artifact_exe_size_bytes") == exe_size,
        "PROOF_BUILD_EXE_SIZE_MISMATCH",
    )
    require(
        cloud_proof.get("completed_run_required") is False
        and cloud_proof.get("run_status_at_verification") == "in_progress"
        and cloud_proof.get("run_conclusion") is None,
        "PROOF_BUILD_SELF_RUN_STATE_MISMATCH",
    )
    require(
        cloud_proof.get("independent_build_verified") is True
        and cloud_proof.get("build_provenance_verified") is True,
        "PROOF_BUILD_NOT_INDEPENDENTLY_VERIFIED",
    )
    require(
        cloud_proof.get("artifact_kind") == "EXE_QA_UNSIGNED",
        "PROOF_BUILD_ARTIFACT_KIND_MISMATCH",
    )
    require(
        cloud_proof.get("physical_gui_verified") is False,
        "PROOF_BUILD_PHYSICAL_GUI_FALSE_CLAIM",
    )
    require(
        cloud_proof.get("gdk_package_verified") is False,
        "PROOF_BUILD_GDK_FALSE_CLAIM",
    )
    require(
        cloud_proof.get("msix_status") == "NOT_BUILT",
        "PROOF_BUILD_MSIX_FALSE_CLAIM",
    )
    require(
        cloud_proof.get("product_acceptance") is False,
        "PROOF_BUILD_PRODUCT_ACCEPTANCE_FALSE_CLAIM",
    )
    exe_artifact_zip_sha = cloud_proof.get("artifact_zip_sha256")
    require(
        isinstance(exe_artifact_zip_sha, str)
        and SHA256.fullmatch(exe_artifact_zip_sha) is not None,
        "PROOF_BUILD_EXE_ARTIFACT_ZIP_SHA_INVALID",
    )
    _positive_int(
        cloud_proof.get("artifact_zip_size_bytes"),
        "PROOF_BUILD_EXE_ARTIFACT_ZIP_SIZE_INVALID",
    )

    return {
        "schema": "signal-sprint-proof-artifact-verification-v1",
        "status": "PASS_PROOF_ARTIFACT_BYTES_VERIFIED",
        "proof_artifact_id": artifact_id,
        "proof_artifact_name": ARTIFACT_NAME,
        "proof_artifact_digest": metadata_digest,
        "proof_artifact_zip_sha256": archive_sha256,
        "proof_artifact_zip_size_bytes": len(archive),
        "build_run_id": run_id,
        "workflow_head_sha": expected_workflow_head,
        "build_artifact_id": receipt["artifact_id"],
        "exe_sha256": exe_sha,
        "exe_size_bytes": exe_size,
        "source_commit": SOURCE,
        "pr30_source_commit": PR30_SOURCE,
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "msix_status": "NOT_BUILT",
        "product_acceptance": False,
        "build_receipt": receipt,
        "cloud_build_proof": cloud_proof,
        "independent_build_receipt": independent_receipt,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-repository-id", required=True)
    parser.add_argument("--expected-workflow-head", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt-output", required=True)
    args = parser.parse_args()

    result = {
        "schema": "signal-sprint-proof-artifact-verification-v1",
        "status": "FAIL_PROOF_ARTIFACT_VERIFICATION",
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "msix_status": "NOT_BUILT",
        "product_acceptance": False,
    }
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        result = verify(
            int(args.artifact_id),
            args.artifact_digest,
            args.expected_run_id,
            int(args.expected_repository_id),
            args.expected_workflow_head,
            token,
        )
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    success = result.get("status") == "PASS_PROOF_ARTIFACT_BYTES_VERIFIED"
    if success:
        proof_dir = Path(args.receipt_output).parent
        proof_dir.mkdir(parents=True, exist_ok=True)
        Path(args.receipt_output).write_text(
            json.dumps(result["build_receipt"], indent=2) + "\n", encoding="utf-8"
        )
        (proof_dir / "cloud-build-proof.json").write_text(
            json.dumps(result["cloud_build_proof"], indent=2) + "\n", encoding="utf-8"
        )
        (proof_dir / "independent-build-receipt.json").write_text(
            json.dumps(result["independent_build_receipt"], indent=2) + "\n",
            encoding="utf-8",
        )
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write("verified=" + ("true" if success else "false") + "\n")
            if success:
                handle.write("proof_artifact_zip_sha256=" + result["proof_artifact_zip_sha256"] + "\n")
                handle.write("proof_artifact_zip_size_bytes=" + str(result["proof_artifact_zip_size_bytes"]) + "\n")
    print(result.get("status", "FAIL_PROOF_ARTIFACT_VERIFICATION"))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
