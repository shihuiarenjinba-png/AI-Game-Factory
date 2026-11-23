"""Cloud-only negative/positive provenance contract fixture; never certifies a real EXE or GUI."""
import hashlib
import os
import json
import pathlib
import re
import sys
import traceback
import zipfile
from urllib.parse import urlsplit

REPO = "shihuiarenjinba-png/AI-Game-Factory"
SOURCE = "1a349faa41663c417c40710140a4d50c79b62b78"
PR30_SOURCE = "a377043d3c9ab0c71d9a100cdb841dd7000313b9"
HEAD = "9ccd7ff4389b3ca0e45c8407d7369a00f4302cf2"
BUTTONS = {
    "EN": ["Start / Retry (R)", "Undo (U)", "Save (Ctrl+S)", "Load (L)", "日本語 (J)"],
    "JP": ["開始 / 再挑戦 (R)", "1手戻す (U)", "保存 (Ctrl+S)", "読込 (L)", "English (J)"],
}
LOST = {"EN": "LOST", "JP": "失敗"}

def validate(receipt, exe, expected_sha, expected_source):
    digest = hashlib.sha256(exe).hexdigest()
    assert re.fullmatch(r"[a-f0-9]{64}", expected_sha), "expected SHA format"
    assert digest == expected_sha, "EXE_SHA_MISMATCH"
    assert isinstance(receipt.get("exe_sha256"), str) and re.fullmatch(r"[a-fA-F0-9]{64}", receipt["exe_sha256"]), "RECEIPT_SHA_INVALID"
    assert receipt["exe_sha256"].lower() == digest, "RECEIPT_SHA_MISMATCH"
    assert isinstance(receipt.get("source_commit"), str) and re.fullmatch(r"[a-f0-9]{40}", receipt["source_commit"]), "RECEIPT_SOURCE_INVALID"
    assert receipt["source_commit"] == expected_source, "SOURCE_MISMATCH"
    assert isinstance(receipt.get("build_run_url"), str) and receipt["build_run_url"], "BUILD_RUN_URL_INVALID"
    url = urlsplit(receipt["build_run_url"])
    assert (url.scheme, url.hostname, url.port, url.username, url.password) == ("https", "github.com", None, None, None), "UNTRUSTED_URL"
    assert not url.query and not url.fragment, "URL_EXTRAS"
    assert re.fullmatch(rf"/{REPO}/actions/runs/[1-9][0-9]*", url.path), "RUN_PATH"
    return digest

def negative(label, fn):
    try:
        fn()
    except (AssertionError, ValueError, KeyError, OSError, RuntimeError, EOFError, zipfile.BadZipFile):
        return {"case": label, "result": "PASS_REJECTED"}
    raise AssertionError("NEGATIVE_ACCEPTED:" + label)

def assert_gate_contract(gate):
    match = re.search(r"\$expected\s*=\s*@\{\s*EN\s*=\s*@\((.*?)\)\s*JP\s*=\s*@\((.*?)\)\s*\}", gate, re.S)
    assert match is not None, "UIA_EXPECTED_BUTTON_MAP_MISSING"
    for language, group in (("EN", 1), ("JP", 2)):
        actual = re.findall(r"'([^']*)'", match.group(group))
        assert actual == BUTTONS[language], "UIA_BUTTON_SET_OR_ORDER_DRIFT:" + language
        assert len(actual) == len(set(actual)) == 5, "UIA_BUTTON_DUPLICATE_OR_COUNT:" + language
        assert LOST[language] in gate, "UIA_LOST_LABEL_MISSING:" + language
    for token in (
        "LOAD_UIA_CASE_NOT_UNIQUE",
        "LOST_UIA_NOT_OBSERVED",
        "START_UIA_CASE_NOT_UNIQUE",
        "START_LOST_PRECONDITION_NOT_OBSERVED",
        "START_LOST_TO_PLAYING_TRANSITION_NOT_OBSERVED",
        "ControlType.Text:PLAYING",
        "ControlType.Text:プレイ中",
    ):
        assert token in gate, "UIA_RUNTIME_LOST_TRANSITION_ASSERTION_MISSING:" + token


def validate_uia_receipt(receipt, expected_exe_sha, expected_source):
    """Validate the exact bilingual UIA receipt shape; synthetic fixtures never attest a GUI."""
    assert isinstance(receipt, dict), "UIA_RECEIPT_NOT_OBJECT"
    assert receipt.get("status") == "PASS", "UIA_RECEIPT_STATUS_NOT_PASS"
    assert receipt.get("source_head") == expected_source, "UIA_SOURCE_LABEL_MISMATCH"
    actual_sha = receipt.get("executable_sha256")
    assert isinstance(actual_sha, str) and re.fullmatch(r"[a-fA-F0-9]{64}", actual_sha), "UIA_EXE_SHA_INVALID"
    assert isinstance(expected_exe_sha, str) and re.fullmatch(r"[a-fA-F0-9]{64}", expected_exe_sha), "UIA_EXPECTED_EXE_SHA_INVALID"
    assert actual_sha.lower() == expected_exe_sha.lower(), "UIA_EXE_SHA_NOT_PREFLIGHT_SHA"
    evidence = receipt.get("evidence")
    assert isinstance(evidence, list) and len(evidence) == 10, "UIA_NOT_PASS_OR_INCOMPLETE"
    for language in ("EN", "JP"):
        cases = [item for item in evidence if isinstance(item, dict) and item.get("language") == language]
        assert len(cases) == 5, "UIA_LANGUAGE_COVERAGE_OR_SEMANTIC_FAILURE:" + language
        names = [item.get("name") for item in cases]
        assert all(isinstance(name, str) for name in names), "UIA_BUTTON_NAME_INVALID:" + language
        assert len(names) == len(set(names)) == 5 and sorted(names) == sorted(BUTTONS[language]), "UIA_BUTTON_EXACT_SET_OR_DUPLICATE:" + language
        by_name = {item["name"]: item for item in cases}
        for item in cases:
            assert item.get("control_type") == "ControlType.Button", "UIA_CONTROL_TYPE_MISMATCH:" + language
            assert all(item.get(key) is True for key in ("invoke_pattern", "focus", "invoked", "side_effect_verified")), "UIA_ACTION_SEMANTIC_STATE_NOT_OBSERVABLE:" + language
            assert isinstance(item.get("uia_before"), list) and isinstance(item.get("uia_after"), list), "UIA_STATE_NODES_INVALID:" + language
        lost_token = "ControlType.Text:LOST" if language == "EN" else "ControlType.Text:失敗"
        playing_token = "ControlType.Text:PLAYING" if language == "EN" else "ControlType.Text:プレイ中"
        load_name = "Load (L)" if language == "EN" else "読込 (L)"
        load_case = by_name[load_name]
        assert isinstance(load_case.get("lost_uia_nodes"), list) and lost_token in load_case["lost_uia_nodes"], "UIA_LOAD_LOST_STATE_NOT_OBSERVED:" + language
        assert lost_token in load_case["uia_after"], "UIA_LOAD_LOST_STATE_NOT_IN_POST_ACTION_TREE:" + language
        start_name = "Start / Retry (R)" if language == "EN" else "開始 / 再挑戦 (R)"
        start_case = by_name[start_name]
        assert lost_token in start_case["uia_before"], "UIA_START_LOST_PRECONDITION_NOT_OBSERVED:" + language
        assert playing_token in start_case["uia_after"] and lost_token not in start_case["uia_after"], "UIA_START_LOST_TO_PLAYING_TRANSITION_NOT_OBSERVED:" + language
        toggle_name = "日本語 (J)" if language == "EN" else "English (J)"
        expected_title = "Signal Sprint | JP" if language == "EN" else "Signal Sprint | EN"
        assert by_name[toggle_name].get("title_after") == expected_title, "UIA_LANGUAGE_TOGGLE_NOT_OBSERVED:" + language
        undo_name = "Undo (U)" if language == "EN" else "1手戻す (U)"
        undo_text = "ControlType.Text:No move to undo" if language == "EN" else "ControlType.Text:戻せる手がありません"
        assert undo_text in by_name[undo_name]["uia_after"], "UIA_UNDO_SEMANTIC_STATE_NOT_OBSERVED:" + language
        save_name = "Save (Ctrl+S)" if language == "EN" else "保存 (Ctrl+S)"
        save_text = "ControlType.Text:Saved on this computer" if language == "EN" else "ControlType.Text:このPCに保存しました"
        assert save_text in by_name[save_name]["uia_after"], "UIA_SAVE_SEMANTIC_STATE_NOT_OBSERVED:" + language
    return True


