"""Fail-closed Signal Sprint hosted GUI UIA receipt verifier.

A screenshot change, a CI success or a UIA HOLD string cannot certify controls.
This verifier intentionally does not assert physical Windows or GDK readiness.
"""
import argparse
import hashlib
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
def expected_inputs():
    """Independent immutable contract for the hosted Windows key sequence."""
    result = []
    def add(phase, language, key):
        result.append({"sequence": len(result) + 1, "phase": phase,
                       "language": language, "key": key})
    add("JP_TOGGLE", "EN", "j")
    add("JP_FIRST_MOVE", "JP", "{RIGHT}")
    add("JP_RESET", "JP", "r")
    for turn in range(30):
        add("JP_EXHAUSTION", "JP", "{RIGHT}" if turn % 2 == 0 else "{LEFT}")
    add("JP_LOST_RETRY", "JP", "r")
    add("JP_REPLAY", "JP", "{RIGHT}")
    add("EN_TOGGLE", "JP", "j")
    add("EN_RESET", "EN", "r")
    add("EN_FIRST_MOVE", "EN", "{RIGHT}")
    add("EN_PRE_EXHAUSTION_RESET", "EN", "r")
    for turn in range(30):
        add("EN_EXHAUSTION", "EN", "{RIGHT}" if turn % 2 == 0 else "{LEFT}")
    add("EN_LOST_RETRY", "EN", "r")
    add("EN_REPLAY", "EN", "{RIGHT}")
    return result


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(receipt, evidence_dir=None):
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
    # Validate the foreground PID measured by Windows immediately before SendKeys.
    events = receipt.get("focus_evidence")
    if not isinstance(events, list) or len(events) != len(expected_inputs()):
        errors.append("FOCUS_EVIDENCE_MISSING")
    else:
        for index, (event, expected) in enumerate(zip(events, expected_inputs())):
            if not isinstance(event, dict) or any(event.get(k) != v for k, v in expected.items()):
                errors.append("INPUT_SEQUENCE_MISMATCH_AT_" + str(index))
                break
            if (not isinstance(event, dict) or
                not isinstance(event.get("expected_pid"), int) or
                event.get("expected_pid") <= 0 or
                event.get("foreground_pid") != event.get("expected_pid") or
                not isinstance(event.get("foreground_handle"), int) or
                event.get("foreground_handle") == 0 or
                event.get("owned_before_input") is not True):
                errors.append("FOCUS_MISMATCH_AT_" + str(index))
                break
    for lang in ("en", "jp"):
        if not receipt.get(lang + "_screenshot_sha256") or not SHA.fullmatch(str(receipt.get(lang + "_screenshot_sha256"))):
            errors.append(lang.upper() + "_SCREENSHOT_UNBOUND")
    if evidence_dir is not None:
        evidence_dir = Path(evidence_dir)
        paths = {"exe_sha256": receipt.get("exe_path"),
                 "en_screenshot_sha256": "signal-sprint-en.png",
                 "jp_screenshot_sha256": "signal-sprint-jp.png"}
        for field, name in paths.items():
            if not isinstance(name, str) or not name:
                errors.append("EVIDENCE_PATH_MISSING_" + field.upper())
                continue
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                errors.append("EVIDENCE_PATH_UNSAFE_" + field.upper())
                continue
            candidate = (evidence_dir / path).resolve()
            if not candidate.is_relative_to(evidence_dir.resolve()):
                errors.append("EVIDENCE_PATH_ESCAPE_" + field.upper())
                continue
            if not candidate.is_file() or file_sha256(candidate) != receipt.get(field):
                errors.append("EVIDENCE_HASH_MISMATCH_" + field.upper())
    if receipt.get("human_qa_pass") is True or receipt.get("sale_ready") is True:
        errors.append("UNAUTHORIZED_PHYSICAL_OR_SALE_PASS")
    return errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
    errors = validate(data, evidence_dir=args.evidence_dir)
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
