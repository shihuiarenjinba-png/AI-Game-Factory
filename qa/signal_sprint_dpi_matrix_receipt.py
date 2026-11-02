"""Fail-closed cross-DPI evidence verifier; synthetic tests never certify GUI.

A green CI result means the verifier ran. Only CHECK_ONLY_REAL_DPI_GUI with
actual measured target DPI and same-EXE screenshots constitutes GUI evidence.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from signal_sprint_exhaustion_receipt import verify_receipt

IMMUTABLE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
SHA = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def verify_probe(probe, base, *, expected_revision, screenshot_dir=None):
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(probe.get("schema_version") == 1, "SCHEMA_MISMATCH")
    require(probe.get("product") == "Signal Sprint", "PRODUCT_MISMATCH")
    require(probe.get("registration") == "GDK_GAME", "REGISTRATION_MISMATCH")
    require(probe.get("immutable_source_sha") == IMMUTABLE, "SOURCE_MISMATCH")
    require(probe.get("revision_sha") == expected_revision and bool(COMMIT.fullmatch(expected_revision)), "REVISION_DRIFT")
    require(probe.get("revision_sha") == base.get("revision_sha"), "BASE_REVISION_DRIFT")
    require(str(probe.get("workflow_run_id", "")).isdigit(), "RUN_ID_MISSING")
    require(probe.get("workflow_run_id") == base.get("workflow_run_id"), "RUN_ID_MISMATCH")
    exe = probe.get("exe_sha256")
    require(isinstance(exe, str) and bool(SHA.fullmatch(exe)), "EXE_SHA_INVALID")
    require(exe == base.get("exe_sha256"), "EXE_NOT_SAME_PACKAGED_BINARY")
    require(type(probe.get("exe_size_bytes")) is int and probe["exe_size_bytes"] > 100000, "EXE_SIZE_INVALID")
    require(probe.get("exe_size_bytes") == base.get("exe_size_bytes"), "EXE_SIZE_DRIFT")
    target = probe.get("target_dpi_percent")
    observed = probe.get("os_system_dpi_percent")
    graphics = probe.get("graphics_dpi_percent")
    require(type(target) is int and target in (125, 150), "TARGET_DPI_INVALID")
    require(observed is None or (type(observed) is int and 50 <= observed <= 400), "OBSERVED_DPI_INVALID")
    require(graphics is None or (type(graphics) is int and 50 <= graphics <= 400), "GRAPHICS_DPI_INVALID")
    require(probe.get("human_qa_pass") is False and probe.get("sale_ready") is False, "FORBIDDEN_SALE_READY")
    for key in ("cas_return_pass", "gdk_sdk_executed", "msixvc2_built", "store_submitted"):
        require(probe.get(key) is False, "FORBIDDEN_" + key.upper())
    require(probe.get("text_clipping") == "HOLD_NOT_AUTOMATICALLY_RECOGNIZED", "FALSE_TEXT_CLIPPING_PASS")
    require(probe.get("uia_text_semantics") == "HOLD_NOT_AUTOMATICALLY_RECOGNIZED", "FALSE_UIA_TEXT_PASS")
    status = probe.get("status")
    require(status in ("HOLD_OS_DPI_NOT_TARGET", "HOLD_DPI_UNVERIFIED", "HOLD_GUI_UNVERIFIED", "CHECK_ONLY_REAL_DPI_GUI"), "UNKNOWN_STATUS")
    if status == "HOLD_OS_DPI_NOT_TARGET":
        require(observed is not None and observed != target, "FALSE_OS_DPI_HOLD")
        require(probe.get("gui_receipt_path") is None, "HOLD_CANNOT_HAVE_GUI_PASS")
    elif status == "HOLD_DPI_UNVERIFIED":
        require(observed is None or graphics is None or observed != graphics, "DPI_HOLD_WITHOUT_EVIDENCE_GAP")
        require(probe.get("gui_receipt_path") is None, "HOLD_CANNOT_HAVE_GUI_PASS")
    elif status == "HOLD_GUI_UNVERIFIED":
        require(probe.get("gui_receipt_path") is not None, "MISSING_FAILED_GUI_RECEIPT")
    elif status == "CHECK_ONLY_REAL_DPI_GUI":
        require(observed == target and graphics == target, "REAL_OS_DPI_NOT_VERIFIED")
        require(probe.get("monitor_bounds") == [0, 0, 1024, 768], "MONITOR_NOT_1024x768")
        work = probe.get("work_area_bounds")
        require(isinstance(work, list) and len(work) == 4 and work[2]-work[0] == 1024 and work[3]-work[1] == 720, "WORK_AREA_NOT_1024x720")
        require(screenshot_dir is not None, "SCREENSHOTS_REQUIRED")
        gui_path = probe.get("gui_receipt_path")
        if not isinstance(gui_path, str) or not gui_path:
            errors.append("GUI_RECEIPT_MISSING")
        else:
            try:
                inner = json.loads(Path(gui_path).read_text(encoding="utf-8-sig"))
                require(inner.get("exe_sha256") == exe, "INNER_EXE_MISMATCH")
                require(inner.get("workflow_run_id") == probe.get("workflow_run_id"), "INNER_RUN_MISMATCH")
                require(inner.get("dpi_percent") == target, "INNER_DPI_MISMATCH")
                errors.extend("GUI_" + err for err in verify_receipt(inner, screenshot_dir, expected_revision=expected_revision, expected_exe=exe))
            except (OSError, ValueError, TypeError) as exc:
                errors.append("GUI_RECEIPT_UNREADABLE:" + type(exc).__name__)
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    try:
        probe = json.loads(args.probe.read_text(encoding="utf-8-sig"))
        base = json.loads(args.base.read_text(encoding="utf-8-sig"))
        errors = verify_probe(probe, base, expected_revision=args.revision, screenshot_dir=args.screenshots)
    except (OSError, ValueError, TypeError) as exc:
        errors = ["UNREADABLE_EVIDENCE:" + type(exc).__name__]
        probe = {}
    print(json.dumps({"verification": "VALID_HOLD_OR_REAL_CHECK_ONLY" if not errors else "INVALID_HOLD",
                      "dpi_status": probe.get("status"), "errors": errors,
                      "sale_ready": False}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