def validate_independent_build_binding(build, preflight):
    """Bind independent build receipt to exact UIA head, run, artifact, source and measured EXE."""
    assert isinstance(build, dict) and isinstance(preflight, dict), "INDEPENDENT_BUILD_BINDING_NOT_OBJECT"
    assert build.get("status") == "PASS_INDEPENDENT_BUILD_ONLY", "INDEPENDENT_BUILD_NOT_VERIFIED"
    assert build.get("independent_build_verified") is True, "INDEPENDENT_BUILD_NOT_VERIFIED"
    assert build.get("completed_run_required") is True, "INDEPENDENT_BUILD_RUN_NOT_COMPLETED_ATTESTED"
    assert build.get("run_status_at_verification") == "completed" and build.get("run_conclusion") == "success", "INDEPENDENT_BUILD_RUN_NOT_COMPLETED_SUCCESS"
    assert preflight.get("build_workflow_head_sha") == preflight.get("workflow_head"), "BUILD_WORKFLOW_HEAD_MISMATCH"
    assert build.get("workflow_head_sha") == preflight.get("build_workflow_head_sha"), "INDEPENDENT_BUILD_WORKFLOW_HEAD_MISMATCH"
    assert build.get("run_id") == preflight.get("build_run_id"), "INDEPENDENT_BUILD_RUN_ARTIFACT_BINDING_MISMATCH"
    assert build.get("artifact_id") == preflight.get("build_artifact_id"), "INDEPENDENT_BUILD_RUN_ARTIFACT_BINDING_MISMATCH"
    assert build.get("product_source") == preflight.get("product_source"), "INDEPENDENT_BUILD_UIA_BINDING_MISMATCH"
    assert build.get("pr30_source_commit") == preflight.get("pr30_source"), "INDEPENDENT_BUILD_PR30_BINDING_MISMATCH"
    build_sha = build.get("exe_sha256")
    preflight_sha = preflight.get("exe_sha256")
    assert isinstance(build_sha, str) and isinstance(preflight_sha, str) and build_sha.lower() == preflight_sha.lower(), "INDEPENDENT_BUILD_UIA_BINDING_MISMATCH"
    return True


def assert_independent_build_binding_fixture(results):
    """Exercise exact-head/run/artifact/source/SHA binding with synthetic receipts only."""
    import copy
    digest = hashlib.sha256(b"synthetic-independent-build-binding-only").hexdigest()
    workflow_head = "c" * 40
    run_id, artifact_id = 123456, 789012
    preflight = {
        "workflow_head": workflow_head,
        "build_workflow_head_sha": workflow_head,
        "product_source": SOURCE,
        "pr30_source": PR30_SOURCE,
        "exe_sha256": digest,
        "build_run_id": run_id,
        "build_artifact_id": artifact_id,
    }
    build = {
        "status": "PASS_INDEPENDENT_BUILD_ONLY",
        "independent_build_verified": True,
        "completed_run_required": True,
        "run_status_at_verification": "completed",
        "run_conclusion": "success",
        "workflow_head_sha": workflow_head,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "product_source": SOURCE,
        "pr30_source_commit": PR30_SOURCE,
        "exe_sha256": digest,
    }
    assert validate_independent_build_binding(build, preflight) is True
    results.append({"case": "synthetic independent build bound to exact UIA head, run, artifact, source and EXE SHA", "result": "PASS_SYNTHETIC"})
    mutations = []
    wrong_receipt_head = copy.deepcopy(preflight)
    wrong_receipt_head["build_workflow_head_sha"] = "d" * 40
    mutations.append(("receipt workflow head mismatch", build, wrong_receipt_head))
    wrong_head = copy.deepcopy(build)
    wrong_head["workflow_head_sha"] = "d" * 40
    mutations.append(("independent build workflow head mismatch", wrong_head, preflight))
    wrong_run = copy.deepcopy(build)
    wrong_run["run_id"] += 1
    mutations.append(("wrong build run ID", wrong_run, preflight))
    wrong_artifact = copy.deepcopy(build)
    wrong_artifact["artifact_id"] += 1
    mutations.append(("wrong build artifact ID", wrong_artifact, preflight))
    wrong_source = copy.deepcopy(build)
    wrong_source["product_source"] = HEAD
    mutations.append(("wrong frozen product source", wrong_source, preflight))
    wrong_pr30 = copy.deepcopy(build)
    wrong_pr30["pr30_source_commit"] = SOURCE
    mutations.append(("wrong PR30 ancestry source", wrong_pr30, preflight))
    wrong_sha = copy.deepcopy(build)
    wrong_sha["exe_sha256"] = "0" * 64
    mutations.append(("wrong independently measured EXE SHA", wrong_sha, preflight))
    not_verified = copy.deepcopy(build)
    not_verified["independent_build_verified"] = False
    mutations.append(("independent build not verified", not_verified, preflight))
    in_progress = copy.deepcopy(build)
    in_progress["completed_run_required"] = False
    in_progress["run_status_at_verification"] = "in_progress"
    in_progress["run_conclusion"] = None
    mutations.append(("in-progress build run cannot bind physical UIA", in_progress, preflight))
    failed_run = copy.deepcopy(build)
    failed_run["run_conclusion"] = "failure"
    mutations.append(("failed completed build run cannot bind physical UIA", failed_run, preflight))
    failed_status = copy.deepcopy(build)
    failed_status["status"] = "FAIL"
    mutations.append(("independent build status not PASS", failed_status, preflight))
    for label, candidate, candidate_preflight in mutations:
        results.append(negative("synthetic build/UIA binding " + label,
                                lambda b=candidate, p=candidate_preflight: validate_independent_build_binding(b, p)))


def assert_uia_receipt_fixture(results):
    """Exercise bilingual receipt validation with synthetic data only."""
    import copy
    digest = hashlib.sha256(b"synthetic-uia-receipt-only").hexdigest()
    evidence = []
    for language in ("EN", "JP"):
        lost = "ControlType.Text:LOST" if language == "EN" else "ControlType.Text:失敗"
        playing = "ControlType.Text:PLAYING" if language == "EN" else "ControlType.Text:プレイ中"
        undo_text = "ControlType.Text:No move to undo" if language == "EN" else "ControlType.Text:戻せる手がありません"
        save_text = "ControlType.Text:Saved on this computer" if language == "EN" else "ControlType.Text:このPCに保存しました"
        for name in BUTTONS[language]:
            item = {
                "language": language, "name": name, "control_type": "ControlType.Button",
                "invoke_pattern": True, "focus": True, "invoked": True,
                "side_effect_verified": True, "title_after": "Signal Sprint | EN",
                "uia_before": ["ControlType.Text:MENU"], "uia_after": [],
                "lost_uia_nodes": [],
            }
            if name == ("Start / Retry (R)" if language == "EN" else "開始 / 再挑戦 (R)"):
                item["uia_before"] = [lost]
                item["uia_after"] = [playing]
            elif name == ("Undo (U)" if language == "EN" else "1手戻す (U)"):
                item["uia_after"] = [undo_text]
            elif name == ("Save (Ctrl+S)" if language == "EN" else "保存 (Ctrl+S)"):
                item["uia_after"] = [save_text]
            elif name == ("Load (L)" if language == "EN" else "読込 (L)"):
                item["uia_after"] = [lost]
                item["lost_uia_nodes"] = [lost]
            elif name == ("日本語 (J)" if language == "EN" else "English (J)"):
                item["title_after"] = "Signal Sprint | JP" if language == "EN" else "Signal Sprint | EN"
            evidence.append(item)
    valid = {
        "schema": "signal-sprint-dynamic-uia-v1",
        "source_head": SOURCE,
        "executable_sha256": digest,
        "evidence": evidence,
        "status": "PASS",
    }
    assert validate_uia_receipt(valid, digest, SOURCE) is True
    results.append({"case": "synthetic bilingual UIA receipt: exact 5 buttons, action semantics, Load LOST and Start transition", "result": "PASS_SYNTHETIC"})
    mutations = []
    wrong_sha = copy.deepcopy(valid)
    wrong_sha["executable_sha256"] = "0" * 64
    mutations.append(("wrong measured EXE SHA", wrong_sha, digest, SOURCE))
    wrong_source = copy.deepcopy(valid)
    wrong_source["source_head"] = HEAD
    mutations.append(("wrong product source label", wrong_source, digest, SOURCE))
    duplicate = copy.deepcopy(valid)
    duplicate["evidence"][4]["name"] = duplicate["evidence"][0]["name"]
    mutations.append(("duplicate EN button", duplicate, digest, SOURCE))
    missing = copy.deepcopy(valid)
    missing["evidence"].pop()
    mutations.append(("missing JP button evidence", missing, digest, SOURCE))
    wrong_lost = copy.deepcopy(valid)
    wrong_lost["evidence"][8]["lost_uia_nodes"] = ["ControlType.Text:LOST"]
    wrong_lost["evidence"][8]["uia_after"] = ["ControlType.Text:LOST"]
    mutations.append(("wrong-language LOST token", wrong_lost, digest, SOURCE))
    unrelated_lost = copy.deepcopy(valid)
    en_load = next(item for item in unrelated_lost["evidence"] if item["language"] == "EN" and item["name"] == "Load (L)")
    en_undo = next(item for item in unrelated_lost["evidence"] if item["language"] == "EN" and item["name"] == "Undo (U)")
    en_load["lost_uia_nodes"] = []
    en_load["uia_after"] = []
    en_undo["lost_uia_nodes"] = ["ControlType.Text:LOST"]
    mutations.append(("LOST on unrelated button cannot satisfy Load", unrelated_lost, digest, SOURCE))
    no_start_lost = copy.deepcopy(valid)
    next(item for item in no_start_lost["evidence"] if item["language"] == "JP" and item["name"] == "開始 / 再挑戦 (R)")["uia_before"] = []
    mutations.append(("Start missing LOST precondition", no_start_lost, digest, SOURCE))
    no_playing = copy.deepcopy(valid)
    next(item for item in no_playing["evidence"] if item["language"] == "EN" and item["name"] == "Start / Retry (R)")["uia_after"] = []
    mutations.append(("Start missing PLAYING state", no_playing, digest, SOURCE))
    stale_lost = copy.deepcopy(valid)
    next(item for item in stale_lost["evidence"] if item["language"] == "EN" and item["name"] == "Start / Retry (R)")["uia_after"] = ["ControlType.Text:PLAYING", "ControlType.Text:LOST"]
    mutations.append(("Start still reports LOST after transition", stale_lost, digest, SOURCE))
    no_effect = copy.deepcopy(valid)
    next(item for item in no_effect["evidence"] if item["language"] == "JP" and item["name"] == "保存 (Ctrl+S)")["side_effect_verified"] = False
    mutations.append(("unverified save side effect", no_effect, digest, SOURCE))
    wrong_toggle = copy.deepcopy(valid)
    next(item for item in wrong_toggle["evidence"] if item["language"] == "JP" and item["name"] == "English (J)")["title_after"] = "Signal Sprint | JP"
    mutations.append(("wrong language toggle title", wrong_toggle, digest, SOURCE))
    wrong_type = copy.deepcopy(valid)
    wrong_type["evidence"][0]["control_type"] = "ControlType.Text"
    mutations.append(("non-button UIA element", wrong_type, digest, SOURCE))
    for label, candidate, expected_sha, expected_source in mutations:
        results.append(negative("synthetic UIA receipt " + label,
                                lambda c=candidate, s=expected_sha, p=expected_source: validate_uia_receipt(c, s, p)))


