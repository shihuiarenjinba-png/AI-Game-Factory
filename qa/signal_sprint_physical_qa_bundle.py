"""Reproducible Signal Sprint Windows QA EXE bundle; never a GDK package.

Build and verify bind the *executed* EXE bytes, screenshot receipt, workflow
run and exact revision. Structural tests are synthetic, not GUI certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

IMMUTABLE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST = "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e"
OLD_GDK_EXE = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
HEAD_RE = re.compile(r"^[a-f0-9]{40}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
MAX_EXE = 80 * 1024 * 1024
MAX_TOTAL = 160 * 1024 * 1024
FALSE_GATES = ("sale_ready", "human_qa_pass", "cas_return_pass", "gdk_sdk_executed",
               "msixvc2_built", "store_submitted", "approved_cas_for_revision",
               "approved_version_and_assets", "approved_gdk_package_exe")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def safe_name(name: str) -> bool:
    return (isinstance(name, str) and bool(name) and not name.startswith("/")
            and "\\" not in name and all(part not in ("", ".", "..") for part in name.split("/")))


def _expected_manifest(receipt: dict, revision: str, run_id: str, files: list) -> dict:
    return {
        "schema_version": 1,
        "product": "Signal Sprint",
        "registration": "GDK_GAME",
        "partner_center_route": "GDK game",
        "evidence_kind": "REAL_EXECUTED_GUI_EXE_FOR_PHYSICAL_QA_ONLY",
        "immutable_source_sha": IMMUTABLE,
        "original_request_id": REQUEST,
        "build_head_sha": revision,
        "workflow_run_id": str(run_id),
        "exe_path": "SignalSprint.exe",
        "exe_sha256": receipt["exe_sha256"],
        "exe_size_bytes": receipt["exe_size_bytes"],
        "gui_receipt_path": "ui-revision-receipt.json",
        "gui_receipt_sha256": None,
        "screenshots": files,
        "package_format": "NOT_A_GDK_PACKAGE",
        "real_os_dpi_125_150": "HOLD",
        "consumer_human_qa": "HOLD",
        "gdk_sdk_status": "HOLD_NOT_EXECUTED",
        "release_gates": {key: False for key in FALSE_GATES},
    }


def validate_archive_structure(archive: Path, revision: str, run_id: str) -> tuple[list[str], dict | None]:
    """Pure archive/lineage integrity check, not a real Windows GUI PASS."""
    errors: list[str] = []
    manifest = None
    try:
        if not HEAD_RE.fullmatch(revision) or not str(run_id).isdigit():
            return ["EXPECTED_REVISION_OR_RUN_INVALID"], None
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if len(infos) > 80 or len(set(names)) != len(names):
                return ["DUPLICATE_OR_EXCESS_ZIP_ENTRIES"], None
            if any(not safe_name(i.filename) or i.is_dir() or
                   stat.S_IFMT(i.external_attr >> 16) == stat.S_IFLNK or
                   i.file_size > MAX_EXE or i.compress_size > MAX_EXE for i in infos):
                return ["UNSAFE_ZIP_ENTRY"], None
            if sum(i.file_size for i in infos) > MAX_TOTAL:
                return ["ZIP_TOTAL_SIZE_EXCEEDED"], None
            if z.testzip() is not None:
                return ["ZIP_CRC_FAILED"], None
            if "manifest.json" not in names or "ui-revision-receipt.json" not in names or "SignalSprint.exe" not in names:
                return ["REQUIRED_BUNDLE_MEMBER_MISSING"], None
            if z.getinfo("manifest.json").file_size > 100000 or z.getinfo("ui-revision-receipt.json").file_size > 200000:
                return ["BUNDLE_METADATA_OVERSIZED"], None
            manifest = json.loads(z.read("manifest.json"))
            receipt_bytes = z.read("ui-revision-receipt.json")
            receipt = json.loads(receipt_bytes.decode("utf-8-sig"))
            exe_bytes = z.read("SignalSprint.exe")
            shots = manifest.get("screenshots")
            if not isinstance(shots, list) or not shots or len(shots) > 60:
                return ["SCREENSHOT_INVENTORY_INVALID"], manifest
            shot_names = [item.get("path") for item in shots if isinstance(item, dict)]
            if len(shot_names) != len(shots) or len(set(shot_names)) != len(shots):
                errors.append("SCREENSHOT_INVENTORY_DUPLICATE")
            expected_names = {"manifest.json", "ui-revision-receipt.json", "SignalSprint.exe", *shot_names}
            if set(names) != expected_names:
                errors.append("ZIP_MEMBER_SET_MISMATCH")
            if any(not isinstance(name, str) or not name.startswith("screenshots/") or
                   not name.endswith(".png") or not safe_name(name) for name in shot_names):
                errors.append("SCREENSHOT_NAME_INVALID")
            for item in shots:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str) or item["path"] not in names:
                    errors.append("SCREENSHOT_MISSING")
                    continue
                data = z.read(item["path"])
                if digest(data) != item.get("sha256") or len(data) != item.get("size_bytes"):
                    errors.append("SCREENSHOT_BYTES_MISMATCH")
                if not data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
                    errors.append("SCREENSHOT_NOT_PNG")
            if (len(exe_bytes) < 100000 or len(exe_bytes) > MAX_EXE or
                    not exe_bytes.startswith(b"MZ")):
                errors.append("EXECUTED_EXE_INVALID")
            if digest(exe_bytes) != manifest.get("exe_sha256") or len(exe_bytes) != manifest.get("exe_size_bytes"):
                errors.append("EXE_SHA_OR_SIZE_MISMATCH")
            if manifest.get("exe_sha256") == OLD_GDK_EXE:
                errors.append("OLD_GDK_EXE_SUBSTITUTION")
            if digest(receipt_bytes) != manifest.get("gui_receipt_sha256"):
                errors.append("GUI_RECEIPT_BYTES_MISMATCH")
            for key, expected in (("exe_sha256", manifest.get("exe_sha256")),
                                  ("exe_size_bytes", manifest.get("exe_size_bytes")),
                                  ("revision_sha", revision), ("workflow_run_id", str(run_id)),
                                  ("immutable_source_sha", IMMUTABLE), ("registration", "GDK_GAME")):
                if str(receipt.get(key)) != str(expected):
                    errors.append("GUI_RECEIPT_BINDING_" + key)
            for key, expected in (("schema_version", 1), ("product", "Signal Sprint"),
                                  ("registration", "GDK_GAME"), ("partner_center_route", "GDK game"),
                                  ("evidence_kind", "REAL_EXECUTED_GUI_EXE_FOR_PHYSICAL_QA_ONLY"),
                                  ("immutable_source_sha", IMMUTABLE), ("original_request_id", REQUEST),
                                  ("build_head_sha", revision), ("workflow_run_id", str(run_id)),
                                  ("exe_path", "SignalSprint.exe"), ("gui_receipt_path", "ui-revision-receipt.json"),
                                  ("package_format", "NOT_A_GDK_PACKAGE"), ("real_os_dpi_125_150", "HOLD"),
                                  ("consumer_human_qa", "HOLD"), ("gdk_sdk_status", "HOLD_NOT_EXECUTED")):
                if manifest.get(key) != expected:
                    errors.append("MANIFEST_LINEAGE_" + key)
            if manifest.get("release_gates") != {key: False for key in FALSE_GATES}:
                errors.append("FORBIDDEN_RELEASE_GATE")
            for key in ("sale_ready", "human_qa_pass", "cas_return_pass", "gdk_sdk_executed",
                        "msixvc2_built", "store_submitted"):
                if receipt.get(key) is not False:
                    errors.append("GUI_RECEIPT_FALSE_PASS_" + key)
            if receipt.get("status") != "GUI_WORK_AREA_AND_JP_TOGGLE_CHECK_ONLY":
                errors.append("GUI_RECEIPT_STATUS_UNTRUSTED")
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        errors.append("ZIP_UNREADABLE_OR_CORRUPT_" + type(exc).__name__)
    return sorted(set(errors)), manifest


def verify_real(archive: Path, revision: str, run_id: str, expected_exe: Path | None = None) -> list[str]:
    errors, manifest = validate_archive_structure(archive, revision, run_id)
    if errors:
        return errors
    if expected_exe is not None:
        try:
            if hash_file(expected_exe) != manifest["exe_sha256"] or expected_exe.stat().st_size != manifest["exe_size_bytes"]:
                return ["EXTERNAL_EXE_NOT_SAME_EXECUTED_BYTES"]
        except OSError:
            return ["EXTERNAL_EXE_UNAVAILABLE"]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with zipfile.ZipFile(archive) as z:
            for member in z.namelist():
                if member == "manifest.json":
                    continue
                target = root / member
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as source, target.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
        receipt = json.loads((root / "ui-revision-receipt.json").read_text(encoding="utf-8-sig"))
        from signal_sprint_visibility_receipt import verify as visibility
        from signal_sprint_bilingual_receipt import verify_bilingual
        visual_errors, _ = visibility(receipt, root / "screenshots", revision, run_id, root / "SignalSprint.exe")
        errors.extend(visual_errors)
        errors.extend(verify_bilingual(receipt, root / "screenshots", revision, root / "SignalSprint.exe"))
    return sorted(set(errors))


def build_bundle(exe: Path, receipt_path: Path, screenshots: Path,
                 revision: str, run_id: str, archive: Path) -> list[str]:
    if not HEAD_RE.fullmatch(revision) or not str(run_id).isdigit():
        return ["EXPECTED_REVISION_OR_RUN_INVALID"]
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes.decode("utf-8-sig"))
    if hash_file(exe) != receipt.get("exe_sha256") or exe.stat().st_size != receipt.get("exe_size_bytes"):
        return ["ACTUAL_EXECUTED_EXE_NOT_RECEIPT_MATCH"]
    if receipt.get("exe_sha256") == OLD_GDK_EXE:
        return ["OLD_GDK_EXE_SUBSTITUTION"]
    from signal_sprint_visibility_receipt import verify as visibility
    from signal_sprint_bilingual_receipt import verify_bilingual
    visual_errors, _ = visibility(receipt, screenshots, revision, run_id, exe)
    errors = visual_errors + verify_bilingual(receipt, screenshots, revision, exe)
    if errors:
        return sorted(set(errors))
    files = []
    for p in sorted(screenshots.rglob("*.png")):
        if p.is_symlink() or not p.is_file():
            return ["SCREENSHOT_SYMLINK_OR_MISSING"]
        relative = p.relative_to(screenshots).as_posix()
        name = "screenshots/" + relative
        if not safe_name(name):
            return ["SCREENSHOT_PATH_UNSAFE"]
        files.append({"path": name, "sha256": hash_file(p), "size_bytes": p.stat().st_size})
    manifest = _expected_manifest(receipt, revision, str(run_id), files)
    manifest["gui_receipt_sha256"] = digest(receipt_bytes)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as z:
        z.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))
        z.writestr("ui-revision-receipt.json", receipt_bytes)
        z.write(exe, "SignalSprint.exe")
        for item in files:
            z.write(screenshots / item["path"][len("screenshots/"):], item["path"])
    return verify_real(archive, revision, str(run_id), exe)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("build", "verify"), required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "build":
            if not all((args.exe, args.receipt, args.screenshots)):
                raise ValueError("BUILD_INPUTS_MISSING")
            errors = build_bundle(args.exe, args.receipt, args.screenshots,
                                  args.revision, args.run_id, args.bundle)
        else:
            errors = verify_real(args.bundle, args.revision, args.run_id, args.exe)
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        errors = ["BUNDLE_BUILD_OR_VERIFY_HOLD_" + type(exc).__name__]
    print(json.dumps({"status": "REAL_GUI_EXE_QA_BUNDLE_CHECK_ONLY" if not errors else "HOLD",
                      "errors": errors, "physical_human_qa": "HOLD",
                      "real_os_dpi_125_150": "HOLD", "gdk_package_ready": False,
                      "sale_ready": False}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
