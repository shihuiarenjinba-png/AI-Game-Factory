"""Cloud-only negative/positive provenance contract fixture; never certifies a real EXE or GUI."""
import hashlib
import os
import json
import pathlib
import re
import sys
import traceback
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
    except (AssertionError, ValueError, KeyError):
        return {"case": label, "result": "PASS_REJECTED"}
    raise AssertionError("NEGATIVE_ACCEPTED:" + label)

def assert_gate_contract(gate):
    for language in ("EN", "JP"):
        assert len(BUTTONS[language]) == len(set(BUTTONS[language])) == 5
        for name in BUTTONS[language]:
            assert "'" + name + "'" in gate, "UIA_BUTTON_CONTRACT_MISSING:" + language + ":" + name
        assert LOST[language] in gate, "UIA_LOST_LABEL_MISSING:" + language

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
    for token in ("RUN_NOT_SUCCESS", "RUN_SOURCE_MISMATCH", "ARTIFACT_RUN_MISMATCH", "ARTIFACT_SOURCE_MISMATCH", "ARTIFACT_EXE_SHA_MISMATCH", "LOCAL_EXE_SHA_MISMATCH", "PASS_INDEPENDENT_BUILD_ONLY"):
        assert token in verifier, "INDEPENDENT_VERIFIER_GUARD_MISSING:" + token
    results.append({"case": "workflow source and evidence upload contract", "result": "PASS_STATIC_ONLY"})
    # Check the real UIA gate source, not only self-declared fixture constants.
    gate = pathlib.Path("qa/signal_sprint_uia_dynamic_gate.ps1").read_text(encoding="utf-8")
    assert_gate_contract(gate)
    for language in ("EN", "JP"):
        results.append({"case": language + " 5-button/LOST source contract", "result": "PASS_STATIC_ONLY"})
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
            "schema": "signal-sprint-cloud-fixture-v2",
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
