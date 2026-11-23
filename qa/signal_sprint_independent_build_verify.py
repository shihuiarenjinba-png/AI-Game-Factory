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
from urllib.parse import urlsplit
import zipfile

REPO = "shihuiarenjinba-png/AI-Game-Factory"
SOURCE = "1a349faa41663c417c40710140a4d50c79b62b78"
API = "https://api.github.com/repos/" + REPO
SHA = re.compile(r"^[0-9a-f]{64}$")
RUN = re.compile(r"^https://github\.com/" + REPO + r"/actions/runs/([1-9][0-9]*)$")
BUILD_WORKFLOW_PATH = ".github/workflows/signal-sprint-cloud-build-proof.yml"
BUILD_WORKFLOW_EVENTS = {"push", "workflow_dispatch"}
BUILD_ARTIFACT_PREFIX = "signal-sprint-frozen-source-exe-"
MAX_BUILD_PROVENANCE_BYTES = 1024 * 1024
BUILD_JOB_NAME = "windows-frozen-source-exe"
MAX_API_JSON_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_ZIP_BYTES = 1024 * 1024 * 1024
MAX_ARTIFACT_UNCOMPRESSED_BYTES = 600 * 1024 * 1024
MAX_EXE_BYTES = 512 * 1024 * 1024


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward the GitHub bearer token to a cross-origin artifact blob host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            old_host = urlsplit(req.full_url).netloc.casefold()
            new_host = urlsplit(newurl).netloc.casefold()
            if old_host != new_host:
                for name in ("Authorization", "X-GitHub-Api-Version", "Accept"):
                    redirected.remove_header(name)
        return redirected


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
    opener = urllib.request.build_opener(SafeRedirectHandler())
    try:
        with opener.open(req, timeout=35) as response:
            # GitHub's artifact ZIP endpoint redirects under the JSON media type.
            # Apply the larger byte cap by endpoint path, not by the Accept header.
            limit = MAX_ARTIFACT_ZIP_BYTES if url.endswith("/zip") else MAX_API_JSON_BYTES
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                require(int(content_length) <= limit, "API_RESPONSE_TOO_LARGE")
            data = response.read(limit + 1)
            require(len(data) <= limit, "API_RESPONSE_TOO_LARGE")
            return data
    except urllib.error.HTTPError as exc:
        target = urlsplit(exc.url or url)
        raise RuntimeError(f"HTTP_ERROR_{exc.code}:{target.netloc}{target.path}") from exc


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
    # The proof workflow's run head is the QA harness; the artifact separately proves
    # that its Windows job checked out the immutable product source.
    require(run.get("path") == BUILD_WORKFLOW_PATH, "BUILD_WORKFLOW_PATH_MISMATCH")
    require(run.get("event") in BUILD_WORKFLOW_EVENTS, "BUILD_WORKFLOW_EVENT_INVALID")
    workflow_head_sha = receipt.get("workflow_head_sha")
    require(isinstance(workflow_head_sha, str) and bool(re.fullmatch(r"[0-9a-f]{40}", workflow_head_sha)), "WORKFLOW_HEAD_SHA_INVALID")
    require(run.get("head_sha") == workflow_head_sha, "WORKFLOW_HEAD_MISMATCH")
    require(run.get("id") == run_id and run.get("repository", {}).get("full_name") == REPO, "RUN_ID_OR_REPO_MISMATCH")
    require(run.get("status") in ("queued", "in_progress", "completed"), "RUN_NOT_ACTIVE_OR_COMPLETE")
    if run.get("status") == "completed":
        require(run.get("conclusion") == "success", "RUN_NOT_SUCCESS")
    jobs_payload = json.loads(fetch(f"{API}/actions/runs/{run_id}/jobs?per_page=100", token))
    jobs = jobs_payload.get("jobs")
    require(isinstance(jobs, list), "RUN_JOBS_INVALID")
    build_jobs = [job for job in jobs if job.get("name") == BUILD_JOB_NAME]
    require(len(build_jobs) == 1, "FROZEN_SOURCE_BUILD_JOB_NOT_UNIQUE")
    require(build_jobs[0].get("status") == "completed" and build_jobs[0].get("conclusion") == "success",
            "FROZEN_SOURCE_BUILD_JOB_NOT_SUCCESS")
    artifact = json.loads(fetch(f"{API}/actions/artifacts/{artifact_id}", token))
    require(artifact.get("id") == artifact_id and not artifact.get("expired", True), "ARTIFACT_INVALID_OR_EXPIRED")
    require(artifact.get("name") == BUILD_ARTIFACT_PREFIX + SOURCE, "BUILD_ARTIFACT_NAME_MISMATCH")
    require(artifact.get("workflow_run", {}).get("id") == run_id, "ARTIFACT_RUN_MISMATCH")
    require(artifact.get("workflow_run", {}).get("head_sha") == workflow_head_sha, "ARTIFACT_WORKFLOW_HEAD_MISMATCH")
    artifact_digest_header = artifact.get("digest")
    require(isinstance(artifact_digest_header, str)
            and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest_header)),
            "ARTIFACT_DIGEST_INVALID")
    archive = fetch(f"{API}/actions/artifacts/{artifact_id}/zip", token)
    require(isinstance(archive, (bytes, bytearray)) and len(archive) <= MAX_ARTIFACT_ZIP_BYTES, "ARTIFACT_ZIP_TOO_LARGE_OR_INVALID")
    archive_sha256 = hashlib.sha256(archive).hexdigest()
    require(artifact_digest_header == "sha256:" + archive_sha256, "ARTIFACT_ARCHIVE_DIGEST_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        infos = z.infolist()
        names = [info.filename for info in infos]
        require(len(names) == len(set(names)), "ARTIFACT_DUPLICATE_MEMBER")
        require(all(safe_zip_member(name) for name in names), "ARTIFACT_UNSAFE_MEMBER_PATH")
        require(sum(info.file_size for info in infos) <= MAX_ARTIFACT_UNCOMPRESSED_BYTES, "ARTIFACT_UNCOMPRESSED_SIZE_LIMIT")
        provenance_member = receipt.get("artifact_provenance_path")
        require(isinstance(provenance_member, str) and safe_zip_member(provenance_member)
                and not provenance_member.endswith("/") and provenance_member != member,
                "ARTIFACT_PROVENANCE_PATH_INVALID")
        require(names.count(member) == 1, "ARTIFACT_EXE_MISSING_OR_DUPLICATE")
        require(names.count(provenance_member) == 1, "ARTIFACT_PROVENANCE_MISSING_OR_DUPLICATE")
        info = z.getinfo(member)
        mode = (info.external_attr >> 16) & 0o170000
        require(not info.is_dir() and mode in (0, stat.S_IFREG), "ARTIFACT_MEMBER_NOT_REGULAR_FILE")
        require(info.file_size <= MAX_EXE_BYTES, "ARTIFACT_EXE_TOO_LARGE")
        with z.open(info) as stream:
            artifact_digest, artifact_size = hash_stream(stream, MAX_EXE_BYTES, "ARTIFACT_EXE_TOO_LARGE")
        require(artifact_size == info.file_size, "ARTIFACT_EXE_SIZE_MISMATCH")
        require(local_size == artifact_size, "LOCAL_EXE_SIZE_MISMATCH")
        provenance_info = z.getinfo(provenance_member)
        provenance_mode = (provenance_info.external_attr >> 16) & 0o170000
        require(not provenance_info.is_dir() and provenance_mode in (0, stat.S_IFREG),
                "ARTIFACT_PROVENANCE_NOT_REGULAR_FILE")
        require(provenance_info.file_size <= MAX_BUILD_PROVENANCE_BYTES, "ARTIFACT_PROVENANCE_TOO_LARGE")
        provenance = json.loads(z.read(provenance_info))
        require(isinstance(provenance, dict), "ARTIFACT_PROVENANCE_NOT_OBJECT")
        require(provenance.get("source_commit") == SOURCE, "ARTIFACT_PROVENANCE_SOURCE_MISMATCH")
        require(provenance.get("workflow_head_sha") == workflow_head_sha, "ARTIFACT_PROVENANCE_WORKFLOW_HEAD_MISMATCH")
        require(provenance.get("build_run_id") == run_id, "ARTIFACT_PROVENANCE_RUN_ID_MISMATCH")
        require(provenance.get("exe_sha256") == digest, "ARTIFACT_PROVENANCE_EXE_SHA_MISMATCH")
        require(provenance.get("artifact_kind") == "EXE_QA_UNSIGNED", "ARTIFACT_KIND_NOT_UNSIGNED_EXE")
        require(provenance.get("msix_status") == "NOT_BUILT", "MSIX_MUST_REMAIN_NOT_BUILT")
        require(provenance.get("gdk_package_verified") is False, "GDK_PACKAGE_MUST_NOT_BE_CLAIMED")
        require(provenance.get("physical_gui_verified") is False, "PHYSICAL_GUI_MUST_NOT_BE_CLAIMED")
    require(artifact_digest == digest, "ARTIFACT_EXE_SHA_MISMATCH")
    return {"schema": "signal-sprint-independent-build-v1",
            "status": "PASS_INDEPENDENT_BUILD_ONLY", "product_source": SOURCE,
            "run_id": run_id, "artifact_id": artifact_id,
            "build_job_name": BUILD_JOB_NAME, "run_status_at_verification": run.get("status"),
            "artifact_exe_path": member, "artifact_provenance_path": provenance_member,
            "artifact_zip_sha256": archive_sha256, "artifact_zip_size_bytes": len(archive),
            "exe_size_bytes": local_size,
            "workflow_head_sha": workflow_head_sha, "exe_sha256": digest,
            "build_provenance_verified": True, "independent_build_verified": True,
            "physical_gui_verified": False, "artifact_kind": "EXE_QA_UNSIGNED",
            "msix_status": "NOT_BUILT", "gdk_package_verified": False}


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
