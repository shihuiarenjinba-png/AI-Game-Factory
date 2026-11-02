"""Read-only structural verifier for *real* Signal Sprint Windows GUI receipts.

This validates byte bindings and rejects false certification claims. It does
NOT prove the LOST text is visible, DPI 125/150, or human playability.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

IMMUTABLE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
IMAGES = {
    "jp_window_sha256": "signal-sprint-jp-window-initial.png",
    "after_input_window_sha256": "signal-sprint-jp-window-after-right.png",
    "pre_exhaustion_window_sha256": "signal-sprint-jp-turn-29.png",
    "exhausted_window_sha256": "signal-sprint-jp-turn-30-expected-lost.png",
    "post_exhaustion_restart_window_sha256": "signal-sprint-jp-after-lost-restart.png",
    "replay_window_sha256": "signal-sprint-jp-after-lost-replay-right.png",
}
SHA = re.compile(r"^[a-f0-9]{64}$")
COMMIT = re.compile(r"^[a-f0-9]{40}$")


def verify_receipt(receipt, screenshot_dir, expected_revision=None, expected_exe=None):
    errors = []
    def require(condition, reason):
        if not condition:
            errors.append(reason)

    require(receipt.get("product") == "Signal Sprint", "WRONG_PRODUCT")
    require(receipt.get("registration") == "GDK_GAME", "WRONG_REGISTRATION")
    require(receipt.get("immutable_source_sha") == IMMUTABLE, "IMMUTABLE_SOURCE_MISMATCH")
    require(receipt.get("evidence_kind") == "NEW_REVISION_REAL_WINDOWS_GUI_CHECK_ONLY", "WRONG_EVIDENCE_KIND")
    revision = receipt.get("revision_sha")
    require(isinstance(revision, str) and bool(COMMIT.fullmatch(revision)), "REVISION_SHA_MISSING")
    if expected_revision:
        require(revision == expected_revision, "REVISION_SHA_DRIFT")
    exe = receipt.get("exe_sha256")
    require(isinstance(exe, str) and bool(SHA.fullmatch(exe)), "EXE_SHA_MISSING")
    if expected_exe:
        require(exe == expected_exe, "EXE_SHA_MISMATCH")
    require(isinstance(receipt.get("exe_size_bytes"), int) and receipt["exe_size_bytes"] > 100000, "EXE_SIZE_INVALID")
    require(str(receipt.get("workflow_run_id", "")).isdigit(), "GITHUB_RUN_ID_MISSING")
    require(receipt.get("status") == "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY", "GUI_NOT_CHECK_ONLY_SUCCESS")
    require(receipt.get("exhaustion_gui_check_only") == "REAL_30_KEYS_AND_CHANGED_LAST_FRAME_CHECK_ONLY", "EXHAUSTION_NOT_OBSERVED")
    require(receipt.get("exhaustion_move_count") == 30, "MOVE_COUNT_NOT_30")
    require(receipt.get("exhaustion_input_sequence") == ["RIGHT" if i % 2 == 0 else "LEFT" for i in range(30)], "INPUT_SEQUENCE_WRONG")
    for field in ("retry_restores_initial_window_pixels", "exhaustion_pixel_change_observed",
                  "exhaustion_reset_pixel_match", "replay_pixel_match", "jp_window_title_observed"):
        require(receipt.get(field) is True, field.upper() + "_NOT_PROVEN")
    for field in ("human_qa_pass", "sale_ready", "cas_return_pass", "gdk_sdk_executed",
                  "msixvc2_built", "store_submitted"):
        require(receipt.get(field) is False, "FORBIDDEN_SUCCESS_CLAIM_" + field)
    # A single real OS DPI run can prove only its own target; the other
    # scale stays HOLD. This verifier does not replace the independent OS probe.
    target_dpi = receipt.get("target_dpi_percent", 100)
    for dpi in (125, 150):
        field = "dpi_" + str(dpi)
        if target_dpi == dpi and receipt.get("dpi_percent") == dpi:
            require(receipt.get(field) == "REAL_OS_DPI_" + str(dpi) + "_GUI_CHECK_ONLY",
                    "DPI_MEASURED_LABEL_INVALID_" + field)
        else:
            require(str(receipt.get(field, "")).startswith("HOLD_"),
                    "UNMEASURED_FALSE_PASS_" + field)
    require(str(receipt.get("jp_en_text_clipping", "")).startswith("HOLD_"),
            "UNMEASURED_FALSE_PASS_jp_en_text_clipping")
    expected_matrix_hold = "HOLD_NOT_TESTED" if target_dpi == 100 else "HOLD_OTHER_DPI_NOT_TESTED"
    require(receipt.get("dpi_125_150") == expected_matrix_hold, "DPI_FALSE_PASS")
    require(receipt.get("lost_text_semantics") in (
        "UIAUTOMATION_JP_LOST_TEXT_OBSERVED",
        "HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED",
        "HOLD_UIAUTOMATION_UNAVAILABLE"), "LOST_TEXT_UNTRUSTED")
    work = receipt.get("work_area_bounds")
    window = receipt.get("window_bounds")
    if (isinstance(work, list) and isinstance(window, list) and
            len(work) == len(window) == 4 and
            all(type(v) is int for v in work + window)):
        require(work[0] <= window[0] < window[2] <= work[2] and
                work[1] <= window[1] < window[3] <= work[3], "WINDOW_OUTSIDE_WORK_AREA")
    else:
        errors.append("BOUNDS_MISSING")
    for field, filename in IMAGES.items():
        value = receipt.get(field)
        require(isinstance(value, str) and bool(SHA.fullmatch(value)), "MISSING_SHA_" + field)
        path = Path(screenshot_dir) / filename
        if not path.is_file():
            errors.append("MISSING_SCREENSHOT_" + filename)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != value:
            errors.append("SCREENSHOT_TAMPER_" + filename)
    require(receipt.get("jp_window_sha256") != receipt.get("after_input_window_sha256"), "FIRST_MOVE_NO_CHANGE")
    require(receipt.get("pre_exhaustion_window_sha256") != receipt.get("exhausted_window_sha256"), "LAST_MOVE_NO_CHANGE")
    require(receipt.get("jp_window_sha256") == receipt.get("post_exhaustion_restart_window_sha256"), "RESET_NOT_EQUAL")
    require(receipt.get("after_input_window_sha256") == receipt.get("replay_window_sha256"), "REPLAY_NOT_EQUAL")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
        errors = verify_receipt(receipt, args.screenshots, expected_revision=args.revision)
    except (OSError, ValueError, TypeError) as exc:
        errors = ["RECEIPT_UNREADABLE:" + type(exc).__name__]
    print(json.dumps({"result": "CHECK_ONLY" if not errors else "HOLD",
                      "errors": errors,
                      "sale_ready": False,
                      "dpi_125_150": "HOLD_UNMEASURED",
                      "lost_text_semantics": "SEPARATE_REVIEW_REQUIRED"}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
