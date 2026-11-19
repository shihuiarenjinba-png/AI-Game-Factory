"""Fail-closed GitHub build provenance verifier. Does not certify physical GUI or GDK packaging."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import zipfile

REPO = "shihuiarenjinba-png/AI-Game-Factory"
SOURCE = "1a349faa41663c417c40710140a4d50c79b62b78"
API = "https://api.github.com/repos/" + REPO
SHA = re.compile(r"^[0-9a-f]{64}$")
RUN = re.compile(r"^https://github\\.com/" + REPO + r"/actions/runs/([1-9][0-9]*)$")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def get(url, token, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "signal-sprint-build-provenance",
    })
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read()


def verify(receipt, exe_path, token, fetch=get):
    require(isinstance(receipt, dict), "RECEIPT_NOT_OBJECT")
    require(receipt.get("source_commit") == SOURCE, "BUILD_SOURCE_MISMATCH")
    require(isinstance(receipt.get("exe_sha256"), str) and bool(SHA.fullmatch(receipt["exe_sha256"].lower())), "RECEIPT_SHA_INVALID")
    require(isinstance(receipt.get("build_run_url"), str), "RUN_URL_MISSING")
    match = RUN.fullmatch(receipt["build_run_url"])
    require(match is not None, "RUN_URL_INVALID")
    run_id = int(match.group(1))
    artifact_id = receipt.get("artifact_id")
    require(type(artifact_id) is int and artifact_id > 0, "ARTIFACT_ID_INVALID")
    member = receipt.get("artifact_exe_path")
    require(isinstance(member, str) and member and not member.startswith("/") and "\\" not in member and ".." not in member.split("/"), "ARTIFACT_EXE_PATH_INVALID")
    exe = Path(exe_path).read_bytes()
    digest = hashlib.sha256(exe).hexdigest()
    require(digest == receipt["exe_sha256"].lower(), "LOCAL_EXE_SHA_MISMATCH")
    run = json.loads(fetch(f"{API}/actions/runs/{run_id}", token))
    require(run.get("id") == run_id and run.get("repository", {}).get("full_name") == REPO, "RUN_ID_OR_REPO_MISMATCH")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "RUN_NOT_SUCCESS")
    require(run.get("head_sha") == SOURCE, "RUN_SOURCE_MISMATCH")
    artifact = json.loads(fetch(f"{API}/actions/artifacts/{artifact_id}", token))
    require(artifact.get("id") == artifact_id and not artifact.get("expired", True), "ARTIFACT_INVALID_OR_EXPIRED")
    require(artifact.get("workflow_run", {}).get("id") == run_id, "ARTIFACT_RUN_MISMATCH")
    require(artifact.get("workflow_run", {}).get("head_sha") == SOURCE, "ARTIFACT_SOURCE_MISMATCH")
    archive = fetch(f"{API}/actions/artifacts/{artifact_id}/zip", token, "application/octet-stream")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names = z.namelist()
        require(names.count(member) == 1, "ARTIFACT_EXE_MISSING_OR_DUPLICATE")
        require(not z.getinfo(member).is_dir(), "ARTIFACT_MEMBER_NOT_FILE")
        with z.open(member) as stream:
            artifact_digest = hashlib.sha256(stream.read()).hexdigest()
    require(artifact_digest == digest, "ARTIFACT_EXE_SHA_MISMATCH")
    return {"schema": "signal-sprint-independent-build-v1",
            "status": "PASS_INDEPENDENT_BUILD_ONLY", "product_source": SOURCE,
            "run_id": run_id, "artifact_id": artifact_id,
            "artifact_exe_path": member, "exe_sha256": digest,
            "independent_build_verified": True, "physical_gui_verified": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = {"schema": "signal-sprint-independent-build-v1", "status": "FAIL",
              "independent_build_verified": False, "physical_gui_verified": False}
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        require(bool(token), "GITHUB_TOKEN_MISSING")
        receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8-sig"))
        result = verify(receipt, args.exe, token)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(result["status"])
    return 0 if result["independent_build_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
