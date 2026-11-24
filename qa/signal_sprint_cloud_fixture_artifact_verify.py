"""Verify the uploaded cloud provenance fixture Artifact bytes and embedded JSON.

This is cloud provenance only. It never certifies physical GUI, GDK packaging,
ordinary MSIX, or product acceptance.
"""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import zipfile

from signal_sprint_independent_build_verify import SafeRedirectHandler, safe_zip_member

REPO = "shihuiarenjinba-png/AI-Game-Factory"
API = "https://api.github.com/repos/" + REPO
ARTIFACT_NAME = "signal-sprint-cloud-provenance-fixture"
ARTIFACT_MEMBER = "cloud-provenance-fixture.json"
SOURCE = "1a349faa41663c417c40710140a4d50c79b62b78"
REFERENCE_WIN_LOSE_HEAD = "9ccd7ff4389b3ca0e45c8407d7369a00f4302cf2"
SCHEMA = "signal-sprint-cloud-fixture-v11"
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SHA40 = re.compile(r"^[a-f0-9]{40}$")
ARTIFACT_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
PASS_RESULTS = {"PASS_SYNTHETIC", "PASS_REJECTED", "PASS_STATIC_ONLY"}
MINIMUM_RESULT_COUNTS = {
    "PASS_SYNTHETIC": 13,
    "PASS_REJECTED": 368,
    "PASS_STATIC_ONLY": 144,
}

SOURCE_HASH_PATHS = {
    "fixture_source_sha256": "qa/signal_sprint_cloud_provenance_fixture.py",
    "artifact_verifier_source_sha256": "qa/signal_sprint_cloud_fixture_artifact_verify.py",
    "uia_workflow_source_sha256": ".github/workflows/signal-sprint-windows-uia-evidence.yml",
    "uia_gate_source_sha256": "qa/signal_sprint_uia_dynamic_gate.ps1",
    "independent_verifier_source_sha256": "qa/signal_sprint_independent_build_verify.py",
    "proof_artifact_verifier_source_sha256": "qa/signal_sprint_proof_artifact_verify.py",
    "build_run_discovery_source_sha256": "qa/signal_sprint_completed_build_discovery.py",
    "gdk_current_source_intake_source_sha256": "qa/signal_sprint_gdk_current_source_intake.py",
    "gdk_current_source_intake_test_source_sha256": "products/signal-sprint/tests/test_gdk_current_source_intake.py",
    "cloud_build_workflow_source_sha256": ".github/workflows/signal-sprint-cloud-build-proof.yml",
}

REQUIRED_CASES = {
    "EN exact 5-button/LOST source contract",
    "artifact verifier self-source hash is recorded in the fixture",
    "JP exact 5-button/LOST source contract",
    "dynamic UIA semantic assertions present",
    "Windows UIA binding guard exact button set and duplicate rejection",
    "Windows UIA binding guard localized LOST nodes",
    "Windows UIA binding guard Load case LOST assertion",
    "Windows UIA binding guard Start LOST precondition",
    "Windows UIA binding guard Start LOST-to-PLAYING transition",
    "Windows UIA binding guard measured EXE hash binding",
    "Windows UIA binding guard independent build run/artifact binding",
    "Windows UIA binding guard EXE SHA must match completed attestation",
    "physical UIA runner gated by hosted exact-head revision preflight",
    "cloud fixture Artifact verifier source has exact run/head/digest/member/source-hash guards",
    "cloud fixture Artifact verification workflow self-test and upload contract present",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def json_object(raw, reason):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError(reason) from exc
    require(isinstance(value, dict), reason)
    return value


def positive_int(value, reason):
    require(type(value) is int and value > 0, reason)
    return value


def get_limited(url, token):
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "signal-sprint-cloud-fixture-artifact-verifier",
    })
    opener = urllib.request.build_opener(SafeRedirectHandler())
    limit = MAX_ARTIFACT_BYTES if url.endswith("/zip") else MAX_JSON_BYTES
    try:
        with opener.open(request, timeout=35) as response:
            length = response.headers.get("Content-Length")
            require(length is None or int(length) <= limit,
                    "CLOUD_FIXTURE_ARTIFACT_RESPONSE_TOO_LARGE")
            data = response.read(limit + 1)
            require(len(data) <= limit, "CLOUD_FIXTURE_ARTIFACT_RESPONSE_TOO_LARGE")
            return data
    except urllib.error.HTTPError as exc:
        target = urlsplit(exc.url or url)
        raise RuntimeError(
            f"CLOUD_FIXTURE_ARTIFACT_HTTP_ERROR_{exc.code}:{target.netloc}{target.path}"
        ) from exc


