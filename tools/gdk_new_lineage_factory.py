"""Fail-closed Signal Sprint NEW lineage receipt (not old Artifact recovery or CAS).

This tool never submits to Store, modifies Git, or calls Partner Center.
The Factory's immutable source commit is built separately from the control HEAD.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
SOURCE_BRANCH = "codex/game-signal-sprint-undo-20261027"
OLD_REQUEST = "game-signal-sprint-" + SOURCE_SHA
OLD_ARTIFACT_ID = 12706862577
OLD_ZIP_SHA = "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412"
OLD_EXE_SHA_CANDIDATES = (
    "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad",
    "e8517df8cd31a40e5ce72afdd4e6a4d63626fb99f7ff8a4fa3296ff8deef05f4",
)
REPOSITORY = "shihuiarenjinba-png/AI-Game-Factory"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
BUILD_ID = re.compile(r"[a-z0-9][a-z0-9-]{7,31}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")


def hold(reason: str):
    raise ValueError("NEW_LINEAGE_HOLD: " + reason)


def _within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def new_request_id(build_id: str, run_id: str) -> str:
    if not isinstance(build_id, str) or not BUILD_ID.fullmatch(build_id):
        hold("invalid build ID")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        hold("invalid GitHub run ID")
    request = OLD_REQUEST + "-reissue-" + build_id + "-" + run_id
    if len(request) > 127 or request == OLD_REQUEST:
        hold("new request ID invalid or reused")
    return request


def validate_context(*, source_sha: str, source_head: str, build_head: str,
                     source_branch: str, build_id: str, run_id: str,
                     source_dir: Path, staging_dir: Path, control_dir: Path) -> str:
    request = new_request_id(build_id, run_id)
    if source_sha != SOURCE_SHA or source_head != SOURCE_SHA:
        hold("immutable source SHA mismatch")
    if source_branch != SOURCE_BRANCH:
        hold("immutable source branch mismatch")
    if not isinstance(build_head, str) or not SHA40.fullmatch(build_head):
        hold("invalid build HEAD")
    if build_head == SOURCE_SHA:
        hold("build HEAD conflated with immutable source")
    source, stage, control = (p.resolve(strict=True) for p in
                              (source_dir, staging_dir, control_dir))
    if _within(stage, source) or _within(stage, control):
        hold("staging inside Factory checkout")
    if _within(source, stage) or _within(control, stage):
        hold("Factory checkout inside staging")
    if source == control or _within(source, control) or _within(control, source):
        hold("source and control checkouts overlap")
    for path in (source_dir, staging_dir, control_dir):
        if path.is_symlink():
            hold("symlinked checkout/staging root")
    return request


def create_bundle(*, exe: Path, intake: dict, stage: Path, request_id: str,
                  build_id: str, run_id: str, build_head: str) -> dict:
    if request_id != new_request_id(build_id, run_id):
        hold("request ID does not belong to this build/run")
    if not SHA40.fullmatch(build_head) or build_head == SOURCE_SHA:
        hold("build HEAD invalid")
    if exe.is_symlink() or not exe.is_file() or not 100000 <= exe.stat().st_size <= 300_000_000:
        hold("missing, linked, or invalid EXE")
    with exe.open("rb") as stream:
        if stream.read(2) != b"MZ":
            hold("EXE is not a PE candidate")
    if stage.is_symlink() or not stage.is_dir():
        hold("staging missing or linked")
    required = {
        "request_id": request_id, "source_sha": SOURCE_SHA,
        "source_branch": SOURCE_BRANCH, "source_repository": REPOSITORY,
        "source_factory": "AI-Game-Factory", "product_type": "GAME",
        "slug": "signal-sprint", "dry_run": True,
    }
    if not isinstance(intake, dict) or any(intake.get(k) != v for k, v in required.items()):
        hold("Provisioner intake mismatch / old request reuse")
    if intake.get("schema_version") != "1.0":
        hold("unexpected intake schema")
    if any((stage / name).exists() or (stage / name).is_symlink()
           for name in ("new-lineage.zip", "lineage-receipt.json", "provenance.json")):
        hold("existing output must not be overwritten")
    exe_sha = _sha256(exe)
    provenance = {
        "schema_version": 1,
        "lineage_type": "NEW_IMMUTABLE_BUILD_NOT_OLD_ARTIFACT_RECOVERY",
        "request_id": request_id, "legacy_request_id": OLD_REQUEST,
        "legacy_artifact_id": OLD_ARTIFACT_ID,
        "legacy_artifact_replaced": False,
        "source_repository": REPOSITORY, "source_branch": SOURCE_BRANCH,
        "source_sha": SOURCE_SHA, "build_head_sha": build_head,
        "build_id": build_id, "github_run_id": int(run_id),
        "slug": "signal-sprint", "product_type": "GAME",
        "artifact_kind": "EXE_QA_UNSIGNED_NEW_LINEAGE",
        "executable": "SignalSprint.exe", "executable_sha256": exe_sha,
        "cas_status": "NOT_EXECUTED", "msixvc2_status": "NOT_BUILT",
        "store_submission": "FORBIDDEN",
    }
    encoded_provenance = (json.dumps(provenance, sort_keys=True, indent=2) + "\n").encode()
    encoded_intake = (json.dumps(intake, sort_keys=True, indent=2) + "\n").encode()
    archive = stage / "new-lineage.zip"
    try:
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for name, content in (("provenance.json", encoded_provenance),
                                  ("provisioner-request.json", encoded_intake)):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                z.writestr(info, content)
            info = zipfile.ZipInfo("SignalSprint.exe", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            with exe.open("rb") as reader, z.open(info, "w", force_zip64=True) as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(chunk)
        with zipfile.ZipFile(archive) as z:
            if set(z.namelist()) != {"provenance.json", "provisioner-request.json", "SignalSprint.exe"}:
                hold("unexpected ZIP contents")
            if hashlib.sha256(z.read("SignalSprint.exe")).hexdigest() != exe_sha:
                hold("ZIP EXE digest mismatch")
        zip_sha = _sha256(archive)
        if zip_sha == OLD_ZIP_SHA:
            hold("legacy ZIP reused")
        receipt = {
            "schema_version": 1, "status": "NEW_LINEAGE_ARTIFACT_CREATED_NOT_CAS",
            "request_id": request_id, "legacy_request_id": OLD_REQUEST,
            "legacy_artifact_id": OLD_ARTIFACT_ID,
            "legacy_zip_sha256": OLD_ZIP_SHA,
            "legacy_exe_sha256_authority_conflict": list(OLD_EXE_SHA_CANDIDATES),
            "legacy_artifact_recovered": False, "legacy_artifact_replaced": False,
            "source_repository": REPOSITORY, "source_sha": SOURCE_SHA,
            "source_branch": SOURCE_BRANCH, "build_head_sha": build_head,
            "build_id": build_id, "github_run_id": int(run_id),
            "artifact_kind": "EXE_QA_UNSIGNED_NEW_LINEAGE",
            "artifact_file": "new-lineage.zip", "artifact_sha256": zip_sha,
            "executable_sha256": exe_sha,
            "github_artifact_id": None,
            "github_evidence_verified": False,
            "cas_status": "NOT_EXECUTED", "msixvc2_status": "NOT_BUILT",
            "store_submission": "FORBIDDEN",
        }
        (stage / "lineage-receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return receipt
    except BaseException:
        archive.unlink(missing_ok=True)
        (stage / "lineage-receipt.json").unlink(missing_ok=True)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("source-dir", "control-dir", "staging-dir", "build-id",
                 "run-id", "build-head"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args(argv)
    try:
        source = Path(args.source_dir)
        control = Path(args.control_dir)
        stage = Path(args.staging_dir)
        for path in (source, control, stage):
            if not path.is_dir():
                hold("checkout/staging directory missing")
        source_head = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True, timeout=10).strip()
        control_head = subprocess.check_output(
            ["git", "-C", str(control), "rev-parse", "HEAD"], text=True, timeout=10).strip()
        if control_head != args.build_head:
            hold("build HEAD differs from checked-out control")
        request_id = validate_context(
            source_sha=SOURCE_SHA, source_head=source_head,
            build_head=args.build_head, source_branch=SOURCE_BRANCH,
            build_id=args.build_id, run_id=args.run_id, source_dir=source,
            staging_dir=stage, control_dir=control)
        exe = source / "dist/game/SignalSprint.exe"
        request_path = stage / "provisioner-request.json"
        if request_path.exists() or request_path.is_symlink():
            hold("intake output already exists")
        subprocess.run([
            sys.executable, str(source / "package_intake_request.py"),
            "--root", str(source), "--slug", "signal-sprint",
            "--request-id", request_id, "--source-sha", SOURCE_SHA,
            "--source-branch", SOURCE_BRANCH, "--output", str(request_path),
        ], check=True, timeout=30)
        intake = json.loads(request_path.read_text(encoding="utf-8"))
        receipt = create_bundle(
            exe=exe, intake=intake, stage=stage, request_id=request_id,
            build_id=args.build_id, run_id=args.run_id, build_head=args.build_head)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError,
            zipfile.BadZipFile) as exc:
        print("NEW_LINEAGE_HOLD: " + str(exc)[:240], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