def assert_independent_verifier_with_mock_api(results):
    """Execute verifier against deterministic API/ZIP bytes, never a real GitHub build."""
    import importlib.util
    import io
    import tempfile
    import zipfile
    spec = importlib.util.spec_from_file_location("independent_build", "qa/signal_sprint_independent_build_verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    exe = b"synthetic-test-exe-only"
    sha = hashlib.sha256(exe).hexdigest()
    workflow_head = "b" * 40
    run_id, artifact_id = 123456, 789012
    member, provenance_member = "SignalSprint.exe", "build-provenance.json"
    url = f"https://github.com/{REPO}/actions/runs/{run_id}"
    receipt = {
        "source_commit": SOURCE, "pr30_source_commit": module.PR30_SOURCE,
        "workflow_head_sha": workflow_head,
        "exe_sha256": sha, "exe_size_bytes": len(exe),
        "build_run_url": url, "artifact_id": artifact_id,
        "artifact_exe_path": member, "artifact_provenance_path": provenance_member,
    }
    provenance = {
        "source_commit": SOURCE, "pr30_source_commit": module.PR30_SOURCE,
        "workflow_head_sha": workflow_head,
        "build_run_id": run_id, "exe_sha256": sha, "exe_size_bytes": len(exe),
        "artifact_kind": "EXE_QA_UNSIGNED", "msix_status": "NOT_BUILT",
        "gdk_package_verified": False, "physical_gui_verified": False,
    }
    run = {
        "id": run_id, "repository": {"full_name": REPO},
        "status": "in_progress", "conclusion": None,
        "head_sha": workflow_head, "path": module.BUILD_WORKFLOW_PATH,
        "event": "push",
    }
    jobs = {"jobs": [{"name": module.BUILD_JOB_NAME, "status": "completed", "conclusion": "success"}]}
    artifact = {
        "id": artifact_id, "name": module.BUILD_ARTIFACT_PREFIX + SOURCE,
        "expired": False,
        "workflow_run": {"id": run_id, "head_sha": workflow_head},
    }
    compare = {
        "status": "ahead", "ahead_by": 11, "behind_by": 0,
        "base_commit": {"sha": module.PR30_SOURCE},
        "commits": [{"sha": module.SOURCE}],
        "merge_base_commit": {"sha": module.PR30_SOURCE},
    }
    def archive_with_entries(entries):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as z:
            for name, data in entries:
                z.writestr(name, data)
        return output.getvalue()
    def archive_for(data, provenance_override=None):
        value = provenance if provenance_override is None else provenance_override
        return archive_with_entries([
            (member, data),
            (provenance_member, json.dumps(value).encode("utf-8")),
        ])
    archive = archive_for(exe)
    def make_fetch(run_obj, artifact_obj, zip_bytes, digest_override=None, include_digest=True, compare_obj=None):
        artifact_payload = dict(artifact_obj)
        if include_digest:
            artifact_payload["digest"] = (
                digest_override if digest_override is not None
                else "sha256:" + hashlib.sha256(zip_bytes).hexdigest()
            )
        else:
            artifact_payload.pop("digest", None)
        def fetch(url, token, accept="application/vnd.github+json"):
            if url == f"{module.API}/compare/{module.PR30_SOURCE}...{module.SOURCE}":
                return json.dumps(compare if compare_obj is None else compare_obj).encode()
            if url == f"{module.API}/actions/runs/{run_id}":
                return json.dumps(run_obj).encode()
            if url == f"{module.API}/actions/runs/{run_id}/jobs?per_page=100":
                return json.dumps(run_obj.get("_mock_jobs", jobs)).encode()
            if url == f"{module.API}/actions/artifacts/{artifact_id}":
                return json.dumps(artifact_payload).encode()
            if url == f"{module.API}/actions/artifacts/{artifact_id}/zip":
                return zip_bytes
            raise AssertionError("UNEXPECTED_API_URL")
        return fetch
    with tempfile.TemporaryDirectory() as temp:
        exe_path = pathlib.Path(temp) / "synthetic.exe"
        exe_path.write_bytes(exe)
        fetch = make_fetch(run, artifact, archive)
        good = module.verify(receipt, exe_path, "mock-token", fetch=fetch)
        assert good["status"] == "PASS_INDEPENDENT_BUILD_ONLY"
        assert good["pr30_source_commit"] == module.PR30_SOURCE and good["pr30_ancestry_verified"] is True
        assert good["exe_sha256"] == sha and good["physical_gui_verified"] is False
        assert good["artifact_zip_sha256"] == hashlib.sha256(archive).hexdigest()
        assert good["artifact_zip_size_bytes"] == len(archive)
        assert good["exe_size_bytes"] == len(exe)
        assert good["artifact_exe_size_bytes"] == len(exe)
        assert good["build_provenance_verified"] is True
        assert good["build_job_name"] == module.BUILD_JOB_NAME
        assert good["run_status_at_verification"] == "in_progress"
        assert good["artifact_kind"] == "EXE_QA_UNSIGNED" and good["msix_status"] == "NOT_BUILT"
        assert good["gdk_package_verified"] is False
        results.append({"case": "mock API exact workflow, source receipt and unsigned EXE positive", "result": "PASS_SYNTHETIC"})
        results.append(negative("mock API receipt PR30 source mismatch", lambda: module.verify(
            {**receipt, "pr30_source_commit": SOURCE}, exe_path, "mock-token",
            fetch=make_fetch(run, artifact, archive))))
        results.append(negative("mock API PR30 compare diverged history", lambda: module.verify(
            receipt, exe_path, "mock-token",
            fetch=make_fetch(run, artifact, archive, compare_obj={**compare, "status": "diverged", "behind_by": 1}))))
        results.append(negative("mock API PR30 compare wrong merge base", lambda: module.verify(
            receipt, exe_path, "mock-token",
            fetch=make_fetch(run, artifact, archive, compare_obj={**compare, "merge_base_commit": {"sha": SOURCE}}))))
        results.append(negative("mock API PR30 compare wrong frozen source head", lambda: module.verify(
            receipt, exe_path, "mock-token",
            fetch=make_fetch(run, artifact, archive, compare_obj={**compare, "commits": [{"sha": HEAD}]}))))
        results.append(negative("mock API PR30 compare wrong base commit", lambda: module.verify(
            receipt, exe_path, "mock-token",
            fetch=make_fetch(run, artifact, archive, compare_obj={**compare, "base_commit": {"sha": SOURCE}}))))
        results.append(negative("mock API missing artifact digest", lambda: module.verify(
            receipt, exe_path, "mock-token",
            fetch=make_fetch(run, artifact, archive, include_digest=False))))
        results.append(negative("mock API malformed artifact digest", lambda: module.verify(
            receipt, exe_path, "mock-token",
            fetch=make_fetch(run, artifact, archive, digest_override="sha256:not-a-sha"))))
        results.append(negative("mock API artifact digest mismatch", lambda: module.verify(
            receipt, exe_path, "mock-token",
            fetch=make_fetch(run, artifact, archive, digest_override="sha256:" + "0" * 64))))
        from urllib.request import Request
        handler = module.SafeRedirectHandler()
        request = Request("https://api.github.com/repos/" + REPO + "/actions/artifacts/1/zip",
                          headers={"Authorization": "Bearer fixture-token",
                                   "Accept": "application/vnd.github+json",
                                   "X-GitHub-Api-Version": "2022-11-28"})
        cross_host = handler.redirect_request(
            request, None, 302, "Found", {},
            "https://artifact-storage.example/blob.zip?sig=fixture")
        assert cross_host.get_header("Authorization") is None
        assert cross_host.get_header("Accept") is None
        same_host = handler.redirect_request(
            request, None, 302, "Found", {},
            "https://api.github.com/repos/" + REPO + "/actions/artifacts/1/zip")
        assert same_host.get_header("Authorization") == "Bearer fixture-token"
        results.append({"case": "cross-origin artifact redirect strips GitHub bearer token", "result": "PASS_SYNTHETIC"})
        completed_good = module.verify(
            receipt, exe_path, "mock-token",
            fetch=make_fetch({**run, "status": "completed", "conclusion": "success"}, artifact, archive),
            require_completed_run=True,
            expected_run_id=str(run_id),
            expected_workflow_head=workflow_head)
        assert completed_good["status"] == "PASS_INDEPENDENT_BUILD_ONLY"
        assert completed_good["run_status_at_verification"] == "completed"
        assert completed_good["run_conclusion"] == "success"
        assert completed_good["completed_run_required"] is True
        results.append({"case": "strict UIA provenance accepts only completed successful exact-run/exact-head build", "result": "PASS_SYNTHETIC"})
        results.append(negative(
            "strict UIA provenance rejects wrong expected build run ID",
            lambda: module.verify(receipt, exe_path, "mock-token",
                fetch=make_fetch({**run, "status": "completed", "conclusion": "success"}, artifact, archive),
                require_completed_run=True, expected_run_id=str(run_id + 1),
                expected_workflow_head=workflow_head)))
        results.append(negative(
            "strict UIA provenance rejects wrong expected build workflow head",
            lambda: module.verify(receipt, exe_path, "mock-token",
                fetch=make_fetch({**run, "status": "completed", "conclusion": "success"}, artifact, archive),
                require_completed_run=True, expected_run_id=str(run_id),
                expected_workflow_head="d" * 40)))
        results.append(negative(
            "strict UIA provenance rejects malformed expected build workflow head",
            lambda: module.verify(receipt, exe_path, "mock-token",
                fetch=make_fetch({**run, "status": "completed", "conclusion": "success"}, artifact, archive),
                require_completed_run=True, expected_run_id=str(run_id),
                expected_workflow_head="not-a-sha")))
        results.append(negative(
            "strict UIA provenance rejects in-progress build workflow",
            lambda: module.verify(receipt, exe_path, "mock-token",
                fetch=make_fetch(run, artifact, archive), require_completed_run=True)))
        results.append(negative(
            "queued workflow cannot attest a completed Windows build job",
            lambda: module.verify(receipt, exe_path, "mock-token",
                fetch=make_fetch({**run, "status": "queued"}, artifact, archive))))
        mutations = [
            ("failed completed workflow run", receipt, {**run, "status": "completed", "conclusion": "failure"}, artifact, archive, exe),
            ("cancelled workflow run", receipt, {**run, "status": "cancelled"}, artifact, archive, exe),
            ("missing frozen source build job", receipt,
             {**run, "_mock_jobs": {"jobs": []}}, artifact, archive, exe),
            ("duplicate frozen source build jobs", receipt,
             {**run, "_mock_jobs": {"jobs": [jobs["jobs"][0], jobs["jobs"][0]]}}, artifact, archive, exe),
            ("failed frozen source build job", receipt,
             {**run, "_mock_jobs": {"jobs": [{"name": module.BUILD_JOB_NAME, "status": "completed", "conclusion": "failure"}]}}, artifact, archive, exe),
            ("wrong workflow head", receipt, {**run, "head_sha": "c" * 40}, artifact, archive, exe),
            ("historical Factory core CI is not EXE build proof", receipt,
             {**run, "path": ".github/workflows/factory-ci.yml", "event": "pull_request"}, artifact, archive, exe),
            ("pull request event is not approved build", receipt,
             {**run, "event": "pull_request"}, artifact, archive, exe),
            ("artifact belongs to other run", receipt, run,
             {**artifact, "workflow_run": {"id": run_id + 1, "head_sha": workflow_head}}, archive, exe),
            ("artifact workflow head mismatch", receipt, run,
             {**artifact, "workflow_run": {"id": run_id, "head_sha": "c" * 40}}, archive, exe),
            ("wrong artifact name", receipt, run,
             {**artifact, "name": "signal-sprint-msixvc"}, archive, exe),
            ("artifact provenance source mismatch", receipt, run, artifact,
             archive_for(exe, {**provenance, "source_commit": HEAD}), exe),
            ("artifact provenance workflow head mismatch", receipt, run, artifact,
             archive_for(exe, {**provenance, "workflow_head_sha": "c" * 40}), exe),
            ("artifact provenance run id mismatch", receipt, run, artifact,
             archive_for(exe, {**provenance, "build_run_id": run_id + 1}), exe),
            ("artifact provenance EXE SHA mismatch", receipt, run, artifact,
             archive_for(exe, {**provenance, "exe_sha256": "0" * 64}), exe),
            ("artifact provenance EXE size mismatch", receipt, run, artifact,
             archive_for(exe, {**provenance, "exe_size_bytes": len(exe) + 1}), exe),
            ("build receipt EXE size mismatch", {**receipt, "exe_size_bytes": len(exe) + 1}, run, artifact, archive, exe),
            ("MSIX artifact kind rejected", receipt, run, artifact,
             archive_for(exe, {**provenance, "artifact_kind": "MSIX"}), exe),
            ("MSIX build claim rejected", receipt, run, artifact,
             archive_for(exe, {**provenance, "msix_status": "BUILT"}), exe),
            ("GDK package claim rejected", receipt, run, artifact,
             archive_for(exe, {**provenance, "gdk_package_verified": True}), exe),
            ("physical GUI claim rejected", receipt, run, artifact,
             archive_for(exe, {**provenance, "physical_gui_verified": True}), exe),
            ("tampered artifact EXE", receipt, run, artifact, archive_for(exe + b"tampered"), exe),
            ("tampered local EXE", receipt, run, artifact, archive, exe + b"tampered"),
            ("expired artifact", receipt, run, {**artifact, "expired": True}, archive, exe),
            ("wrong run repository", receipt, {**run, "repository": {"full_name": "other/repo"}}, artifact, archive, exe),
            ("wrong artifact id", {**receipt, "artifact_id": artifact_id + 1}, run, artifact, archive, exe),
            ("missing artifact path", {**receipt, "artifact_exe_path": "missing.exe"}, run, artifact, archive, exe),
            ("missing artifact provenance path", {**receipt, "artifact_provenance_path": "missing.json"}, run, artifact, archive, exe),
            ("unsafe artifact traversal path", {**receipt, "artifact_exe_path": "../SignalSprint.exe"}, run, artifact, archive, exe),
            ("unsafe provenance traversal path", {**receipt, "artifact_provenance_path": "../build-provenance.json"}, run, artifact, archive, exe),
            ("absolute artifact path", {**receipt, "artifact_exe_path": "/build/SignalSprint.exe"}, run, artifact, archive, exe),
            ("Windows artifact path", {**receipt, "artifact_exe_path": "build\\\\SignalSprint.exe"}, run, artifact, archive, exe),
            ("duplicate artifact member", receipt, run, artifact,
             archive_with_entries([(member, exe), (member, exe)]), exe),
            ("corrupt artifact ZIP", receipt, run, artifact, b"not-a-valid-zip", exe),
        ]
        for label, candidate, run_obj, art_obj, zipped, local in mutations:
            exe_path.write_bytes(local)
            results.append(negative("mock API " + label, lambda c=candidate, r=run_obj, a=art_obj, z=zipped:
                module.verify(c, exe_path, "mock-token", fetch=make_fetch(r, a, z))))
        exe_path.write_bytes(exe)
        for attribute, limit, label in (
            ("MAX_ARTIFACT_ZIP_BYTES", len(archive) - 1, "artifact ZIP size limit"),
            ("MAX_ARTIFACT_UNCOMPRESSED_BYTES", len(exe) - 1, "artifact uncompressed size limit"),
            ("MAX_EXE_BYTES", len(exe) - 1, "EXE size limit"),
        ):
            original = getattr(module, attribute)
            setattr(module, attribute, limit)
            try:
                results.append(negative("mock API " + label, lambda: module.verify(
                    receipt, exe_path, "mock-token", fetch=make_fetch(run, artifact, archive))))
            finally:
                setattr(module, attribute, original)

def run_checks(results):
    exe = b"synthetic-fixture-only-not-a-shipping-executable"
    digest = hashlib.sha256(exe).hexdigest()
    receipt = {"source_commit": SOURCE, "exe_sha256": digest, "build_run_url": f"https://github.com/{REPO}/actions/runs/123456"}
    results.append({"case": "matching synthetic receipt", "result": "PASS_SYNTHETIC", "sha256": validate(receipt, exe, digest, SOURCE)})
    for name, update in [
        ("tampered exe", {"exe": exe + b"x"}),
        ("wrong expected SHA", {"expected_sha": "0" * 64}),
        ("wrong receipt SHA", {"receipt": {**receipt, "exe_sha256": "0" * 64}}),
        ("short receipt SHA", {"receipt": {**receipt, "exe_sha256": "abc"}}),
        ("nonstring receipt SHA", {"receipt": {**receipt, "exe_sha256": None}}),
        ("nonstring source", {"receipt": {**receipt, "source_commit": None}}),
        ("nonstring build URL", {"receipt": {**receipt, "build_run_url": None}}),
        ("wrong source", {"receipt": {**receipt, "source_commit": HEAD}}),
        ("spoofed host", {"receipt": {**receipt, "build_run_url": f"https://github.com.evil.test/{REPO}/actions/runs/123456"}}),
        ("wrong repository", {"receipt": {**receipt, "build_run_url": "https://github.com/other/repo/actions/runs/123456"}}),
        ("query suffix", {"receipt": {**receipt, "build_run_url": receipt["build_run_url"] + "?x=1"}}),
        ("invalid run id", {"receipt": {**receipt, "build_run_url": f"https://github.com/{REPO}/actions/runs/0"}}),
        ("missing receipt sha", {"receipt": {"source_commit": SOURCE, "build_run_url": receipt["build_run_url"]}}),
        ("http scheme", {"receipt": {**receipt, "build_run_url": f"http://github.com/{REPO}/actions/runs/123456"}}),
        ("userinfo spoof", {"receipt": {**receipt, "build_run_url": f"https://attacker@github.com/{REPO}/actions/runs/123456"}}),
        ("fragment suffix", {"receipt": {**receipt, "build_run_url": receipt["build_run_url"] + "#artifact"}}),
        ("malformed expected sha", {"expected_sha": "not-a-sha"}),
        ("missing build run url", {"receipt": {"source_commit": SOURCE, "exe_sha256": digest}}),
        ("empty build run url", {"receipt": {**receipt, "build_run_url": ""}}),
        ("missing source commit", {"receipt": {"exe_sha256": digest, "build_run_url": receipt["build_run_url"]}}),
        ("trailing slash", {"receipt": {**receipt, "build_run_url": receipt["build_run_url"] + "/"}}),
        ("explicit alternate port", {"receipt": {**receipt, "build_run_url": f"https://github.com:444/{REPO}/actions/runs/123456"}}),
        ("wrong actions route", {"receipt": {**receipt, "build_run_url": f"https://github.com/{REPO}/actions/workflows/123456"}}),
        ("wrong product source", {"expected_source": HEAD}),
        ("uppercase expected hash", {"expected_sha": digest.upper()}),
        ("wrong receipt source length", {"receipt": {**receipt, "source_commit": SOURCE[:-1]}}),
        ("encoded repository path", {"receipt": {**receipt, "build_run_url": f"https://github.com/{REPO.replace('/', '%2F')}/actions/runs/123456"}}),
        ("URL path traversal", {"receipt": {**receipt, "build_run_url": f"https://github.com/{REPO}/actions/runs/../123456"}}),
    ]:
        kwargs = {"receipt": receipt, "exe": exe, "expected_sha": digest, "expected_source": SOURCE}
        kwargs.update(update)
        results.append(negative(name, lambda kw=kwargs: validate(**kw)))
    assert_independent_verifier_with_mock_api(results)
    assert_uia_receipt_fixture(results)
    assert_independent_build_binding_fixture(results)
    # The proof workflow builds only an unsigned pre-GDK EXE from the immutable product source.
    build_workflow = pathlib.Path(".github/workflows/signal-sprint-cloud-build-proof.yml").read_text(encoding="utf-8")
    for token in (
        "windows-frozen-source-exe:",
        "ref: 1a349faa41663c417c40710140a4d50c79b62b78",
        "$pr30 = 'a377043d3c9ab0c71d9a100cdb841dd7000313b9'",
        "git -C frozen-source merge-base --is-ancestor $pr30 $actual",
        "PR30_SOURCE_ANCESTRY_MISMATCH",
        "PR30_SOURCE_SHA: ${{ steps.source.outputs.pr30_source_sha }}",
        "pr30_source_commit = $env:PR30_SOURCE_SHA",
        "Pillow==11.3.0",
        "pyinstaller==6.16.0",
        "& $venvPython -m PyInstaller",
        "--noconfirm --clean --onefile --windowed",
        "artifact_kind = 'EXE_QA_UNSIGNED'",
        "msix_status = 'NOT_BUILT'",
        "gdk_package_verified = $false",
        "signal-sprint-frozen-source-exe-",
    ):
        assert token in build_workflow, "FROZEN_SOURCE_EXE_BUILDER_CONTRACT_MISSING:" + token
    build_verify_command = next((line.strip() for line in build_workflow.splitlines()
                                 if "signal_sprint_independent_build_verify.py --receipt" in line), "")
    assert build_verify_command and "--require-completed-run" not in build_verify_command, "BUILD_SELF_VERIFY_MUST_ALLOW_IN_PROGRESS_PARENT"
    results.append({"case": "build workflow self-verification permits its own in-progress parent run", "result": "PASS_STATIC_ONLY"})
    verifier_source = pathlib.Path("qa/signal_sprint_independent_build_verify.py").read_text(encoding="utf-8")
    for token in ("validate_run_status", "RUN_NOT_COMPLETED_SUCCESS", "completed_run_required",
                  'PR30_SOURCE = "a377043d3c9ab0c71d9a100cdb841dd7000313b9"', "PR30_SOURCE_RECEIPT_MISMATCH",
                  "PR30_SOURCE_NOT_ANCESTOR", "PR30_SOURCE_ANCESTRY_MISMATCH",
                  "PR30_SOURCE_COMPARE_HEAD_MISMATCH", "ARTIFACT_PROVENANCE_PR30_SOURCE_MISMATCH",
                  "pr30_ancestry_verified"):
        assert token in verifier_source, "INDEPENDENT_PR30_ANCESTRY_GUARD_MISSING:" + token
    results.append({"case": "independent verifier proves fixed PR30 source is ancestor of frozen build source", "result": "PASS_STATIC_ONLY"})
    results.append({"case": "frozen source unsigned EXE builder never claims GDK/MSIX package", "result": "PASS_STATIC_ONLY"})
    # Keep the cloud fixture aligned with the actual Windows preflight contract.
    workflow = pathlib.Path(".github/workflows/signal-sprint-windows-uia-evidence.yml").read_text(encoding="utf-8")
    completed_job = workflow.split("  completed-build-attestation:", 1)[1].split("  bilingual-uia:", 1)[0]
    windows_job = workflow.split("  bilingual-uia:", 1)[1]
    uia_verify_command = next((line.strip() for line in windows_job.splitlines()
                               if "signal_sprint_independent_build_verify.py --receipt" in line), "")
    def assert_uia_completed_build_contract(command):
        assert "--require-completed-run" in command, "PHYSICAL_UIA_MUST_REQUIRE_COMPLETED_BUILD_RUN"
    assert_uia_completed_build_contract(uia_verify_command)
    results.append({"case": "physical UIA requires completed successful independent build run", "result": "PASS_STATIC_ONLY"})
    completed_job_contract = {
        "hosted cloud runner": "runs-on: ubuntu-latest",
        "cloud push path": "github.event_name == 'push'",
        "independent dependency": "needs: [cloud-provenance-fixture]",
        "exact-head workflow run lookup": "head_sha",
        "pinned build workflow ID": "/actions/workflows/427222317/runs",
        "build run path validation": ".github/workflows/signal-sprint-cloud-build-proof.yml",
        "build run completion check": 'latest_status == "completed"',
        "completed build receipt artifact": "signal-sprint-independent-cloud-build-proof",
        "exact build EXE artifact ID": "artifact-ids: ${{ steps.receipt.outputs.artifact_id }}",
        "same run artifact download": "run-id: ${{ steps.discover.outputs.build_run_id }}",
        "receipt run ID match": "BUILD_RUN_ID_RECEIPT_MISMATCH",
        "receipt exact workflow head": "BUILD_WORKFLOW_HEAD_NOT_EXACT_UIA_HEAD",
        "strict completed-run verifier": "--require-completed-run",
        "strict expected run ID": "--expected-run-id",
        "strict expected workflow head": "--expected-workflow-head",
        "completed attestation artifact": "signal-sprint-completed-build-attestation",
        "HOLD receipt on no completed run": "HOLD_BUILD_RUN_NOT_COMPLETED",
    }
    for label, token in completed_job_contract.items():
        assert token in completed_job, "COMPLETED_BUILD_ATTESTATION_CONTRACT_MISSING:" + label
        results.append({"case": "completed build attestation contract " + label, "result": "PASS_STATIC_ONLY"})
    assert "self-hosted" not in completed_job and "signal-sprint-gdk" not in completed_job, "CLOUD_ATTESTATION_MUST_NOT_ALLOCATE_PHYSICAL_GDK_RUNNER"
    def assert_completed_job_contract(candidate):
        for label, token in completed_job_contract.items():
            assert token in candidate, "COMPLETED_BUILD_ATTESTATION_CONTRACT_MISSING:" + label
        assert "self-hosted" not in candidate and "signal-sprint-gdk" not in candidate, "CLOUD_ATTESTATION_MUST_NOT_ALLOCATE_PHYSICAL_GDK_RUNNER"
    for label, token in completed_job_contract.items():
        changed = completed_job.replace(token, "REMOVED_BY_MUTATION_TEST")
        assert changed != completed_job, "COMPLETED_ATTESTATION_MUTATION_NO_EFFECT:" + label
        results.append(negative("completed build attestation mutation reject " + label,
                                lambda candidate=changed: assert_completed_job_contract(candidate)))
    results.append(negative(
        "completed build attestation cannot use the physical GDK runner",
        lambda: assert_completed_job_contract(completed_job + "\n    runs-on: [self-hosted, Windows, interactive-desktop, signal-sprint-gdk]")))
    results.append(negative(
        "physical UIA strict completion flag mutation reject",
        lambda: assert_uia_completed_build_contract(uia_verify_command.replace("--require-completed-run", ""))))
    assert "$productSource = '" + SOURCE + "'" in workflow, "WORKFLOW_PRODUCT_SOURCE_DRIFT"
    assert "$pr30 = '" + PR30_SOURCE + "'" in workflow and "PR30_SOURCE_ANCESTRY_MISMATCH" in workflow, "UIA_WORKFLOW_PR30_ANCESTRY_GUARD_MISSING"
    assert SOURCE != HEAD, "PRODUCT_SOURCE_REFERENCE_ALIGNMENT_CHANGED_REVIEW_REQUIRED"
    assert "signal-sprint-cloud-provenance-fixture" in workflow, "CLOUD_ARTIFACT_UPLOAD_MISSING"
    assert "signal-sprint-uia-receipt" in workflow, "WINDOWS_ARTIFACT_UPLOAD_MISSING"
    # Assert evidence upload semantics, not merely artifact-name strings.
    cloud_job = workflow.split("  cloud-provenance-fixture:", 1)[1].split("  bilingual-uia:", 1)[0]
    windows_job = workflow.split("  bilingual-uia:", 1)[1]
    # The self-hosted GDK desktop must not be allocated for a known frozen-source
    # revision HOLD. A hosted preflight exports the decision; only an explicit
    # exact-head dispatch with revision inclusion may schedule physical UIA.
    runner_gate_tokens = {
        "preflight step id": "id: preflight",
        "revision output": "revision_included: ${{ steps.preflight.outputs.revision_included }}",
        "preflight status output": "preflight_status: ${{ steps.preflight.outputs.preflight_status }}",
        "output file binding": "GITHUB_OUTPUT",
        "hosted dependency": "needs: [cloud-provenance-fixture, cloud-revision-hold, completed-build-attestation]",
        "fixture result gate": "needs.cloud-provenance-fixture.result == 'success'",
        "exact dispatch head": "inputs.expected_head == github.sha",
        "explicit physical UIA request": "inputs.run_physical_uia == true",
        "completed build attestation result": "needs.completed-build-attestation.outputs.attestation_status == 'PASS_INDEPENDENT_BUILD_ONLY'",
        "physical EXE path required": "inputs.exe_path != ''",
        "physical EXE SHA required": "inputs.exe_sha256 != ''",
        "physical build receipt required": "inputs.build_receipt_path != ''",
        "revision inclusion gate": "needs.cloud-revision-hold.outputs.revision_included == 'true'",
        "current QA branch gate": "github.ref == 'refs/heads/codex/signal-sprint-cloud-build-proof-20261123'",
        "expected hold remains observable": "EXPECTED_PRODUCT_HOLD:",
        "included revision path": "REVISION_INCLUDED:",
    }
    def assert_runner_gate_contract(candidate):
        revision_section = candidate.split("  cloud-revision-hold:", 1)[1].split("  bilingual-uia:", 1)[0]
        physical_header = candidate.split("  bilingual-uia:", 1)[1].split("    runs-on:", 1)[0]
        for label, token in runner_gate_tokens.items():
            section = physical_header if label in {
                "hosted dependency", "fixture result gate", "exact dispatch head", "explicit physical UIA request",
                "completed build attestation result", "physical EXE path required",
                "physical EXE SHA required", "physical build receipt required",
                "revision inclusion gate", "current QA branch gate"
            } else revision_section
            assert token in section, "PHYSICAL_UIA_RUNNER_GATE_MISSING:" + label
        assert "FIXTURE_EXPECTED_REVISION_MISMATCH_NO_LONGER_PRESENT_REVIEW_FREEZE" not in revision_section, "EXPECTED_HOLD_MUST_NOT_FAIL_CLOUD_JOB"
    assert_runner_gate_contract(workflow)
    # The dispatch SHA is untrusted user input: it must be passed via env, never interpolated into shell source.
    def assert_cloud_exact_head_contract(candidate):
        step = candidate.split("      - name: Assert exact-head cloud checkout", 1)[1].split("      - name:", 1)[0]
        env_block, run_block = step.split("        run: |", 1)
        assert "DISPATCH_EXPECTED_HEAD: ${{ inputs.expected_head }}" in env_block, "DISPATCH_HEAD_ENV_BINDING_MISSING"
        assert '[[ "$DISPATCH_EXPECTED_HEAD" =~ ^[a-f0-9]{40}$ ]]' in run_block, "DISPATCH_HEAD_FORMAT_NOT_VALIDATED"
        assert 'test "$DISPATCH_EXPECTED_HEAD" = "$EXPECTED_HEAD"' in run_block, "DISPATCH_HEAD_EXACT_MATCH_MISSING"
        assert '${{ inputs.expected_head }}' not in run_block, "UNTRUSTED_DISPATCH_HEAD_INTERPOLATED_IN_SHELL"
    assert_cloud_exact_head_contract(workflow)
    for token in (
        "DISPATCH_EXPECTED_HEAD: ${{ inputs.expected_head }}",
        '[[ "$DISPATCH_EXPECTED_HEAD" =~ ^[a-f0-9]{40}$ ]]',
        'test "$DISPATCH_EXPECTED_HEAD" = "$EXPECTED_HEAD"',
    ):
        changed = workflow.replace(token, "REMOVED_BY_MUTATION_TEST")
        assert changed != workflow, "EXACT_HEAD_MUTATION_NO_EFFECT:" + token
        results.append(negative("exact-head dispatch guard mutation reject " + token,
                                lambda candidate=changed: assert_cloud_exact_head_contract(candidate)))
    results.append({"case": "workflow dispatch expected-head input is env-bound and shell-injection safe", "result": "PASS_STATIC_ONLY"})
    for label, token in runner_gate_tokens.items():
        changed = workflow.replace(token, "REMOVED_BY_MUTATION_TEST")
        assert changed != workflow, "RUNNER_GATE_MUTATION_NO_EFFECT:" + label
        results.append(negative("physical UIA runner gate mutation reject " + label,
                                lambda candidate=changed: assert_runner_gate_contract(candidate)))
    results.append({"case": "physical UIA runner gated by hosted exact-head revision preflight", "result": "PASS_STATIC_ONLY"})
    assert "runs-on: ubuntu-latest" in cloud_job, "CLOUD_JOB_NOT_HOSTED"
    assert "python3 qa/signal_sprint_cloud_provenance_fixture.py" in cloud_job, "CLOUD_FIXTURE_NOT_EXECUTED"
    assert "if: always()" in cloud_job, "CLOUD_FAILURE_EVIDENCE_NOT_GUARANTEED"
    assert "if-no-files-found: error" in cloud_job, "CLOUD_MISSING_EVIDENCE_NOT_FATAL"
    assert "path: evidence/cloud-provenance-fixture.json" in cloud_job, "CLOUD_EVIDENCE_PATH_DRIFT"
    assert "self-hosted, Windows, interactive-desktop, signal-sprint-gdk" in windows_job, "GDK_RUNNER_CONTRACT_DRIFT"
    assert "qa/signal_sprint_uia_dynamic_gate.ps1" in windows_job, "WINDOWS_UIA_GATE_NOT_EXECUTED"
    assert "if: always()" in windows_job, "WINDOWS_FAILURE_EVIDENCE_NOT_GUARANTEED"
    # A green synthetic fixture must not hide removal of real Windows provenance guards.
    required_preflight = {
        "exact dispatch HEAD": "DISPATCH_HEAD_MISMATCH",
        "checkout HEAD": "CHECKOUT_HEAD_MISMATCH",
        "EXE file hash": "Get-FileHash -LiteralPath $env:EXE_PATH -Algorithm SHA256",
        "EXE expected hash": "EXE_SHA256_MISMATCH",
        "build receipt file": "BUILD_RECEIPT_MISSING",
        "receipt file SHA calculation": "Get-FileHash -LiteralPath $env:BUILD_RECEIPT_PATH -Algorithm SHA256",
        "receipt SHA evidence field": "build_receipt_sha256=$receiptFileSha",
        "build receipt source": "BUILD_SOURCE_MISMATCH",
        "build receipt EXE hash": "BUILD_RECEIPT_EXE_SHA_MISMATCH",
        "build receipt workflow head format": "BUILD_WORKFLOW_HEAD_SHA_INVALID",
        "build receipt exact workflow head": "BUILD_WORKFLOW_HEAD_MISMATCH",
        "build run ID parsed from trusted URL": "$buildRunId = [long]$buildRunMatch.Groups[1].Value",
        "build run ID validation": "BUILD_RUN_ID_INVALID",
        "build artifact ID validation": "BUILD_ARTIFACT_ID_INVALID",
        "preflight build run ID": "build_run_id=$buildRunId",
        "preflight build artifact ID": "build_artifact_id=$buildArtifactId",
        "preflight build workflow head": "build_workflow_head_sha=$receipt.workflow_head_sha",
        "trusted build run": "BUILD_RUN_URL_INVALID_OR_UNTRUSTED",
        "independent build disclaimer": "RECEIPT_MATCHED_NOT_INDEPENDENTLY_VERIFIED",
        "physical GUI disclaimer": "NOT_YET_TESTED",
    }
    for label, token in required_preflight.items():
        assert token in windows_job, "WINDOWS_PREFLIGHT_GUARD_MISSING:" + label
        results.append({"case": "Windows preflight guard " + label, "result": "PASS_STATIC_ONLY"})
    assert "github.event_name == 'workflow_dispatch'" in windows_job, "UIA_MUST_REQUIRE_DISPATCH"
    assert "if-no-files-found: warn" in windows_job, "WINDOWS_FAILURE_EVIDENCE_POLICY_DRIFT"
    # The Windows binding must reject incomplete, duplicated, or cross-language UIA evidence.
    # Static checks only: these do not certify a physical GUI run or an independent build.
    binding_guards = {
        "receipt status and total": "UIA_NOT_PASS_OR_INCOMPLETE",
        "source label binding": "UIA_SOURCE_LABEL_MISMATCH",
        "measured EXE hash binding": "UIA_EXE_SHA_NOT_PREFLIGHT_SHA",
        "per-language semantic side effects": "UIA_LANGUAGE_COVERAGE_OR_SEMANTIC_FAILURE",
        "exact button set and duplicate rejection": "UIA_BUTTON_EXACT_SET_OR_DUPLICATE",
        "localized LOST nodes": "UIA_LOCALIZED_LOST_NOT_OBSERVED",
        "EN localized LOST token": "ControlType.Text:LOST",
        "JP localized LOST token": "ControlType.Text:失敗",
        "per-language LOST token selection": "$lostToken = if ($lang -ceq 'EN')",
        "Load case LOST assertion": "UIA_LOAD_LOST_STATE_NOT_OBSERVED",
        "Start LOST precondition": "UIA_START_LOST_PRECONDITION_NOT_OBSERVED",
        "Start LOST-to-PLAYING transition": "UIA_START_LOST_TO_PLAYING_TRANSITION_NOT_OBSERVED",
        "localized English PLAYING state": "ControlType.Text:PLAYING",
        "localized Japanese PLAYING state": "ControlType.Text:プレイ中",
        "Load case selection": "$loadName = if ($lang -ceq 'EN')",
        "Start case selection": "$startName = if ($lang -ceq 'EN')",
        "independent build verified in UIA binding": "independent_build_verified=$true",
        "independent run and EXE binding": "INDEPENDENT_BUILD_UIA_BINDING_MISMATCH",
        "independent build workflow-head binding": "INDEPENDENT_BUILD_WORKFLOW_HEAD_MISMATCH",
        "independent build run/artifact binding": "INDEPENDENT_BUILD_RUN_ARTIFACT_BINDING_MISMATCH",
        "independent build PR30 binding": "INDEPENDENT_BUILD_PR30_BINDING_MISMATCH",
        "independent build workflow-head evidence field": "independent_build_workflow_head_sha=$build.workflow_head_sha",
        "independent build failure": "INDEPENDENT_BUILD_NOT_VERIFIED",
    }
    for label, token in binding_guards.items():
        assert token in windows_job, "WINDOWS_UIA_BINDING_GUARD_MISSING:" + label
        results.append({"case": "Windows UIA binding guard " + label, "result": "PASS_STATIC_ONLY"})
    # Mutation-test the Windows receipt-binding contract itself. A static green
    # fixture must fail when a critical receipt guard is removed from the workflow.
    def assert_binding_contract(candidate):
        for label, token in binding_guards.items():
            assert token in candidate, "WINDOWS_UIA_BINDING_GUARD_MISSING:" + label
    for label, token in binding_guards.items():
        changed = windows_job.replace(token, "REMOVED_BY_MUTATION_TEST")
        assert changed != windows_job, "BINDING_MUTATION_NO_EFFECT:" + label
        results.append(negative("Windows binding mutation reject " + label,
                                lambda candidate=changed: assert_binding_contract(candidate)))
    assert "signal-sprint-uia-hash-binding-v1" in windows_job, "UIA_BINDING_SCHEMA_MISSING"
    assert "path: evidence/" in windows_job, "UIA_BINDING_ARTIFACT_PATH_MISSING"
    assert "PASS_HASH_BOUND_INDEPENDENT_BUILD_AND_PHYSICAL_UIA" in windows_job, "UIA_INDEPENDENCE_BINDING_MISSING"
    assert "qa/signal_sprint_independent_build_verify.py" in windows_job, "INDEPENDENT_VERIFIER_NOT_EXECUTED"
    assert "actions: read" in workflow, "GITHUB_ACTIONS_READ_PERMISSION_MISSING"
    verifier = pathlib.Path("qa/signal_sprint_independent_build_verify.py").read_text(encoding="utf-8")
    for token in ("EXPECTED_BUILD_RUN_ID_INVALID", "EXPECTED_BUILD_RUN_ID_MISMATCH",
                  "EXPECTED_BUILD_WORKFLOW_HEAD_INVALID", "EXPECTED_BUILD_WORKFLOW_HEAD_MISMATCH",
                  "expected_run_id", "expected_workflow_head",
                  "BUILD_WORKFLOW_PATH_MISMATCH", "BUILD_WORKFLOW_EVENT_INVALID", "WORKFLOW_HEAD_SHA_INVALID", "WORKFLOW_HEAD_MISMATCH", "RUN_NOT_ACTIVE_OR_COMPLETE", "RUN_JOBS_INVALID", "FROZEN_SOURCE_BUILD_JOB_NOT_UNIQUE", "FROZEN_SOURCE_BUILD_JOB_NOT_SUCCESS", "BUILD_ARTIFACT_NAME_MISMATCH", "RUN_NOT_SUCCESS", "ARTIFACT_RUN_MISMATCH", "ARTIFACT_WORKFLOW_HEAD_MISMATCH", "ARTIFACT_EXE_SHA_MISMATCH", "ARTIFACT_PROVENANCE_PATH_INVALID", "ARTIFACT_PROVENANCE_MISSING_OR_DUPLICATE", "ARTIFACT_PROVENANCE_NOT_REGULAR_FILE", "ARTIFACT_PROVENANCE_TOO_LARGE", "ARTIFACT_PROVENANCE_SOURCE_MISMATCH", "ARTIFACT_PROVENANCE_WORKFLOW_HEAD_MISMATCH", "ARTIFACT_PROVENANCE_RUN_ID_MISMATCH", "ARTIFACT_PROVENANCE_EXE_SHA_MISMATCH", "ARTIFACT_PROVENANCE_EXE_SIZE_MISMATCH", "RECEIPT_EXE_SIZE_INVALID", "RECEIPT_EXE_SIZE_MISMATCH", "ARTIFACT_KIND_NOT_UNSIGNED_EXE", "MSIX_MUST_REMAIN_NOT_BUILT", "GDK_PACKAGE_MUST_NOT_BE_CLAIMED", "PHYSICAL_GUI_MUST_NOT_BE_CLAIMED", "ARTIFACT_ZIP_TOO_LARGE_OR_INVALID", "ARTIFACT_DIGEST_INVALID", "ARTIFACT_ARCHIVE_DIGEST_MISMATCH", "LOCAL_EXE_SIZE_MISMATCH", "artifact_zip_sha256", "url.endswith(\"/zip\")", "application/vnd.github+json", "SafeRedirectHandler", "redirected.remove_header(name)", "Authorization", "HTTP_ERROR_", "ARTIFACT_DUPLICATE_MEMBER", "ARTIFACT_UNSAFE_MEMBER_PATH", "ARTIFACT_UNCOMPRESSED_SIZE_LIMIT", "ARTIFACT_MEMBER_NOT_REGULAR_FILE", "ARTIFACT_EXE_TOO_LARGE", "LOCAL_EXE_SHA_MISMATCH", "PASS_INDEPENDENT_BUILD_ONLY", "EXE_QA_UNSIGNED", "NOT_BUILT", "gdk_package_verified"):
        assert token in verifier, "INDEPENDENT_VERIFIER_GUARD_MISSING:" + token
    results.append({"case": "workflow source and evidence upload contract", "result": "PASS_STATIC_ONLY"})
    cloud_build_workflow = pathlib.Path(".github/workflows/signal-sprint-cloud-build-proof.yml").read_text(encoding="utf-8")
    cloud_failure_guards = (
        "failure_reason", "failure_command", "HOLD_FROZEN_SOURCE_EXE_BUILD_FAILED",
        "HOLD_INDEPENDENT_VERIFICATION_FAILED", "HOLD_INDEPENDENT_VERIFICATION_INCOMPLETE",
        "HOLD_ARTIFACT_DOWNLOAD_FAILED", "windows-frozen-source-exe:",
        "actions/download-artifact@v4", "artifact-id", "merge-multiple: true", "build-provenance.json",
        "workflow_head_sha", "artifact_provenance_path", "exe_size_bytes",
        "OpenRead(", "$stream.Read($mz, 0, 2)", "$stream.Dispose()",
        "local_size = exe.stat().st_size", "EMBEDDED_EXE_SIZE_MISMATCH",
        "stream.read(1024 * 1024)", "if: always()",
    )
    def assert_cloud_build_contract(candidate):
        assert all(required in candidate for required in cloud_failure_guards), "CLOUD_BUILD_GUARD_MISSING"
        assert "ReadAllBytes" not in candidate, "PE_HEADER_MUST_USE_STREAMING_READ"
        assert "exe.read_bytes()" not in candidate, "EXE_HASH_MUST_USE_STREAMING_READ"
    for token in cloud_failure_guards:
        assert token in cloud_build_workflow, "CLOUD_BUILD_GUARD_MISSING:" + token
        changed = cloud_build_workflow.replace(token, "REMOVED_BY_MUTATION_TEST")
        assert changed != cloud_build_workflow, "CLOUD_BUILD_MUTATION_NO_EFFECT:" + token
        results.append(negative("cloud build workflow mutation reject " + token,
                                lambda candidate=changed: assert_cloud_build_contract(candidate)))
    assert "vars.SIGNAL_SPRINT_BUILD_RUN_ID" not in cloud_build_workflow, "MANUAL_BUILD_RUN_VARIABLE_MUST_NOT_BE_REQUIRED"
    assert "vars.SIGNAL_SPRINT_BUILD_ARTIFACT_ID" not in cloud_build_workflow, "MANUAL_BUILD_ARTIFACT_VARIABLE_MUST_NOT_BE_REQUIRED"
    # Check the real UIA gate source, not only self-declared fixture constants.
    gate = pathlib.Path("qa/signal_sprint_uia_dynamic_gate.ps1").read_text(encoding="utf-8")
    assert_gate_contract(gate)
    expected_map = re.search(r"\$expected\s*=\s*@\{\s*EN\s*=\s*@\((.*?)\)\s*JP\s*=\s*@\((.*?)\)\s*\}", gate, re.S)
    for language, group in (("EN", 1), ("JP", 2)):
        block = expected_map.group(group)
        for variant, changed_block in (
            ("extra button", block + ", 'Unexpected (X)'"),
            ("duplicate button", block + ", '" + BUTTONS[language][0] + "'"),
            ("missing button", block.replace("'" + BUTTONS[language][-1] + "'", "", 1)),
        ):
            mutated = gate[:expected_map.start(group)] + changed_block + gate[expected_map.end(group):]
            results.append(negative(language + " exact-set mutation reject " + variant,
                                    lambda candidate=mutated: assert_gate_contract(candidate)))
        results.append({"case": language + " exact 5-button/LOST source contract", "result": "PASS_STATIC_ONLY"})
    # Each mutation must make the complete contract validator fail, not just
    # reduce the number of occurrences of a string.
    for language in ("EN", "JP"):
        for label in [*BUTTONS[language], LOST[language]]:
            needle = "'" + label + "'" if label in BUTTONS[language] else label
            assert needle in gate, "MISSING_CONTRACT:" + language + ":" + label
            mutated = gate.replace(needle, "REMOVED_BY_FIXTURE")
            assert mutated != gate, "MUTATION_DID_NOT_REMOVE:" + label
            results.append(negative(language + " mutation reject " + label,
                                    lambda changed=mutated: assert_gate_contract(changed)))
    for assertion in ("BILINGUAL_BUTTON_COVERAGE_INCOMPLETE", "LOST_UIA_NOT_OBSERVED",
                      "ACTION_SEMANTIC_STATE_NOT_OBSERVABLE", "side_effect_verified",
                      "GetCurrentPattern", "Invoke()", "lost_uia_nodes"):
        assert assertion in gate, "UIA_ASSERTION_MISSING:" + assertion
    results.append({"case": "dynamic UIA semantic assertions present", "result": "PASS_STATIC_ONLY"})
def main():
    results = []
    status = "FAIL"
    failure = None
    try:
        expected_head = os.environ.get("EXPECTED_HEAD")
        if expected_head is not None:
            assert re.fullmatch(r"[a-f0-9]{40}", expected_head), "WORKFLOW_HEAD_INVALID"
        actions_run_id = os.environ.get("ACTIONS_RUN_ID")
        if actions_run_id is not None:
            assert re.fullmatch(r"[1-9][0-9]*", actions_run_id), "ACTIONS_RUN_ID_INVALID"
        run_checks(results)
        status = "PASS"
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc),
                   "traceback": traceback.format_exc(limit=8)}
    finally:
        out = pathlib.Path("evidence")
        out.mkdir(parents=True, exist_ok=True)
        (out / "cloud-provenance-fixture.json").write_text(json.dumps({
            "workflow_head": os.environ.get("EXPECTED_HEAD"),
            "actions_run_id": os.environ.get("ACTIONS_RUN_ID"),
            "fixture_source_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
            "uia_workflow_source_sha256": hashlib.sha256(pathlib.Path(".github/workflows/signal-sprint-windows-uia-evidence.yml").read_bytes()).hexdigest(),
            "uia_gate_source_sha256": hashlib.sha256(pathlib.Path("qa/signal_sprint_uia_dynamic_gate.ps1").read_bytes()).hexdigest(),
            "independent_verifier_source_sha256": hashlib.sha256(pathlib.Path("qa/signal_sprint_independent_build_verify.py").read_bytes()).hexdigest(),
            "cloud_build_workflow_source_sha256": hashlib.sha256(pathlib.Path(".github/workflows/signal-sprint-cloud-build-proof.yml").read_bytes()).hexdigest(),
            "schema": "signal-sprint-cloud-fixture-v4",
            "status": status, "failure": failure,
            "product_source": SOURCE, "reference_win_lose_head": HEAD,
            "source_alignment": "UNVERIFIED_DIFFERENT_SOURCE_REFS" if SOURCE != HEAD else "SAME_REF_NOT_BUILD_PROOF",
            "functional_gate": "HOLD_REAL_WINDOWS_UIA",
            "delivery_gate": "HOLD_GDK_PACKAGE",
            "independent_build_verified": False, "physical_gui_verified": False,
            "results": results
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Cloud fixture:", status, len(results), "checks; NOT physical GUI or independent build proof")
    if failure:
        print(failure["traceback"], file=sys.stderr)
        raise SystemExit(1)

if __name__ == "__main__":
    main()