def fetch_artifact_zip(url, token, fetch, sleep_fn=time.sleep):
    """Retry only transient GitHub artifact-download visibility/rate-limit failures."""
    parsed = urlsplit(url)
    expected_target = f":{parsed.netloc}{parsed.path}"
    retryable_codes = {"404", "429", "500", "502", "503", "504"}
    for attempt in range(6):
        try:
            return fetch(url, token)
        except RuntimeError as exc:
            message = str(exc)
            retryable = any(
                f"CLOUD_FIXTURE_ARTIFACT_HTTP_ERROR_{code}{expected_target}" in message
                for code in retryable_codes
            )
            if not retryable or attempt == 5:
                raise
            sleep_fn(attempt + 1)


def source_hashes(source_root):
    root = Path(source_root)
    result = {}
    for field, relative in SOURCE_HASH_PATHS.items():
        path = root / relative
        require(path.is_file(), "CLOUD_FIXTURE_SOURCE_FILE_MISSING:" + relative)
        result[field] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def validate_fixture(fixture, run_id, repository_id, workflow_head, source_root):
    require(fixture.get("schema") == SCHEMA, "CLOUD_FIXTURE_JSON_SCHEMA_MISMATCH")
    require(fixture.get("status") == "PASS", "CLOUD_FIXTURE_JSON_STATUS_NOT_PASS")
    require(fixture.get("failure") is None, "CLOUD_FIXTURE_JSON_FAILURE_PRESENT")
    require(fixture.get("workflow_head") == workflow_head, "CLOUD_FIXTURE_JSON_HEAD_MISMATCH")
    require(fixture.get("actions_run_id") == str(run_id), "CLOUD_FIXTURE_JSON_ACTION_RUN_MISMATCH")
    require(fixture.get("product_source") == SOURCE, "CLOUD_FIXTURE_JSON_SOURCE_MISMATCH")
    require(fixture.get("reference_win_lose_head") == REFERENCE_WIN_LOSE_HEAD,
            "CLOUD_FIXTURE_JSON_REVISION_MISMATCH")
    require(fixture.get("source_alignment") == "UNVERIFIED_DIFFERENT_SOURCE_REFS",
            "CLOUD_FIXTURE_JSON_SOURCE_ALIGNMENT_MISMATCH")
    require(fixture.get("functional_gate") == "HOLD_REAL_WINDOWS_UIA",
            "CLOUD_FIXTURE_JSON_FUNCTIONAL_GATE_MISMATCH")
    require(fixture.get("delivery_gate") == "HOLD_GDK_PACKAGE",
            "CLOUD_FIXTURE_JSON_DELIVERY_GATE_MISMATCH")
    require(fixture.get("independent_build_verified") is False,
            "CLOUD_FIXTURE_JSON_FALSE_BUILD_CLAIM")
    require(fixture.get("physical_gui_verified") is False,
            "CLOUD_FIXTURE_JSON_FALSE_GUI_CLAIM")
    require(fixture.get("gdk_package_verified") is False,
            "CLOUD_FIXTURE_JSON_FALSE_GDK_CLAIM")
    require(fixture.get("product_acceptance") is False,
            "CLOUD_FIXTURE_JSON_PRODUCT_ACCEPTANCE_TRUE")
    require(fixture.get("msix_status") == "NOT_BUILT",
            "CLOUD_FIXTURE_JSON_MSIX_CLAIM_INVALID")

    for field, expected in source_hashes(source_root).items():
        actual = fixture.get(field)
        require(isinstance(actual, str) and SHA256.fullmatch(actual),
                "CLOUD_FIXTURE_JSON_SOURCE_HASH_INVALID:" + field)
        require(actual == expected, "CLOUD_FIXTURE_SOURCE_HASH_MISMATCH:" + field)

    results = fixture.get("results")
    require(isinstance(results, list) and len(results) >= 100,
            "CLOUD_FIXTURE_JSON_RESULT_COUNT_INVALID")
    cases = {}
    counts = {}
    for item in results:
        require(isinstance(item, dict), "CLOUD_FIXTURE_JSON_RESULT_ITEM_INVALID")
        case, status = item.get("case"), item.get("result")
        require(isinstance(case, str) and case, "CLOUD_FIXTURE_JSON_CASE_INVALID")
        require(case not in cases, "CLOUD_FIXTURE_RESULT_DUPLICATE_CASE:" + case)
        require(status in PASS_RESULTS, "CLOUD_FIXTURE_RESULT_STATUS_INVALID:" + case)
        cases[case] = status
        counts[status] = counts.get(status, 0) + 1

    missing = sorted(REQUIRED_CASES - set(cases))
    require(not missing, "CLOUD_FIXTURE_REQUIRED_CASE_MISSING:" + ",".join(missing))
    for case in REQUIRED_CASES:
        require(cases[case] == "PASS_STATIC_ONLY",
                "CLOUD_FIXTURE_REQUIRED_CASE_NOT_STATIC_PASS:" + case)
    for status, minimum in MINIMUM_RESULT_COUNTS.items():
        require(counts.get(status, 0) >= minimum,
                "CLOUD_FIXTURE_RESULT_COUNT_BELOW_MINIMUM:" + status)
    return {"result_count": len(results), "result_counts": counts,
            "required_case_count": len(REQUIRED_CASES),
            "source_hashes_verified": len(SOURCE_HASH_PATHS)}


