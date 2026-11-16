"""Cloud-only negative/positive provenance contract fixture; never certifies a real EXE or GUI."""
import hashlib
import json
import pathlib
import re
import tempfile
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
    assert receipt["exe_sha256"].lower() == digest, "RECEIPT_SHA_MISMATCH"
    assert receipt["source_commit"] == expected_source, "SOURCE_MISMATCH"
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

def main():
    exe = b"synthetic-fixture-only-not-a-shipping-executable"
    digest = hashlib.sha256(exe).hexdigest()
    receipt = {"source_commit": SOURCE, "exe_sha256": digest, "build_run_url": f"https://github.com/{REPO}/actions/runs/123456"}
    results = [{"case": "matching synthetic receipt", "result": "PASS_SYNTHETIC", "sha256": validate(receipt, exe, digest, SOURCE)}]
    for name, update in [
        ("tampered exe", {"exe": exe + b"x"}),
        ("wrong expected SHA", {"expected_sha": "0" * 64}),
        ("wrong receipt SHA", {"receipt": {**receipt, "exe_sha256": "0" * 64}}),
        ("wrong source", {"receipt": {**receipt, "source_commit": HEAD}}),
        ("spoofed host", {"receipt": {**receipt, "build_run_url": f"https://github.com.evil.test/{REPO}/actions/runs/123456"}}),
        ("wrong repository", {"receipt": {**receipt, "build_run_url": "https://github.com/other/repo/actions/runs/123456"}}),
        ("query suffix", {"receipt": {**receipt, "build_run_url": receipt["build_run_url"] + "?x=1"}}),
        ("invalid run id", {"receipt": {**receipt, "build_run_url": f"https://github.com/{REPO}/actions/runs/0"}}),
    ]:
        kwargs = {"receipt": receipt, "exe": exe, "expected_sha": digest, "expected_source": SOURCE}
        kwargs.update(update)
        results.append(negative(name, lambda kw=kwargs: validate(**kw)))
    # Check the real UIA gate source, not only self-declared fixture constants.
    gate = pathlib.Path("qa/signal_sprint_uia_dynamic_gate.ps1").read_text(encoding="utf-8")
    for language in ("EN", "JP"):
        assert len(BUTTONS[language]) == len(set(BUTTONS[language])) == 5
        for name in BUTTONS[language]:
            assert "'" + name + "'" in gate, "UIA_BUTTON_CONTRACT_MISSING:" + language + ":" + name
        assert LOST[language] in gate, "UIA_LOST_LABEL_MISSING:" + language
        results.append({"case": language + " 5-button/LOST source contract", "result": "PASS_STATIC_ONLY"})
    for assertion in ("BILINGUAL_BUTTON_COVERAGE_INCOMPLETE", "LOST_UIA_NOT_OBSERVED",
                      "ACTION_SEMANTIC_STATE_NOT_OBSERVABLE", "side_effect_verified",
                      "GetCurrentPattern", "Invoke()", "lost_uia_nodes"):
        assert assertion in gate, "UIA_ASSERTION_MISSING:" + assertion
    results.append({"case": "dynamic UIA semantic assertions present", "result": "PASS_STATIC_ONLY"})
    out = pathlib.Path("evidence")
    out.mkdir(exist_ok=True)
    (out / "cloud-provenance-fixture.json").write_text(json.dumps({
        "schema": "signal-sprint-cloud-fixture-v1",
        "product_source": SOURCE, "reference_win_lose_head": HEAD,
        "independent_build_verified": False, "physical_gui_verified": False,
        "results": results
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Cloud fixture:", len(results), "assertions; NOT physical GUI or independent build proof")

if __name__ == "__main__":
    main()
