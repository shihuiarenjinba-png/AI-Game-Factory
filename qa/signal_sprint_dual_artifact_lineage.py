"""Fail-closed, read-only comparison of two REAL GitHub QA EXE artifacts.

Only a review lineage check. Never executes an EXE, approves physical QA, CAS,
GDK package, signing, MSIXVC2, or a Store submission.
"""
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

SOURCE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST = "game-signal-sprint-" + SOURCE
OLD_GDK_EXE = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
OLD_FIXED_QA_EXE = "95695560d524e70def41afa2de81eb9cf07f51862d40b9d5cef8624b528e4ea1"
PROFILES = {
    "pinned": dict(artifact=13180405918, gui_artifact=13180545199,
        run="41525954534", head="15b666871eb6749133df671ca1b271d89ecdf3ae",
        outer_sha="b3a57f479b987a6b32ea52bc3ba00fdd97cfc49ba06cc6f4771f257d8da0b78b",
        inner_sha="08d9e565058275c4283a8975ec200ec7357f4b024b60e7b39edfd94b971060e3",
        exe_sha="6d63ff1a09386e7c1203827a4707893b2e93c025aca5bf6f6976edf04d4396e8",
        exe_size=11446063),
    "candidate": dict(artifact=13185196046, gui_artifact=13185220900,
        run="41536644056", head="6ce4a9b47b55d865c33c7e0a50ffb18f5219c138",
        outer_sha="8fa5f5aad0f63abedc43b9c057f5ebb2c1e0350b0bf29055edda21cca797925a",
        inner_sha="7842e1f79770339629270562730b80443e202caf7bd5ad1bdd32047c10c7cddb",
        exe_sha="352b198c40fe5888af41047bd897e4357327c296691ccb77c7dae6a691da7a86",
        exe_size=11445323),
}
RELEASE = ("approved_cas_for_revision", "approved_gdk_package_exe",
    "approved_version_and_assets", "cas_return_pass", "gdk_sdk_executed",
    "human_qa_pass", "msixvc2_built", "sale_ready", "store_submitted")