def verify(expected_run_id, expected_repository_id, expected_workflow_head,
           token, source_root=".", fetch=get_limited, sleep_fn=time.sleep):
    require(isinstance(expected_run_id, str) and re.fullmatch(r"[1-9][0-9]*", expected_run_id),
            "CLOUD_FIXTURE_EXPECTED_RUN_ID_INVALID")
    run_id = int(expected_run_id)
    repository_id = positive_int(expected_repository_id,
                                 "CLOUD_FIXTURE_EXPECTED_REPOSITORY_ID_INVALID")
    require(isinstance(expected_workflow_head, str) and SHA40.fullmatch(expected_workflow_head),
            "CLOUD_FIXTURE_EXPECTED_HEAD_INVALID")
    require(isinstance(token, str) and token, "GITHUB_TOKEN_MISSING")

    listing_url = f"{API}/actions/runs/{run_id}/artifacts?per_page=100"
    listing = None
    artifacts = None
    exact = []
    # GitHub can expose total_count before all Artifact rows are visible, and
    # a just-finalized upload may take a few seconds to appear in the list.
    for attempt in range(10):
        listing = json_object(fetch(listing_url, token), "CLOUD_FIXTURE_ARTIFACT_LIST_INVALID")
        artifacts = listing.get("artifacts")
        require(isinstance(artifacts, list), "CLOUD_FIXTURE_ARTIFACT_COLLECTION_INVALID")
        total_count = listing.get("total_count")
        require(type(total_count) is int and 0 <= total_count <= 100 and total_count >= len(artifacts),
                "CLOUD_FIXTURE_ARTIFACT_COLLECTION_COUNT_INVALID")
        exact = [item for item in artifacts
                 if isinstance(item, dict) and item.get("name") == ARTIFACT_NAME]
        require(len(exact) <= 1, "CLOUD_FIXTURE_ARTIFACT_DUPLICATE")
        if total_count == len(artifacts) and len(exact) == 1:
            break
        if attempt < 9:
            sleep_fn(1)
    else:
        if not exact:
            raise ValueError("CLOUD_FIXTURE_ARTIFACT_NOT_VISIBLE")
        raise ValueError("CLOUD_FIXTURE_ARTIFACT_COLLECTION_INCOMPLETE")
    listed = exact[0]
    artifact_id = positive_int(listed.get("id"), "CLOUD_FIXTURE_ARTIFACT_ID_INVALID")

    metadata = json_object(
        fetch(f"{API}/actions/artifacts/{artifact_id}", token),
        "CLOUD_FIXTURE_ARTIFACT_METADATA_INVALID",
    )
    require(metadata.get("id") == artifact_id, "CLOUD_FIXTURE_ARTIFACT_ID_MISMATCH")
    require(metadata.get("name") == ARTIFACT_NAME, "CLOUD_FIXTURE_ARTIFACT_NAME_MISMATCH")
    require(metadata.get("expired") is False, "CLOUD_FIXTURE_ARTIFACT_EXPIRED")
    size = positive_int(metadata.get("size_in_bytes"), "CLOUD_FIXTURE_ARTIFACT_SIZE_INVALID")
    require(size <= MAX_ARTIFACT_BYTES, "CLOUD_FIXTURE_ARTIFACT_TOO_LARGE")
    digest = metadata.get("digest")
    require(isinstance(digest, str) and ARTIFACT_DIGEST.fullmatch(digest),
            "CLOUD_FIXTURE_ARTIFACT_METADATA_DIGEST_INVALID")
    require(digest == listed.get("digest"),
            "CLOUD_FIXTURE_ARTIFACT_METADATA_DIGEST_MISMATCH")
    require(size == listed.get("size_in_bytes"),
            "CLOUD_FIXTURE_ARTIFACT_METADATA_SIZE_MISMATCH")

    run = metadata.get("workflow_run")
    require(isinstance(run, dict), "CLOUD_FIXTURE_ARTIFACT_WORKFLOW_RUN_MISSING")
    require(run.get("id") == run_id, "CLOUD_FIXTURE_ARTIFACT_RUN_MISMATCH")
    require(run.get("head_sha") == expected_workflow_head,
            "CLOUD_FIXTURE_ARTIFACT_HEAD_MISMATCH")
    require(run.get("repository_id") == repository_id,
            "CLOUD_FIXTURE_ARTIFACT_REPOSITORY_MISMATCH")
    require(run.get("head_repository_id") == repository_id,
            "CLOUD_FIXTURE_ARTIFACT_HEAD_REPOSITORY_MISMATCH")

    archive = fetch_artifact_zip(
        f"{API}/actions/artifacts/{artifact_id}/zip", token, fetch, sleep_fn=sleep_fn
    )
    require(isinstance(archive, (bytes, bytearray)) and 0 < len(archive) <= MAX_ARTIFACT_BYTES,
            "CLOUD_FIXTURE_ARTIFACT_DOWNLOAD_SIZE_INVALID")
    require(len(archive) == size, "CLOUD_FIXTURE_ARTIFACT_ZIP_SIZE_MISMATCH")
    archive_sha = hashlib.sha256(archive).hexdigest()
    require("sha256:" + archive_sha == digest,
            "CLOUD_FIXTURE_ARTIFACT_ZIP_DIGEST_MISMATCH")

    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            infos = bundle.infolist()
            names = [item.filename for item in infos]
            require(len(names) == len(set(names)), "CLOUD_FIXTURE_ARTIFACT_DUPLICATE_MEMBER")
            require(len(infos) == 1 and names == [ARTIFACT_MEMBER],
                    "CLOUD_FIXTURE_ARTIFACT_MEMBER_MISMATCH")
            info = infos[0]
            require(safe_zip_member(info.filename) and not info.is_dir(),
                    "CLOUD_FIXTURE_ARTIFACT_UNSAFE_MEMBER")
            mode = (info.external_attr >> 16) & 0o170000
            require(mode in (0, stat.S_IFREG),
                    "CLOUD_FIXTURE_ARTIFACT_MEMBER_NOT_REGULAR_FILE")
            require(0 < info.file_size <= MAX_JSON_BYTES,
                    "CLOUD_FIXTURE_ARTIFACT_JSON_SIZE_INVALID")
            fixture = json_object(bundle.read(ARTIFACT_MEMBER),
                                  "CLOUD_FIXTURE_ARTIFACT_JSON_INVALID")
    except zipfile.BadZipFile as exc:
        raise ValueError("CLOUD_FIXTURE_ARTIFACT_ZIP_INVALID") from exc

    summary = validate_fixture(fixture, run_id, repository_id,
                               expected_workflow_head, source_root)
    return {
        "schema": "signal-sprint-cloud-fixture-artifact-verification-v1",
        "status": "PASS_CLOUD_FIXTURE_ARTIFACT_VERIFIED",
        "artifact_id": artifact_id,
        "artifact_name": ARTIFACT_NAME,
        "artifact_digest": digest,
        "artifact_zip_sha256": archive_sha,
        "artifact_zip_size_bytes": len(archive),
        "workflow_run_id": run_id,
        "workflow_head_sha": expected_workflow_head,
        "repository_id": repository_id,
        "fixture_schema": fixture["schema"],
        "fixture_source_sha256": fixture["fixture_source_sha256"],
        "artifact_verifier_source_sha256": fixture["artifact_verifier_source_sha256"],
        "uia_workflow_source_sha256": fixture["uia_workflow_source_sha256"],
        "fixture_result_count": summary["result_count"],
        "fixture_result_counts": summary["result_counts"],
        "required_case_count": summary["required_case_count"],
        "source_hashes_verified": summary["source_hashes_verified"],
        "product_source": SOURCE,
        "reference_win_lose_head": REFERENCE_WIN_LOSE_HEAD,
        "independent_build_verified": False,
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "msix_status": "NOT_BUILT",
        "product_acceptance": False,
    }


