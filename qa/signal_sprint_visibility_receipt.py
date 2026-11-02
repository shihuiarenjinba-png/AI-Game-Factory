"""Fail-closed screenshot geometry/pixel-ROI check for Signal Sprint's separate UI revision.

This is *not* OCR, semantic translation verification, DPI 125/150, or human QA.
The screenshots must come from the real EXE in the same Windows workflow run.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageChops

IMMUTABLE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
# Window-relative, based on the 916x659 window measured on 1024x768 / OS DPI 100.
# Regions are deliberately wider than their text, with a >=4 px edge guard.
REGIONS = {
    "heading": ((270, 40, 650, 85), 500),
    "objective": ((270, 88, 650, 117), 80),
    "counters": ((505, 125, 725, 191), 200),
    "instructions": ((505, 188, 898, 222), 70),
    "status": ((535, 229, 880, 264), 15),
    "state_message": ((535, 262, 880, 297), 70),
    "controls": ((505, 299, 899, 449), 350),
}
SCREENS = {
    "en_initial": ("signal-sprint-en-window-initial.png", "en_window_sha256"),
    "jp_initial": ("signal-sprint-jp-window-initial.png", "jp_window_sha256"),
    "en_lost": ("signal-sprint-en-turn-30-expected-lost.png", "en_exhausted_window_sha256"),
    "jp_lost": ("signal-sprint-jp-turn-30-expected-lost.png", "exhausted_window_sha256"),
}
SHA = re.compile(r"^[0-9a-f]{64}$")
HEAD = re.compile(r"^[0-9a-f]{40}$")


def _hash(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _bounds(value):
    return (isinstance(value, list) and len(value) == 4 and
            all(type(v) is int for v in value) and value[0] < value[2] and value[1] < value[3])


def _bright_box(image, rect):
    x0, y0, x1, y1 = rect
    found = []
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            r, g, b = image.getpixel((xx, yy))[:3]
            if min(r, g, b) > 125 and max(r, g, b) > 175:
                found.append((xx, yy))
    if not found:
        return 0, None
    return len(found), [min(p[0] for p in found), min(p[1] for p in found),
                        max(p[0] for p in found), max(p[1] for p in found)]


def verify(receipt, screenshots, revision, run_id, exe=None):
    """Return (errors, report). No successful result certifies glyph or text meaning."""
    errors = []
    regions = []
    def require(test, reason):
        if not test:
            errors.append(reason)

    require(receipt.get("product") == "Signal Sprint", "PRODUCT_MISMATCH")
    require(receipt.get("registration") == "GDK_GAME", "REGISTRATION_MISMATCH")
    require(receipt.get("immutable_source_sha") == IMMUTABLE, "IMMUTABLE_SOURCE_MISMATCH")
    require(bool(HEAD.fullmatch(str(revision))), "EXPECTED_HEAD_INVALID")
    require(receipt.get("revision_sha") == revision, "REVISION_HEAD_MISMATCH")
    require(str(receipt.get("workflow_run_id")) == str(run_id) and bool(str(run_id)), "RUN_ID_MISMATCH")
    require(receipt.get("evidence_kind") == "NEW_REVISION_REAL_WINDOWS_GUI_CHECK_ONLY", "EVIDENCE_KIND_MISMATCH")
    require(receipt.get("status") == "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY", "GUI_NOT_CHECK_ONLY_PASS")
    require(receipt.get("language_matrix_status") == "REAL_JP_AND_EN_SAME_EXE_CHECK_ONLY", "LANGUAGE_MATRIX_MISSING")
    require(receipt.get("dpi_percent") == 100 and receipt.get("target_dpi_percent") == 100,
            "REAL_OS_DPI_100_NOT_MEASURED")
    require(receipt.get("dpi_125") == "HOLD_UNMEASURED" and
            receipt.get("dpi_150") == "HOLD_UNMEASURED", "DPI_125_150_FALSE_PASS")
    require(receipt.get("jp_en_text_clipping") == "HOLD_UNMEASURED", "GLYPH_CLIPPING_FALSE_PASS")
    for forbidden in ("human_qa_pass", "sale_ready", "cas_return_pass", "gdk_sdk_executed", "msixvc2_built", "store_submitted"):
        require(receipt.get(forbidden) is False, "FORBIDDEN_PASS_" + forbidden)
    require(isinstance(receipt.get("exe_sha256"), str) and
            bool(SHA.fullmatch(receipt["exe_sha256"])), "EXE_SHA_INVALID")
    require(type(receipt.get("exe_size_bytes")) is int and receipt["exe_size_bytes"] > 100000,
            "EXE_SIZE_INVALID")
    if exe is not None:
        try:
            require(exe.is_file() and exe.stat().st_size == receipt.get("exe_size_bytes") and
                    _hash(exe) == receipt.get("exe_sha256"), "EXE_BYTES_MISMATCH")
        except OSError:
            errors.append("EXE_UNREADABLE")
    monitor, work, window = (receipt.get(k) for k in ("monitor_bounds", "work_area_bounds", "window_bounds"))
    require(_bounds(monitor) and monitor == [0, 0, 1024, 768], "MONITOR_NOT_1024x768")
    require(_bounds(work) and work == [0, 0, 1024, 720], "WORK_AREA_NOT_1024x720")
    require(_bounds(window) and window == [16, 16, 932, 675], "WINDOW_NOT_MEASURED_BASELINE")
    if not all(_bounds(v) for v in (monitor, work, window)):
        return errors, {"regions": regions, "status": "HOLD", "limitations": _limitations()}
    require(work[0] <= window[0] < window[2] <= work[2] and
            work[1] <= window[1] < window[3] <= work[3], "WINDOW_OUTSIDE_WORK_AREA")

    images = {}
    for key, (filename, sha_field) in SCREENS.items():
        path = screenshots / filename
        try:
            require(_hash(path) == receipt.get(sha_field), "SCREENSHOT_SHA_MISMATCH_" + key)
            with Image.open(path) as src:
                require(src.format == "PNG" and src.size == (916, 659), "WINDOW_PNG_DIMENSIONS_" + key)
                images[key] = src.convert("RGB")
        except (OSError, ValueError):
            errors.append("SCREENSHOT_UNREADABLE_" + key)
            continue
        if images[key].size != (916, 659):
            continue
        regions.append({"screen": key, "regions": {}})
        for name, (rect, minimum) in REGIONS.items():
            count, box = _bright_box(images[key], rect)
            regions[-1]["regions"][name] = {"window_relative_roi": list(rect), "bright_pixels": count,
                                             "bright_bounds": box}
            require(count >= minimum, "REGION_EMPTY_" + key + "_" + name)
            if box:
                x0, y0, x1, y1 = rect
                require(box[0] >= x0 + 4 and box[1] >= y0 + 4 and
                        box[2] <= x1 - 5 and box[3] <= y1 - 5,
                        "REGION_EDGE_CLIP_RISK_" + key + "_" + name)
    # Independently bind monitor screenshot pixels to the measured window crop.
    for lang, field in (("en", "en_screenshot_sha256"), ("jp", "jp_screenshot_sha256")):
        try:
            path = screenshots / ("signal-sprint-" + lang + ".png")
            require(_hash(path) == receipt.get(field), "MONITOR_SCREENSHOT_SHA_MISMATCH_" + lang)
            with Image.open(path) as src:
                require(src.format == "PNG" and src.size == (1024, 768), "MONITOR_PNG_DIMENSIONS_" + lang)
                cropped = src.convert("RGB").crop(tuple(window))
            if lang + "_initial" in images:
                require(ImageChops.difference(cropped, images[lang + "_initial"]).getbbox() is None,
                        "MONITOR_WINDOW_CROP_MISMATCH_" + lang)
        except (OSError, ValueError):
            errors.append("MONITOR_SCREENSHOT_UNREADABLE_" + lang)
    if "en_initial" in images and "jp_initial" in images:
        require(ImageChops.difference(images["en_initial"], images["jp_initial"]).getbbox() is not None,
                "JP_EN_PIXELS_IDENTICAL")
    return errors, {"status": "CHECK_ONLY" if not errors else "HOLD", "regions": regions,
                    "exe_sha256": receipt.get("exe_sha256"), "revision_sha": revision,
                    "workflow_run_id": str(run_id), "measured_os_dpi_percent": receipt.get("dpi_percent"),
                    "limitations": _limitations(), "errors": errors}


def _limitations():
    return ["PIXEL_ROI_NOT_OCR_OR_TRANSLATION_CERTIFICATION",
            "GLYPH_CLIPPING_AND_UIAUTOMATION_TEXT_HOLD",
            "REAL_OS_DPI_125_AND_150_HOLD", "HUMAN_QA_AND_SALE_READY_HOLD"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
        errors, report = verify(receipt, args.screenshots, args.revision, args.run_id, args.exe)
    except (OSError, ValueError, TypeError) as exc:
        errors = ["RECEIPT_UNREADABLE_" + type(exc).__name__]
        report = {"status": "HOLD", "errors": errors, "limitations": _limitations()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "errors": errors, "limitations": _limitations()}))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
