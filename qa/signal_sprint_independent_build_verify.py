"""Fail-closed GitHub build provenance verifier. Does not certify physical GUI or GDK packaging."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import urllib.error
import urllib.request
import zipfile

REPO = "shihuiarenjinba-png/AI-Game-Factory"
SOURCE = "1a349faa41663c417c40710140a4d50c79b62b78"
API = "https://api.github.com/repos/" + REPO
SHA = re.compile(r"^[0-9a-f]{64}$")
RUN = re.compile(r"^https://github\.com/" + REPO + r"/actions/runs/([1-9][0-9]*)$")
MAX_API_JSON_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_ZIP_BYTES = 1024 * 1024 * 1024
MAX_ARTIFACT_UNCOMPRESSED_BYTES = 600 * 1024 * 1024
MAX_EXE_BYTES = 512 * 1024 * 1024


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
        limit = MAX_ARTIFACT_ZIP_BYTES if accept == "application/octet-stream" else MAX_API_JSON_BYTES
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            require(int(content_length) <= limit, "API_RESPONSE_TOO_LARGE")
        data = response.read(limit + 1)
        require(len(data) <= limit, "API_RESPONSE_TOO_LARGE")
        return data


def hash_stream(stream, limit, reason):
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        require(total <= limit, reason)
        digest.update(chunk)
    return digest.hexdigest(), total


def hash_file(path, limit, reason):
    with Path(path).open("rb") as stream:
        return hash_stream(stream, limit, reason)


def safe_zip_member(name):
    normalized = name[:-1] if name.endswith("/") else name
    parts = normalized.split("/")
    return (
        bool(normalized)
        and not name.startswith("/")
        and "\\" not in name
        and all(part not in ("", ".", "..") for part in parts)
        and ":" not in parts[0]
    )


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
    require(isinstance(member, str) and safe_zip_member(member) and not member.endswith("/"), "ARTIFACT_EXE_PATH_INVALID")
    digest, local_size = hash_file(exe_path, MAX_EXE_BYTES, "LOCAL_EXE_TOO_LARGE")
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
    require(isinstance(archive, (bytes, bytearray)) and len(archive) <= MAX_ARTIFACT_ZIP_BYTES, "ARTIFACT_ZIP_TOO_LARGE_OR_INVALID")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        infos = z.infolist()
        names = [info.filename for info in infos]
        require(len(names) == len(set(names)), "ARTIFACT_DUPLICATE_MEMBER")
        require(all(safe_zip_member(name) for name in names), "ARTIFACT_UNSAFE_MEMBER_PATH")
        require(sum(info.file_size for info in infos) <= MAX_ARTIFACT_UNCOMPRESSED_BYTES, "ARTIFACT_UNCOMPRESSED_SIZE_LIMIT")
        require(names.count(member) == 1, "ARTIFACT_EXE_MISSING_OR_DUPLICATE")
        info = z.getinfo(member)
        mode = (info.external_attr >> 16) & 0o170000
        require(not info.is_dir() and mode in (0, stat.S_IFREG), "ARTIFACT_MEMBER_NOT_REGULAR_FILE")
        require(info.file_size <= MAX_EXE_BYTES, "ARTIFACT_EXE_TOO_LARGE")
        with z.open(info) as stream:
            artifact_digest, artifact_size = hash_stream(stream, MAX_EXE_BYTES, "ARTIFACT_EXE_TOO_LARGE")
        require(artifact_size == info.file_size, "ARTIFACT_EXE_SIZE_MISMATCH")
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
