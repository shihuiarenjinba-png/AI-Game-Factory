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
        "source_commit": SOURCE, "workflow_head_sha": workflow_head,
        "exe_sha256": sha, "build_run_url": url, "artifact_id": artifact_id,
        "artifact_exe_path": member, "artifact_provenance_path": provenance_member,
    }
    provenance = {
        "source_commit": SOURCE, "workflow_head_sha": workflow_head,
        "build_run_id": run_id, "exe_sha256": sha,
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
    def make_fetch(run_obj, artifact_obj, zip_bytes):
        def fetch(url, token, accept="application/vnd.github+json"):
            if url == f"{module.API}/actions/runs/{run_id}":
                return json.dumps(run_obj).encode()
            if url == f"{module.API}/actions/runs/{run_id}/jobs?per_page=100":
                return json.dumps(run_obj.get("_mock_jobs", jobs)).encode()
            if url == f"{module.API}/actions/artifacts/{artifact_id}":
                return json.dumps(artifact_obj).encode()
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
        assert good["exe_sha256"] == sha and good["physical_gui_verified"] is False
        assert good["build_provenance_verified"] is True
        assert good["build_job_name"] == module.BUILD_JOB_NAME
        assert good["run_status_at_verification"] == "in_progress"
        assert good["artifact_kind"] == "EXE_QA_UNSIGNED" and good["msix_status"] == "NOT_BUILT"
        assert good["gdk_package_verified"] is False
        results.append({"case": "mock API exact workflow, source receipt and unsigned EXE positive", "result": "PASS_SYNTHETIC"})
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
        queued_good = module.verify(receipt, exe_path, "mock-token",
                                    fetch=make_fetch({**run, "status": "queued"}, artifact, archive))
        assert queued_good["status"] == "PASS_INDEPENDENT_BUILD_ONLY"
        results.append({"case": "queued overall run with completed Windows build job is accepted", "result": "PASS_SYNTHETIC"})
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
    # The proof workflow builds only an unsigned pre-GDK EXE from the immutable product source.
    build_workflow = pathlib.Path(".github/workflows/signal-sprint-cloud-build-proof.yml").read_text(encoding="utf-8")
    for token in (
        "windows-frozen-source-exe:",
        "ref: 1a349faa41663c417c40710140a4d50c79b62b78",
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
    results.append({"case": "frozen source unsigned EXE builder never claims GDK/MSIX package", "result": "PASS_STATIC_ONLY"})
    # Keep the cloud fixture aligned with the actual Windows preflight contract.
    workflow = pathlib.Path(".github/workflows/signal-sprint-windows-uia-evidence.yml").read_text(encoding="utf-8")
    assert "$productSource = '" + SOURCE + "'" in workflow, "WORKFLOW_PRODUCT_SOURCE_DRIFT"
    assert SOURCE != HEAD, "PRODUCT_SOURCE_REFERENCE_ALIGNMENT_CHANGED_REVIEW_REQUIRED"
    assert "signal-sprint-cloud-provenance-fixture" in workflow, "CLOUD_ARTIFACT_UPLOAD_MISSING"
    assert "signal-sprint-uia-receipt" in workflow, "WINDOWS_ARTIFACT_UPLOAD_MISSING"
    # Assert evidence upload semantics, not merely artifact-name strings.
    cloud_job = workflow.split("  cloud-provenance-fixture:", 1)[1].split("  bilingual-uia:", 1)[0]
    windows_job = workflow.split("  bilingual-uia:", 1)[1]
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
        "trusted build run": "BUILD_RUN_URL_INVALID_OR_UNTRUSTED",
        "independent build disclaimer": "RECEIPT_MATCHED_NOT_INDEPENDENTLY_VERIFIED",
        "physical GUI disclaimer": "NOT_YET_TESTED",
    }
    for label, token in required_preflight.items():
        assert token in windows_job, "WINDOWS_PREFLIGHT_GUARD_MISSING:" + label
        results.append({"case": "Windows preflight guard " + label, "result": "PASS_STATIC_ONLY"})
    assert "if: github.event_name == 'workflow_dispatch'" in windows_job, "UIA_MUST_REQUIRE_DISPATCH"
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
        "independent build verified in UIA binding": "independent_build_verified=$true",
        "independent run and EXE binding": "INDEPENDENT_BUILD_UIA_BINDING_MISMATCH",
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
    for token in ("BUILD_WORKFLOW_PATH_MISMATCH", "BUILD_WORKFLOW_EVENT_INVALID", "WORKFLOW_HEAD_SHA_INVALID", "WORKFLOW_HEAD_MISMATCH", "RUN_NOT_ACTIVE_OR_COMPLETE", "RUN_JOBS_INVALID", "FROZEN_SOURCE_BUILD_JOB_NOT_UNIQUE", "FROZEN_SOURCE_BUILD_JOB_NOT_SUCCESS", "BUILD_ARTIFACT_NAME_MISMATCH", "RUN_NOT_SUCCESS", "ARTIFACT_RUN_MISMATCH", "ARTIFACT_WORKFLOW_HEAD_MISMATCH", "ARTIFACT_EXE_SHA_MISMATCH", "ARTIFACT_PROVENANCE_PATH_INVALID", "ARTIFACT_PROVENANCE_MISSING_OR_DUPLICATE", "ARTIFACT_PROVENANCE_NOT_REGULAR_FILE", "ARTIFACT_PROVENANCE_TOO_LARGE", "ARTIFACT_PROVENANCE_SOURCE_MISMATCH", "ARTIFACT_PROVENANCE_WORKFLOW_HEAD_MISMATCH", "ARTIFACT_PROVENANCE_RUN_ID_MISMATCH", "ARTIFACT_PROVENANCE_EXE_SHA_MISMATCH", "ARTIFACT_KIND_NOT_UNSIGNED_EXE", "MSIX_MUST_REMAIN_NOT_BUILT", "GDK_PACKAGE_MUST_NOT_BE_CLAIMED", "PHYSICAL_GUI_MUST_NOT_BE_CLAIMED", "ARTIFACT_ZIP_TOO_LARGE_OR_INVALID", "url.endswith(\"/zip\")", "application/vnd.github+json", "SafeRedirectHandler", "redirected.remove_header(name)", "Authorization", "HTTP_ERROR_", "ARTIFACT_DUPLICATE_MEMBER", "ARTIFACT_UNSAFE_MEMBER_PATH", "ARTIFACT_UNCOMPRESSED_SIZE_LIMIT", "ARTIFACT_MEMBER_NOT_REGULAR_FILE", "ARTIFACT_EXE_TOO_LARGE", "LOCAL_EXE_SHA_MISMATCH", "PASS_INDEPENDENT_BUILD_ONLY", "EXE_QA_UNSIGNED", "NOT_BUILT", "gdk_package_verified"):
        assert token in verifier, "INDEPENDENT_VERIFIER_GUARD_MISSING:" + token
    results.append({"case": "workflow source and evidence upload contract", "result": "PASS_STATIC_ONLY"})
    cloud_build_workflow = pathlib.Path(".github/workflows/signal-sprint-cloud-build-proof.yml").read_text(encoding="utf-8")
    cloud_failure_guards = (
        "failure_reason", "failure_command", "HOLD_FROZEN_SOURCE_EXE_BUILD_FAILED",
        "HOLD_INDEPENDENT_VERIFICATION_FAILED", "HOLD_INDEPENDENT_VERIFICATION_INCOMPLETE",
        "HOLD_ARTIFACT_DOWNLOAD_FAILED", "windows-frozen-source-exe:",
        "actions/download-artifact@v4", "artifact-id", "merge-multiple: true", "build-provenance.json",
        "workflow_head_sha", "artifact_provenance_path", "if: always()",
    )
    def assert_cloud_build_contract(candidate):
        assert all(required in candidate for required in cloud_failure_guards), "CLOUD_BUILD_GUARD_MISSING"
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
            "uia_gate_source_sha256": hashlib.sha256(pathlib.Path("qa/signal_sprint_uia_dynamic_gate.ps1").read_bytes()).hexdigest(),
            "independent_verifier_source_sha256": hashlib.sha256(pathlib.Path("qa/signal_sprint_independent_build_verify.py").read_bytes()).hexdigest(),
            "cloud_build_workflow_source_sha256": hashlib.sha256(pathlib.Path(".github/workflows/signal-sprint-cloud-build-proof.yml").read_bytes()).hexdigest(),
            "schema": "signal-sprint-cloud-fixture-v3",
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
