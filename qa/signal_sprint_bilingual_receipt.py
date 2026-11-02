"""Structural JP/EN real GUI screenshot verifier (not text/OCR certification).

Positive unit fixtures are synthetic; only CI screenshots from the real
packaged EXE, with a bound run HEAD and OS DPI, can be CHECK_ONLY evidence.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from signal_sprint_exhaustion_receipt import verify_receipt

EN_IMAGES = {
    "en_window_sha256": "signal-sprint-en-window-initial.png",
    "en_after_input_window_sha256": "signal-sprint-en-window-after-right.png",
    "en_pre_exhaustion_window_sha256": "signal-sprint-en-turn-29.png",
    "en_exhausted_window_sha256": "signal-sprint-en-turn-30-expected-lost.png",
    "en_post_exhaustion_restart_window_sha256": "signal-sprint-en-after-lost-restart.png",
    "en_replay_window_sha256": "signal-sprint-en-after-lost-replay-right.png",
}
SHA = re.compile(r"^[0-9a-f]{64}$")


def verify_bilingual(receipt, screenshot_dir, expected_revision=None, expected_exe=None):
    errors = verify_receipt(receipt, screenshot_dir, expected_revision, expected_exe)

    def require(condition, reason):
        if not condition:
            errors.append(reason)

    require(receipt.get("language_matrix_status") == "REAL_JP_AND_EN_SAME_EXE_CHECK_ONLY", "BILINGUAL_NOT_PROVEN")
    require(receipt.get("en_exhaustion_gui_check_only") == "REAL_EN_30_KEYS_RESTART_REPLAY_CHECK_ONLY", "EN_EXHAUSTION_NOT_PROVEN")
    require(receipt.get("en_exhaustion_move_count") == 30, "EN_MOVE_COUNT_WRONG")
    require(receipt.get("en_exhaustion_input_sequence") == ["RIGHT" if i % 2 == 0 else "LEFT" for i in range(30)], "EN_SEQUENCE_WRONG")
    require(receipt.get("en_lost_text_semantics") in (
        "UIAUTOMATION_EN_LOST_TEXT_OBSERVED",
        "HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED",
        "HOLD_UIAUTOMATION_UNAVAILABLE"), "EN_TEXT_UNTRUSTED")
    require(receipt.get("jp_en_text_clipping") == "HOLD_UNMEASURED", "GLYPH_CLIPPING_FALSE_PASS")
    require(receipt.get("target_dpi_percent") in (100, 125, 150), "TARGET_DPI_INVALID")
    require(receipt.get("dpi_percent") == receipt.get("target_dpi_percent"), "MEASURED_DPI_MISMATCH")
    bounds = receipt.get("window_bounds")
    if isinstance(bounds, list) and len(bounds) == 4 and all(type(x) is int for x in bounds):
        expected_size = (bounds[2]-bounds[0], bounds[3]-bounds[1])
    else:
        expected_size = None
        errors.append("WINDOW_BOUNDS_INVALID")
    for field, filename in EN_IMAGES.items():
        value = receipt.get(field)
        require(isinstance(value, str) and bool(SHA.fullmatch(value)), "EN_SHA_MISSING_" + field)
        path = Path(screenshot_dir) / filename
        if not path.is_file():
            errors.append("EN_IMAGE_MISSING_" + filename)
            continue
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == value, "EN_IMAGE_TAMPER_" + filename)
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            errors.append("EN_IMAGE_NOT_PNG_" + filename)
        elif expected_size is not None:
            require(struct.unpack(">II", data[16:24]) == expected_size, "EN_IMAGE_DIMENSIONS_NOT_WINDOW_" + filename)
    require(receipt.get("en_window_sha256") != receipt.get("en_after_input_window_sha256"), "EN_FIRST_MOVE_NO_CHANGE")
    require(receipt.get("en_pre_exhaustion_window_sha256") != receipt.get("en_exhausted_window_sha256"), "EN_LAST_MOVE_NO_CHANGE")
    require(receipt.get("en_window_sha256") == receipt.get("en_post_exhaustion_restart_window_sha256"), "EN_RESTART_NOT_EQUAL")
    require(receipt.get("en_after_input_window_sha256") == receipt.get("en_replay_window_sha256"), "EN_REPLAY_NOT_EQUAL")
    require(receipt.get("en_window_sha256") != receipt.get("jp_window_sha256"), "EN_JP_SAME_PIXELS")
    return errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--screenshots", type=Path, required=True)
    p.add_argument("--revision", required=True)
    args = p.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
        errors = verify_bilingual(receipt, args.screenshots, expected_revision=args.revision)
    except (OSError, ValueError, TypeError) as exc:
        errors = ["UNREADABLE_RECEIPT:" + type(exc).__name__]
    print(json.dumps({"result": "CHECK_ONLY" if not errors else "HOLD", "errors": errors,
                      "text_clipping": "HOLD_NOT_AUTOMATICALLY_RECOGNIZED",
                      "human_qa_pass": False, "sale_ready": False}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