def make_zip(fixture, member=ARTIFACT_MEMBER):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(member, json.dumps(fixture, ensure_ascii=False).encode("utf-8"))
    return stream.getvalue()


def self_test():
    tests = 0
    head, run_id, repo_id, token = "b" * 40, "12345", 1434022838, "synthetic-token"
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        hashes = {}
        for field, relative in SOURCE_HASH_PATHS.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("source:" + relative).encode("utf-8"))
            hashes[field] = hashlib.sha256(path.read_bytes()).hexdigest()
        results = [{"case": case, "result": "PASS_STATIC_ONLY"}
                   for case in sorted(REQUIRED_CASES)]
        results += [{"case": f"self-test synthetic {i:03d}", "result": "PASS_SYNTHETIC"}
                    for i in range(MINIMUM_RESULT_COUNTS["PASS_SYNTHETIC"])]
        results += [{"case": f"self-test rejected {i:03d}", "result": "PASS_REJECTED"}
                    for i in range(MINIMUM_RESULT_COUNTS["PASS_REJECTED"])]
        results += [{"case": f"self-test filler {i:03d}", "result": "PASS_STATIC_ONLY"}
                    for i in range(MINIMUM_RESULT_COUNTS["PASS_STATIC_ONLY"] - len(REQUIRED_CASES))]
        fixture = {
            "schema": SCHEMA, "status": "PASS", "failure": None,
            "workflow_head": head, "actions_run_id": run_id, **hashes,
            "product_source": SOURCE, "reference_win_lose_head": REFERENCE_WIN_LOSE_HEAD,
            "source_alignment": "UNVERIFIED_DIFFERENT_SOURCE_REFS",
            "functional_gate": "HOLD_REAL_WINDOWS_UIA", "delivery_gate": "HOLD_GDK_PACKAGE",
            "independent_build_verified": False, "physical_gui_verified": False,
            "gdk_package_verified": False, "product_acceptance": False,
            "msix_status": "NOT_BUILT", "results": results,
        }
        state = {}

        def reset(payload=None, member=ARTIFACT_MEMBER):
            archive = make_zip(copy.deepcopy(payload if payload is not None else fixture), member)
            digest = "sha256:" + hashlib.sha256(archive).hexdigest()
            metadata = {
                "id": 98765, "name": ARTIFACT_NAME, "expired": False,
                "size_in_bytes": len(archive), "digest": digest,
                "workflow_run": {"id": int(run_id), "repository_id": repo_id,
                                 "head_repository_id": repo_id, "head_sha": head},
            }
            state.clear()
            state.update({"metadata": metadata, "artifacts": [copy.deepcopy(metadata)],
                          "archive": archive, "list_reads": 0, "simulate_listing_race": False,
                          "simulate_fixture_visibility": False, "zip_reads": 0,
                          "simulate_zip_visibility": 0})

        list_url = f"{API}/actions/runs/{run_id}/artifacts?per_page=100"

        def fake_fetch(url, supplied_token):
            require(supplied_token == token, "SELF_TEST_TOKEN_MISMATCH")
            if url == list_url:
                state["list_reads"] += 1
                total = len(state["artifacts"])
                if state["simulate_listing_race"] and state["list_reads"] == 1:
                    total += 1
                if state["simulate_fixture_visibility"] and state["list_reads"] == 1:
                    return json.dumps({"total_count": total, "artifacts": []}).encode()
                return json.dumps({"total_count": total,
                                   "artifacts": state["artifacts"]}).encode()
            if url == f"{API}/actions/artifacts/98765":
                return json.dumps(state["metadata"]).encode()
            if url == f"{API}/actions/artifacts/98765/zip":
                state["zip_reads"] += 1
                if state["zip_reads"] <= state["simulate_zip_visibility"]:
                    parsed = urlsplit(url)
                    raise RuntimeError(
                        "CLOUD_FIXTURE_ARTIFACT_HTTP_ERROR_404:"
                        + parsed.netloc + parsed.path
                    )
                return state["archive"]
            raise ValueError("SELF_TEST_UNEXPECTED_URL:" + url)

        def repack(payload):
            state["archive"] = make_zip(payload)
            state["metadata"]["size_in_bytes"] = len(state["archive"])
            state["metadata"]["digest"] = "sha256:" + hashlib.sha256(state["archive"]).hexdigest()
            state["artifacts"][0]["size_in_bytes"] = state["metadata"]["size_in_bytes"]
            state["artifacts"][0]["digest"] = state["metadata"]["digest"]

        def accepted():
            result = verify(run_id, repo_id, head, token, source_root=root,
                            fetch=fake_fetch, sleep_fn=lambda _seconds: None)
            require(result["status"] == "PASS_CLOUD_FIXTURE_ARTIFACT_VERIFIED",
                    "SELF_TEST_POSITIVE_NOT_VERIFIED")

        def rejected(label, expected, mutation):
            nonlocal tests
            reset()
            mutation()
            try:
                verify(run_id, repo_id, head, token, source_root=root,
                       fetch=fake_fetch, sleep_fn=lambda _seconds: None)
            except (ValueError, RuntimeError, zipfile.BadZipFile) as exc:
                require(expected in str(exc), "SELF_TEST_WRONG_REJECTION:" + label + ":" + str(exc))
            else:
                raise AssertionError("SELF_TEST_MUTATION_ACCEPTED:" + label)
            tests += 1

        reset()
        accepted()
        tests += 1
        reset()
        state["simulate_listing_race"] = True
        accepted()
        tests += 1
        reset()
        state["simulate_fixture_visibility"] = True
        accepted()
        tests += 1
        reset()
        state["simulate_zip_visibility"] = 2
        accepted()
        tests += 1
        rejected("artifact ZIP persistent 404", "CLOUD_FIXTURE_ARTIFACT_HTTP_ERROR_404",
                 lambda: state.update({"simulate_zip_visibility": 6}))
        rejected("digest", "CLOUD_FIXTURE_ARTIFACT_ZIP_DIGEST_MISMATCH",
                 lambda: (state["metadata"].update({"digest": "sha256:" + "0" * 64}),
                          state["artifacts"][0].update({"digest": "sha256:" + "0" * 64})))
        rejected("head", "CLOUD_FIXTURE_ARTIFACT_HEAD_MISMATCH",
                 lambda: (state["metadata"]["workflow_run"].update({"head_sha": "c" * 40}),
                          state["artifacts"][0]["workflow_run"].update({"head_sha": "c" * 40})))
        rejected("repository", "CLOUD_FIXTURE_ARTIFACT_REPOSITORY_MISMATCH",
                 lambda: (state["metadata"]["workflow_run"].update({"repository_id": 1}),
                          state["artifacts"][0]["workflow_run"].update({"repository_id": 1})))
        rejected("expired", "CLOUD_FIXTURE_ARTIFACT_EXPIRED",
                 lambda: (state["metadata"].update({"expired": True}),
                          state["artifacts"][0].update({"expired": True})))
        rejected("duplicate", "CLOUD_FIXTURE_ARTIFACT_DUPLICATE",
                 lambda: state["artifacts"].append(copy.deepcopy(state["metadata"])))
        rejected("corrupt ZIP", "CLOUD_FIXTURE_ARTIFACT_ZIP_INVALID",
                 lambda: (state.update({"archive": b"not-a-zip"}),
                          state["metadata"].update({"size_in_bytes": 9,
                              "digest": "sha256:" + hashlib.sha256(b"not-a-zip").hexdigest()}),
                          state["artifacts"][0].update({"size_in_bytes": 9,
                              "digest": state["metadata"]["digest"]})))
        rejected("fixture status", "CLOUD_FIXTURE_JSON_STATUS_NOT_PASS",
                 lambda: repack({**fixture, "status": "FAIL"}))
        rejected("GUI false claim", "CLOUD_FIXTURE_JSON_FALSE_GUI_CLAIM",
                 lambda: repack({**fixture, "physical_gui_verified": True}))
        missing = [item for item in fixture["results"]
                   if item["case"] != sorted(REQUIRED_CASES)[0]]
        rejected("required button/LOST case", "CLOUD_FIXTURE_REQUIRED_CASE_MISSING",
                 lambda: repack({**fixture, "results": missing}))
        rejected("synthetic coverage floor", "CLOUD_FIXTURE_RESULT_COUNT_BELOW_MINIMUM:PASS_SYNTHETIC",
                 lambda: repack({**fixture, "results": [item for item in fixture["results"] if item["case"] != "self-test synthetic 000"]}))
        rejected("mutation rejection coverage floor", "CLOUD_FIXTURE_RESULT_COUNT_BELOW_MINIMUM:PASS_REJECTED",
                 lambda: repack({**fixture, "results": [item for item in fixture["results"] if item["case"] != "self-test rejected 000"]}))
        rejected("static contract coverage floor", "CLOUD_FIXTURE_RESULT_COUNT_BELOW_MINIMUM:PASS_STATIC_ONLY",
                 lambda: repack({**fixture, "results": [item for item in fixture["results"] if item["case"] != "self-test filler 000"]}))
        rejected("source hash", "CLOUD_FIXTURE_SOURCE_HASH_MISMATCH",
                 lambda: repack({**fixture, "fixture_source_sha256": "0" * 64}))
        rejected("artifact verifier source hash mismatch",
                 "CLOUD_FIXTURE_SOURCE_HASH_MISMATCH:artifact_verifier_source_sha256",
                 lambda: repack({**fixture, "artifact_verifier_source_sha256": "0" * 64}))
        rejected("missing artifact verifier source hash",
                 "CLOUD_FIXTURE_SOURCE_HASH_INVALID:artifact_verifier_source_sha256",
                 lambda: repack({key: value for key, value in fixture.items()
                                 if key != "artifact_verifier_source_sha256"}))
        rejected("unsafe ZIP member", "CLOUD_FIXTURE_ARTIFACT_MEMBER_MISMATCH",
                 lambda: (state.update({"archive": make_zip(fixture, "../cloud-provenance-fixture.json")}),
                          state["metadata"].update({"size_in_bytes": len(state["archive"]),
                              "digest": "sha256:" + hashlib.sha256(state["archive"]).hexdigest()}),
                          state["artifacts"][0].update({"size_in_bytes": state["metadata"]["size_in_bytes"],
                              "digest": state["metadata"]["digest"]})))
    print(f"CLOUD_FIXTURE_ARTIFACT_VERIFIER_SELF_TEST_PASS:{tests}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--expected-run-id")
    parser.add_argument("--expected-repository-id")
    parser.add_argument("--expected-workflow-head")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.self_test:
        return self_test()

    result = {
        "schema": "signal-sprint-cloud-fixture-artifact-verification-v1",
        "status": "FAIL_CLOUD_FIXTURE_ARTIFACT_VERIFICATION",
        "independent_build_verified": False, "physical_gui_verified": False,
        "gdk_package_verified": False, "msix_status": "NOT_BUILT",
        "product_acceptance": False,
    }
    try:
        require(args.expected_run_id is not None, "CLOUD_FIXTURE_EXPECTED_RUN_ID_MISSING")
        require(args.expected_repository_id is not None, "CLOUD_FIXTURE_EXPECTED_REPOSITORY_ID_MISSING")
        require(args.expected_workflow_head is not None, "CLOUD_FIXTURE_EXPECTED_HEAD_MISSING")
        require(args.output is not None, "CLOUD_FIXTURE_OUTPUT_PATH_MISSING")
        result = verify(args.expected_run_id, int(args.expected_repository_id),
                        args.expected_workflow_head, os.environ.get("GITHUB_TOKEN", ""))
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    success = result.get("status") == "PASS_CLOUD_FIXTURE_ARTIFACT_VERIFIED"
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write("verified=" + ("true" if success else "false") + "\n")
            if success:
                handle.write("artifact_id=" + str(result["artifact_id"]) + "\n")
                handle.write("artifact_zip_sha256=" + result["artifact_zip_sha256"] + "\n")
                handle.write("artifact_zip_size_bytes=" + str(result["artifact_zip_size_bytes"]) + "\n")
    print(result.get("status", "FAIL_CLOUD_FIXTURE_ARTIFACT_VERIFICATION"))
    if not success:
        print(result.get("error", "CLOUD_FIXTURE_ARTIFACT_VERIFICATION_FAILED"), file=sys.stderr)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