PHASES = {
    "en_window_sha256": "screenshots/signal-sprint-en-window-initial.png",
    "en_exhausted_window_sha256": "screenshots/signal-sprint-en-turn-30-expected-lost.png",
    "en_replay_window_sha256": "screenshots/signal-sprint-en-after-lost-replay-right.png",
    "jp_window_sha256": "screenshots/signal-sprint-jp-window-initial.png",
    "exhausted_window_sha256": "screenshots/signal-sprint-jp-turn-30-expected-lost.png",
    "replay_window_sha256": "screenshots/signal-sprint-jp-after-lost-replay-right.png",
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def zip_errors(z, expected=None):
    names = z.namelist()
    errors = []
    if len(names) != len(set(names)):
        errors.append("ZIP_DUPLICATE_NAMES")
    if expected is not None and set(names) != set(expected):
        errors.append("ZIP_MEMBER_SET_MISMATCH")
    for entry in z.infolist():
        name = entry.filename
        if (name.startswith("/") or "\\" in name or
                any(part in ("", ".", "..") for part in name.split("/")) or
                (entry.external_attr >> 16) & 0o170000 == 0o120000):
            errors.append("ZIP_UNSAFE_ENTRY")
        if entry.file_size > 20000000:
            errors.append("ZIP_MEMBER_TOO_LARGE")
    if sum(x.file_size for x in z.infolist()) > 35000000:
        errors.append("ZIP_TOTAL_TOO_LARGE")
    if z.testzip() is not None:
        errors.append("ZIP_CRC_INVALID")
    return errors

def inspect_outer(path, profile):
    errors = []
    evidence = dict(artifact_id=profile["artifact"], gui_artifact_id=profile["gui_artifact"],
                    workflow_run_id=profile["run"], build_head_sha=profile["head"],
                    immutable_source_sha=SOURCE, original_request_id=REQUEST,
                    exe_sha256=profile["exe_sha"], exe_size_bytes=profile["exe_size"])
    try:
        data = Path(path).read_bytes()
        evidence["outer_sha256"] = sha(data)
        if len(data) > 25000000:
            return ["OUTER_TOO_LARGE"], evidence
        if sha(data) != profile["outer_sha"]:
            errors.append("OUTER_ARTIFACT_DIGEST_MISMATCH")
        with zipfile.ZipFile(io.BytesIO(data)) as outer:
            errors += zip_errors(outer, ["SignalSprint-physical-qa.zip"])
            if errors:
                return sorted(set(errors)), evidence
            inner_bytes = outer.read("SignalSprint-physical-qa.zip")
        evidence["inner_sha256"] = sha(inner_bytes)
        if sha(inner_bytes) != profile["inner_sha"]:
            errors.append("INNER_BUNDLE_DIGEST_MISMATCH")
        with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner:
            errors += zip_errors(inner)
            if errors:
                return sorted(set(errors)), evidence
            manifest = json.loads(inner.read("manifest.json"))
            receipt_bytes = inner.read("ui-revision-receipt.json")
            receipt = json.loads(receipt_bytes.decode("utf-8-sig"))
            exe = inner.read("SignalSprint.exe")
            screenshots = manifest.get("screenshots")
            if not isinstance(screenshots, list) or len(screenshots) < 6:
                errors.append("SCREENSHOT_MANIFEST_INCOMPLETE")
                screenshots = []
            expected_names = {"manifest.json", "ui-revision-receipt.json", "SignalSprint.exe"}
            image_shas = {}
            for shot in screenshots:
                if not isinstance(shot, dict):
                    errors.append("SCREENSHOT_ENTRY_INVALID")
                    continue
                name = shot.get("path")
                if not isinstance(name, str) or not name.startswith("screenshots/") or not name.endswith(".png"):
                    errors.append("SCREENSHOT_PATH_INVALID")
                    continue
                expected_names.add(name)
                raw = inner.read(name)
                if sha(raw) != shot.get("sha256") or len(raw) != shot.get("size_bytes"):
                    errors.append("SCREENSHOT_BYTES_MISMATCH")
                if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                    errors.append("SCREENSHOT_NOT_PNG")
                image_shas[name] = sha(raw)
            if set(inner.namelist()) != expected_names:
                errors.append("BUNDLE_FILE_SET_MISMATCH")
            for key, name in PHASES.items():
                if receipt.get(key) != image_shas.get(name) or not image_shas.get(name):
                    errors.append("GUI_PHASE_RECEIPT_MISMATCH_" + key)
            if sha(receipt_bytes) != manifest.get("gui_receipt_sha256"):
                errors.append("GUI_RECEIPT_TAMPERED")
            for key, value in (
                ("build_head_sha", profile["head"]), ("workflow_run_id", profile["run"]),
                ("immutable_source_sha", SOURCE), ("original_request_id", REQUEST),
                ("registration", "GDK_GAME"), ("partner_center_route", "GDK game"),
                ("package_format", "NOT_A_GDK_PACKAGE"),
                ("exe_sha256", profile["exe_sha"]), ("exe_size_bytes", profile["exe_size"]),
                ("consumer_human_qa", "HOLD"), ("real_os_dpi_125_150", "HOLD"),
                ("gdk_sdk_status", "HOLD_NOT_EXECUTED"),
            ):
                if manifest.get(key) != value:
                    errors.append("MANIFEST_BINDING_" + key)
            for key, value in (
                ("revision_sha", profile["head"]), ("workflow_run_id", profile["run"]),
                ("immutable_source_sha", SOURCE), ("registration", "GDK_GAME"),
                ("exe_sha256", profile["exe_sha"]), ("exe_size_bytes", profile["exe_size"]),
                ("dpi_percent", 100), ("target_dpi_percent", 100),
                ("human_qa_pass", False), ("sale_ready", False),
                ("msixvc2_built", False), ("gdk_sdk_executed", False),
            ):
                if receipt.get(key) != value:
                    errors.append("GUI_RECEIPT_BINDING_" + key)
            if receipt.get("ui_automation_controls") != "HOLD_UNVERIFIED":
                errors.append("UIA_FALSE_PASS")
            if any(receipt.get(k) not in ("HOLD_UNMEASURED", "HOLD_NOT_TESTED")
                   for k in ("dpi_125", "dpi_150")):
                errors.append("PHYSICAL_DPI_FALSE_PASS")
            if any(receipt.get(k) != "HOLD_UIAUTOMATION_TEXT_NOT_EXPOSED"
                   for k in ("lost_text_semantics", "en_lost_text_semantics")):
                errors.append("TEXT_SEMANTICS_FALSE_PASS")
            if manifest.get("release_gates") != {k: False for k in RELEASE}:
                errors.append("RELEASE_GATE_FALSE_PASS")
            if sha(exe) != profile["exe_sha"] or len(exe) != profile["exe_size"]:
                errors.append("EXE_BYTES_MISMATCH")
            if profile["exe_sha"] in (OLD_GDK_EXE, OLD_FIXED_QA_EXE, SOURCE):
                errors.append("OLD_GDK_OR_SOURCE_MISLABELED_AS_REVIEW_EXE")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, zipfile.BadZipFile,
            zipfile.LargeZipFile, EOFError) as exc:
        errors.append("ARTIFACT_UNVERIFIABLE_" + type(exc).__name__)
    return sorted(set(errors)), evidence

def compare(pinned_path, candidate_path, profiles=None):
    profiles = PROFILES if profiles is None else profiles
    a_errors, a = inspect_outer(pinned_path, profiles["pinned"])
    b_errors, b = inspect_outer(candidate_path, profiles["candidate"])
    errors = ["PINNED_" + x for x in a_errors] + ["CANDIDATE_" + x for x in b_errors]
    if a["build_head_sha"] == b["build_head_sha"] or a["workflow_run_id"] == b["workflow_run_id"]:
        errors.append("REVISION_AND_RUN_MUST_BE_SEPARATE")
    if errors:
        status = "LINEAGE_HOLD"
    elif (a["exe_sha256"], a["exe_size_bytes"]) == (b["exe_sha256"], b["exe_size_bytes"]):
        status = "SAME_EXE_BYTES_VERIFIED_DIFFERENT_RUNS"
    else:
        status = "DISTINCT_EXE_REVISIONS_VERIFIED"
    return dict(status=status, errors=sorted(set(errors)), pinned=a, candidate=b,
                physical_qa_status="PHYSICAL_HOLD", sale_ready=False,
                gdk_package_ready=False, msixvc2_built=False, cas_approved=False,
                limitation="ZIP and receipt integrity do not establish physical DPI or human QA")

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pinned", required=True, type=Path)
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    report = compare(args.pinned, args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "errors": report["errors"]}))
    return 2 if report["status"] == "LINEAGE_HOLD" else 0

if __name__ == "__main__":
    raise SystemExit(main())
