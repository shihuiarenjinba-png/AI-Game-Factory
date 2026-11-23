#!/usr/bin/env python3
"""Read-only Windows GDK SDK / MakePkg capability probe.

The probe never executes MakePkg, validates content, downloads or installs SDK
files, signs binaries, creates packages, or contacts Partner Center. A PASS
means only that a reviewed toolchain version and its Microsoft signatures were
observed on this Windows host; it is not package readiness or GUI evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

SCHEMA = "signal-sprint-gdk-sdk-capability-v1"
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}$")
MICROSOFT_CN_RE = re.compile(r"(?:^|,\s*)CN=Microsoft Corporation(?:,|$)", re.IGNORECASE)
REPARSE_POINT = 0x400


def _is_reparse_point(path: Path) -> bool:
    try:
        st = path.lstat()
        return path.is_symlink() or bool(getattr(st, "st_file_attributes", 0) & REPARSE_POINT)
    except OSError:
        return False


def _absolute_non_unc(path: Path) -> bool:
    raw = str(path)
    return path.is_absolute() and not raw.startswith(("\\\\", "//")) and ".." not in path.parts


def _is_descendant_without_reparse(root: Path, candidate: Path) -> bool:
    if not _absolute_non_unc(root) or not _absolute_non_unc(candidate):
        return False
    try:
        root_abs = root.absolute()
        candidate_abs = candidate.absolute()
        relative = candidate_abs.relative_to(root_abs)
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        resolved_candidate.relative_to(resolved_root)
    except (OSError, ValueError):
        return False
    if _is_reparse_point(root_abs):
        return False
    current = root_abs
    for part in relative.parts:
        if part in ("", ".", ".."):
            return False
        current = current / part
        if _is_reparse_point(current):
            return False
    return True


def _discover_makepkg(root: Path) -> list[Path]:
    found: list[Path] = []
    visited = 0
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        visited += 1
        if visited > 20000:
            break
        base = Path(current)
        directories[:] = [
            name for name in directories
            if not _is_reparse_point(base / name)
        ]
        for name in files:
            if name.casefold() == "makepkg.exe":
                found.append(base / name)
                if len(found) > 1:
                    return found
    return found


def _find_submission_validator(root: Path, makepkg: Path) -> Path | None:
    # Microsoft documents MakePkg's own directory first, then %GameDK%\\bin.
    candidates = [
        makepkg.parent / "SubmissionValidator.dll",
        root / "bin" / "SubmissionValidator.dll",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _powershell_json(path: Path, command: str) -> dict:
    powershell = (
        shutil.which("powershell.exe")
        or shutil.which("powershell")
        or shutil.which("pwsh.exe")
        or shutil.which("pwsh")
    )
    if not powershell:
        raise RuntimeError("POWERSHELL_UNAVAILABLE")
    env = os.environ.copy()
    env["GDK_PROBE_FILE"] = str(path)
    result = subprocess.run(
        [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("POWERSHELL_METADATA_QUERY_FAILED")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("POWERSHELL_METADATA_EMPTY")
    value = json.loads(lines[-1])
    if type(value) is not dict:
        raise RuntimeError("POWERSHELL_METADATA_NOT_OBJECT")
    return value


def _read_version(path: Path) -> dict:
    return _powershell_json(
        path,
        "$v=[Diagnostics.FileVersionInfo]::GetVersionInfo($env:GDK_PROBE_FILE); "
        "[pscustomobject]@{file_version=$v.FileVersion; product_version=$v.ProductVersion} "
        "| ConvertTo-Json -Compress",
    )


def _read_signature(path: Path) -> dict:
    return _powershell_json(
        path,
        "$s=Get-AuthenticodeSignature -LiteralPath $env:GDK_PROBE_FILE; "
        "$subject=$null; $thumbprint=$null; "
        "if($null -ne $s.SignerCertificate){$subject=$s.SignerCertificate.Subject;"
        "$thumbprint=$s.SignerCertificate.Thumbprint}; "
        "[pscustomobject]@{status=[string]$s.Status; signer_subject=$subject; "
        "signer_thumbprint=$thumbprint} | ConvertTo-Json -Compress",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _component_evidence(path: Path, version_reader, signature_reader) -> dict:
    version = version_reader(path)
    signature = signature_reader(path)
    if type(version) is not dict or type(signature) is not dict:
        raise ValueError("COMPONENT_METADATA_NOT_OBJECT")
    file_version = str(version.get("file_version") or "")
    product_version = str(version.get("product_version") or "")
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "file_version": file_version or None,
        "product_version": product_version or None,
        "effective_version": product_version or file_version or None,
        "signature_status": str(signature.get("status") or "UNKNOWN"),
        "signer_subject": signature.get("signer_subject"),
        "signer_thumbprint": signature.get("signer_thumbprint"),
    }


def _microsoft_signed(component: dict) -> bool:
    return (
        component.get("signature_status") == "Valid"
        and isinstance(component.get("signer_subject"), str)
        and MICROSOFT_CN_RE.search(component["signer_subject"]) is not None
    )


def probe(
    sdk_root: str | Path | None,
    *,
    makepkg_path: str | Path | None = None,
    expected_version: str | None = None,
    root_source: str = "EXPLICIT_OR_ENVIRONMENT",
    version_reader=_read_version,
    signature_reader=_read_signature,
    host_os: str | None = None,
    workflow_head_sha: str | None = None,
    build_run_id: str | int | None = None,
) -> dict:
    host = host_os or platform.system()
    receipt = {
        "schema": SCHEMA,
        "status": "HOLD_NOT_PROBED",
        "host_os": host,
        "runner_scope": "WINDOWS_HOST_ONLY_NOT_PHYSICAL_GUI",
        "sdk_root": str(sdk_root) if sdk_root else None,
        "sdk_root_source": root_source,
        "expected_sdk_version": expected_version or None,
        "workflow_head_sha": workflow_head_sha,
        "build_run_id": int(build_run_id) if str(build_run_id or "").isdigit() else None,
        "makepkg": None,
        "submission_validator": None,
        "read_only": True,
        "makepkg_executed": False,
        "submission_validator_executed": False,
        "sdk_validation_executed": False,
        "package_built": False,
        "msixvc2_built": False,
        "signing_performed": False,
        "store_submitted": False,
        "physical_gui_verified": False,
        "gdk_package_verified": False,
        "ordinary_msix_allowed": False,
    }

    def hold(status: str, reason: str | None = None) -> dict:
        receipt["status"] = status
        if reason:
            receipt["reason"] = reason
        return receipt

    if host != "Windows":
        return hold("HOLD_WINDOWS_HOST_REQUIRED")
    if not sdk_root:
        return hold("HOLD_GDK_SDK_ROOT_NOT_FOUND")
    root = Path(sdk_root)
    if not _absolute_non_unc(root):
        return hold("HOLD_GDK_SDK_ROOT_PATH_INVALID")
    if not root.is_dir():
        return hold("HOLD_GDK_SDK_ROOT_NOT_FOUND")
    if _is_reparse_point(root):
        return hold("HOLD_GDK_SDK_ROOT_REPARSE_POINT")

    if makepkg_path is None:
        candidates = _discover_makepkg(root)
        if not candidates:
            return hold("HOLD_MAKEPKG_NOT_FOUND")
        if len(candidates) != 1:
            return hold("HOLD_MAKEPKG_CANDIDATES_AMBIGUOUS")
        makepkg = candidates[0]
    else:
        makepkg = Path(makepkg_path)
        if not _absolute_non_unc(makepkg):
            return hold("HOLD_MAKEPKG_PATH_INVALID")
        if not makepkg.is_file():
            return hold("HOLD_MAKEPKG_NOT_FOUND")
    if not _is_descendant_without_reparse(root, makepkg):
        return hold("HOLD_MAKEPKG_PATH_UNTRUSTED")

    try:
        makepkg_evidence = _component_evidence(makepkg, version_reader, signature_reader)
    except Exception as exc:
        return hold("HOLD_MAKEPKG_METADATA_UNAVAILABLE", type(exc).__name__ + ":" + str(exc))
    receipt["makepkg"] = makepkg_evidence
    if not _microsoft_signed(makepkg_evidence):
        return hold("HOLD_MAKEPKG_SIGNATURE_NOT_MICROSOFT_VALID")
    actual_version = makepkg_evidence.get("effective_version")
    if not isinstance(actual_version, str) or not VERSION_RE.fullmatch(actual_version):
        return hold("HOLD_MAKEPKG_VERSION_UNAVAILABLE")

    validator = _find_submission_validator(root, makepkg)
    if validator is None:
        return hold("HOLD_SUBMISSION_VALIDATOR_MISSING")
    if not _is_descendant_without_reparse(root, validator):
        return hold("HOLD_SUBMISSION_VALIDATOR_PATH_UNTRUSTED")
    try:
        validator_evidence = _component_evidence(validator, version_reader, signature_reader)
    except Exception as exc:
        return hold("HOLD_SUBMISSION_VALIDATOR_METADATA_UNAVAILABLE", type(exc).__name__ + ":" + str(exc))
    receipt["submission_validator"] = validator_evidence
    if not _microsoft_signed(validator_evidence):
        return hold("HOLD_SUBMISSION_VALIDATOR_SIGNATURE_NOT_MICROSOFT_VALID")

    if not expected_version:
        return hold("HOLD_GDK_SDK_VERSION_NOT_APPROVED")
    if not VERSION_RE.fullmatch(expected_version):
        return hold("HOLD_EXPECTED_GDK_SDK_VERSION_INVALID")
    if actual_version != expected_version:
        return hold("HOLD_GDK_SDK_VERSION_MISMATCH")
    receipt["status"] = "PASS_TOOLCHAIN_CAPABILITY_ONLY"
    return receipt


def discover_root(environment: dict | None = None) -> tuple[Path | None, str]:
    env = environment if environment is not None else os.environ
    gamedk = env.get("GameDK") or env.get("GAMEDK")
    if gamedk:
        return Path(gamedk), "GAMEDK_ENVIRONMENT"
    program_files_x86 = env.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    return Path(program_files_x86) / "Microsoft GDK", "DOCUMENTED_DEFAULT_INSTALL_ROOT"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root")
    parser.add_argument("--makepkg-path")
    parser.add_argument("--expected-version", default=os.environ.get("EXPECTED_GDK_SDK_VERSION", ""))
    parser.add_argument("--output", type=Path, default=Path("evidence/gdk-sdk-capability.json"))
    args = parser.parse_args(argv)

    if args.sdk_root:
        root, root_source = Path(args.sdk_root), "EXPLICIT_ARGUMENT"
    else:
        root, root_source = discover_root()
    receipt = probe(
        root,
        makepkg_path=args.makepkg_path,
        expected_version=args.expected_version,
        root_source=root_source,
        workflow_head_sha=os.environ.get("GITHUB_SHA"),
        build_run_id=os.environ.get("GITHUB_RUN_ID"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as output:
            output.write("gdk_sdk_capability_status=" + receipt["status"] + "\n")
    print(json.dumps({
        "status": receipt["status"],
        "host_os": receipt["host_os"],
        "makepkg_executed": receipt["makepkg_executed"],
        "sdk_validation_executed": receipt["sdk_validation_executed"],
        "package_built": receipt["package_built"],
        "physical_gui_verified": receipt["physical_gui_verified"],
    }))
    # Missing or unapproved SDK is an evidence HOLD, not a reason to stop the cloud build.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
