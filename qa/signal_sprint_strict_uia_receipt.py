"""Fail-closed Signal Sprint hosted GUI UIA receipt verifier.

A screenshot change, a CI success or a UIA HOLD string cannot certify controls.
This verifier intentionally does not assert physical Windows or GDK readiness.
"""
import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{64}$")
SOURCE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUIRED = {
    "en_buttons_in_workarea": "REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY",
    "jp_buttons_in_workarea": "REAL_UIA_FIVE_BUTTONS_INSIDE_WORKAREA_CHECK_ONLY",
    "lost_text_semantics": "UIAUTOMATION_JP_LOST_TEXT_OBSERVED",
    "en_lost_text_semantics": "UIAUTOMATION_EN_LOST_TEXT_OBSERVED",
}
def validate(receipt):
    errors = []
    if receipt.get("immutable_source_sha") != SOURCE:
        errors.append("SOURCE_BINDING_MISMATCH")
    if not SHA.fullmatch(str(receipt.get("exe_sha256", ""))):
        errors.append("EXE_SHA_UNBOUND")
    if not re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("revision_sha", ""))):
        errors.append("REVISION_SHA_UNBOUND")
    if not str(receipt.get("workflow_run_id", "")).isdigit():
        errors.append("CI_RUN_UNBOUND")
    if receipt.get("status") != "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY":
        errors.append("HOSTED_GUI_NOT_COMPLETE")
    for key, expected in REQUIRED.items():
        if receipt.get(key) != expected:
            errors.append("UIA_" + key.upper() + "_HOLD")
    # AppActivate alone does not establish focus ownership. The runner must
    # independently record foreground HWND and expected GUI HWND at every key.
    events = receipt.get("focus_events")
    if not isinstance(events, list) or len(events) < 68:
        errors.append("FOCUS_EVIDENCE_MISSING")
    else:
        for index, event in enumerate(events):
            if (not isinstance(event, dict) or
                not event.get("expected_hwnd") or
                event.get("foreground_hwnd") != event.get("expected_hwnd") or
                event.get("verified_before_send") is not True):
                errors.append("FOCUS_MISMATCH_AT_" + str(index))
                break
    for lang in ("en", "jp"):
        if not receipt.get(lang + "_screenshot_sha256") or not SHA.fullmatch(str(receipt.get(lang + "_screenshot_sha256"))):
            errors.append(lang.upper() + "_SCREENSHOT_UNBOUND")
    if receipt.get("human_qa_pass") is True or receipt.get("sale_ready") is True:
        errors.append("UNAUTHORIZED_PHYSICAL_OR_SALE_PASS")
    return errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
    errors = validate(data)
    result = {"schema_version": 1, "gate": "SIGNAL_SPRINT_HOSTED_UIA_STRICT",
              "status": "CHECK_ONLY_PASS" if not errors else "UIA_HOLD",
              "reasons": errors, "physical_windows": "PHYSICAL_HOLD",
              "gdk_package": "GDK_HOLD"}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errors else 2

if __name__ == "__main__":
    raise SystemExit(main())
