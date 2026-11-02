"""Read-only Signal Sprint GDK post-Identity preflight.

No local JSON can authorize CAS, GDK SDK, signing, MSIXVC2, or Store.
Provisioner PR53 is parsed as data; its code is never imported or executed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import stat
import struct

from signal_sprint_gdk_review_gate import (
    ASSETS, IMMUTABLE, PINNED_EXE, PINNED_REQUEST, PR53_SHA, ROUTE,
    _assigned, _parse, load_pr53_contract,
)

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
VERSION = re.compile(r"(0|[1-9][0-9]{0,4})(?:\.(0|[1-9][0-9]{0,4})){2}\.0\Z")
MAX_FILE = {"SignalSprint.exe": 40_000_000, "MicrosoftGame.config": 1_000_000,
            **{name: 20_000_000 for name, _ in ASSETS.values()}}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _regular(path: Path, limit: int):
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError("LINKED_EVIDENCE_PATH")
    if not path.exists() or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("EVIDENCE_FILE_MISSING")
    if not 0 < path.stat().st_size <= limit:
        raise ValueError("EVIDENCE_FILE_SIZE_INVALID")


def _json(path: Path):
    _regular(path, 65536)
    result = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique)
    if type(result) is not dict:
        raise ValueError("EVIDENCE_JSON_NOT_OBJECT")
    return result


def _sha(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hold(gates, name, reason, **details):
    gates[name] = {"status": "HOLD", "reason": reason, **details}


def _check(gates, name, reason, **details):
    gates[name] = {"status": "CHECK_ONLY", "reason": reason, **details}


def _identity_expected(pr53: Path):
    identity = _assigned(_parse(pr53 / "package_identity_provisioner.py"),
                         "PINNED_SIGNAL_SPRINT_GDK_IDENTITY")
    required = {"store_id", "name", "publisher", "publisher_display_name",
                "package_family_name", "package_sid", "xbox_title_id", "xbox_scid", "msa_app_id"}
    if type(identity) is not dict or set(identity) != required or not all(
            type(v) is str and v for v in identity.values()):
        raise ValueError("PINNED_IDENTITY_CONTRACT_INVALID")
    return identity


def _inventory(root: Path, approved_hashes):
    if root.is_symlink() or getattr(root, "is_junction", lambda: False)() or not root.is_dir():
        raise ValueError("STAGING_DIRECTORY_MISSING_OR_LINKED")
    for parent in root.parents:
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise ValueError("STAGING_DIRECTORY_LINKED_ANCESTOR")
    entries = list(root.iterdir())
    if len(entries) != len(MAX_FILE) or {p.name for p in entries} != set(MAX_FILE):
        raise ValueError("GDK_SIX_FILE_INVENTORY_INCOMPLETE_OR_EXTRA")
    hashes = {}
    for path in entries:
        _regular(path, MAX_FILE[path.name])
        hashes[path.name] = _sha(path)
        if path.suffix.lower() == ".png":
            with path.open("rb") as stream:
                header = stream.read(24)
            if (len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n"
                    or header[12:16] != b"IHDR"):
                raise ValueError("GDK_ASSET_NOT_PNG_" + path.name)
            expected = next(dims for name, dims in ASSETS.values() if name == path.name)
            if struct.unpack(">II", header[16:24]) != expected:
                raise ValueError("GDK_ASSET_DIMENSIONS_MISMATCH_" + path.name)
    if hashes["SignalSprint.exe"] != PINNED_EXE:
        raise ValueError("REVIEW_GUI_EXE_IS_NOT_PINNED_GDK_EXE")
    if approved_hashes is None:
        raise ValueError("APPROVED_STAGING_SHA_MANIFEST_MISSING")
    if set(approved_hashes) != set(MAX_FILE) or any(
            type(v) is not str or not SHA256.fullmatch(v) for v in approved_hashes.values()):
        raise ValueError("APPROVED_STAGING_SHA_MANIFEST_INVALID")
    if hashes != approved_hashes:
        raise ValueError("STAGING_BYTES_DIFFER_FROM_REVIEWED_HASHES")
    return hashes


def assess(pr53: Path, *, identity_json=None, version_json=None, staging_dir=None,
           asset_hashes_json=None, makepkg_path=None, trusted_makepkg_sha256=None,
           cas_sha=None, build_sha=None, sdk_result_json=None, signing_json=None):
    gates = {}
    try:
        contract = load_pr53_contract(pr53)
        if (contract["provisioner_head_sha"] != PR53_SHA or
                contract["source_sha"] != IMMUTABLE or
                contract["pinned_request_id"] != PINNED_REQUEST or
                contract["routing"] != ROUTE or contract["registration"] != "GDK_GAME"):
            raise ValueError("PINNED_SOURCE_REQUEST_ROUTE_MISMATCH")
        expected_identity = _identity_expected(pr53)
        _check(gates, "source_request_route", "PR53_PINNED_CONTRACT_READ_ONLY")
    except (ValueError, OSError, TypeError, KeyError) as exc:
        _hold(gates, "source_request_route", "SOURCE_REQUEST_ROUTE_CONTRACT_INVALID", detail=str(exc))
        expected_identity = None

    if expected_identity is None:
        _hold(gates, "identity", "PINNED_IDENTITY_SOURCE_UNVERIFIED")
    elif identity_json is None:
        _hold(gates, "identity", "APPROVED_IDENTITY_FILE_NOT_SUPPLIED_CAS_UNVERIFIED")
    else:
        try:
            identity = _json(Path(identity_json))
            if identity.get("source_sha") != IMMUTABLE or identity.get("request_id") != PINNED_REQUEST:
                raise ValueError("IDENTITY_SOURCE_REQUEST_MISMATCH")
            if identity.get("packaging_family") != "GDK" or identity.get("source") != "partner_center_user_provided":
                raise ValueError("IDENTITY_GDK_ROUTE_OR_PROVENANCE_MISMATCH")
            for key, expected in expected_identity.items():
                if type(identity.get(key)) is not str or identity[key] != expected:
                    raise ValueError("IDENTITY_EXACT_FIELD_MISMATCH_" + key)
            if "package_version" in identity or "version" in identity:
                raise ValueError("IDENTITY_MUST_NOT_SUPPLY_PACKAGE_VERSION")
            _check(gates, "identity", "IDENTITY_FIELDS_MATCH_PINNED_REVIEW_CAS_STILL_HOLD")
        except (ValueError, OSError, UnicodeError) as exc:
            _hold(gates, "identity", "IDENTITY_EVIDENCE_REJECTED", detail=str(exc))

    if cas_sha is None or build_sha is None:
        _hold(gates, "cas", "ACTUAL_IDENTITY_ONLY_CAS_AND_POST_CAS_BUILD_NOT_VERIFIED")
    elif (type(cas_sha) is not str or not SHA40.fullmatch(cas_sha) or
          type(build_sha) is not str or not SHA40.fullmatch(build_sha) or
          cas_sha == IMMUTABLE or build_sha == IMMUTABLE):
        _hold(gates, "cas", "CAS_OR_BUILD_SHA_INVALID")
    else:
        _hold(gates, "cas", "CAS_SHA_SUPPLIED_BUT_GIT_PARENT_AND_IDENTITY_BLOB_NOT_VERIFIED")

    if version_json is None:
        _hold(gates, "version", "EXPLICIT_APPROVED_GDK_PACKAGE_VERSION_MISSING")
    else:
        try:
            review = _json(Path(version_json))
            if (set(review) != {"package_version", "reviewed", "request_id", "source_sha"} or
                    type(review["reviewed"]) is not bool or not review["reviewed"] or
                    review["source_sha"] != IMMUTABLE or review["request_id"] != PINNED_REQUEST or
                    type(review["package_version"]) is not str or
                    not VERSION.fullmatch(review["package_version"])):
                raise ValueError("VERSION_APPROVAL_BINDING_INVALID")
            _check(gates, "version", "VERSION_REVIEW_RECORD_ONLY_NOT_INDEPENDENT_APPROVAL",
                   package_version=review["package_version"])
        except (ValueError, OSError, UnicodeError, KeyError) as exc:
            _hold(gates, "version", "VERSION_REVIEW_REJECTED", detail=str(exc))

    if staging_dir is None:
        _hold(gates, "assets_and_staging", "SIX_REAL_GDK_STAGING_FILES_NOT_SUPPLIED")
    else:
        try:
            hashes = _json(Path(asset_hashes_json)) if asset_hashes_json is not None else None
            checked = _inventory(Path(staging_dir), hashes)
            _check(gates, "assets_and_staging",
                   "SIX_FILE_HASHES_CHECK_ONLY_PNG_FULL_VALIDATION_AND_ART_REVIEW_PENDING",
                   sha256=checked)
        except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
            _hold(gates, "assets_and_staging", "GDK_STAGING_REJECTED", detail=str(exc))

    if platform.system() != "Windows":
        _hold(gates, "sdk_toolchain", "GDK_SDK_WINDOWS_HOST_REQUIRED")
    elif makepkg_path is None or trusted_makepkg_sha256 is None:
        _hold(gates, "sdk_toolchain", "MAKEPKG_EXE_AND_INDEPENDENT_APPROVED_SHA_MISSING")
    else:
        try:
            path = Path(makepkg_path)
            if not path.is_absolute() or not SHA256.fullmatch(str(trusted_makepkg_sha256)):
                raise ValueError("MAKEPKG_PATH_OR_TRUSTED_SHA_INVALID")
            _regular(path, 100_000_000)
            if path.name.casefold() != "makepkg.exe" or _sha(path) != trusted_makepkg_sha256:
                raise ValueError("MAKEPKG_BYTES_OR_FILENAME_MISMATCH")
            _check(gates, "sdk_toolchain", "MAKEPKG_BYTES_CHECK_ONLY_SDK_NOT_EXECUTED")
        except (ValueError, OSError) as exc:
            _hold(gates, "sdk_toolchain", "MAKEPKG_TOOLCHAIN_REJECTED", detail=str(exc))

    if sdk_result_json is None:
        _hold(gates, "sdk_validation", "OFFICIAL_GDK_SDK_VALIDATION_NOT_EXECUTED_OR_EVIDENCED")
    else:
        try:
            value = _json(Path(sdk_result_json))
            _hold(gates, "sdk_validation", "UNTRUSTED_SDK_RESULT_CANNOT_CLAIM_PASS"
                  if value.get("gdk_sdk_validated") is True or value.get("real_msixvc_built") is True
                  else "SDK_RESULT_NOT_INDEPENDENTLY_AUTHENTICATED")
        except (ValueError, OSError, UnicodeError) as exc:
            _hold(gates, "sdk_validation", "SDK_RESULT_EVIDENCE_REJECTED", detail=str(exc))

    if signing_json is None:
        _hold(gates, "signing", "GDK_SIGNING_REVIEW_OR_VALID_SIGNATURE_EVIDENCE_MISSING")
    else:
        try:
            value = _json(Path(signing_json))
            _hold(gates, "signing", "UNTRUSTED_SIGNING_JSON_NOT_SIGNATURE_VERIFICATION"
                  if value.get("signed") is True or value.get("signature_valid") is True
                  else "SIGNED_GDK_PACKAGE_NOT_VERIFIED")
        except (ValueError, OSError, UnicodeError) as exc:
            _hold(gates, "signing", "SIGNING_EVIDENCE_REJECTED", detail=str(exc))

    _hold(gates, "msixvc2", "REAL_MSIXVC2_BUILD_AND_BYTES_NOT_VERIFIED")
    _hold(gates, "physical_human_qa", "JA_EN_DPI_125_150_AND_FIRST30_PHYSICAL_HUMAN_QA_NOT_VERIFIED")
    return {
        "schema_version": 1, "status": "HOLD", "product": "Signal Sprint",
        "partner_center_selection": "GDK_GAME", "packaging_family": "GDK",
        "immutable_source_sha": IMMUTABLE, "request_id": PINNED_REQUEST,
        "provisioner_pr53_sha": PR53_SHA, "gates": gates,
        "missing_or_rejected": [name + ":" + gate["reason"]
                               for name, gate in gates.items() if gate["status"] == "HOLD"],
        "cas_return_pass": False, "gdk_sdk_validated": False,
        "msixvc2_built": False, "sale_ready": False, "store_submitted": False,
        "limitations": ["CHECK_ONLY_NEVER_GDK_PACKAGE_APPROVAL",
                        "REVIEW_GUI_EXE_NEVER_SUBSTITUTES_PINNED_GDK_EXE",
                        "NO_PROVISIONER_CODE_EXECUTED", "NO_STORE_OR_CAS_WRITE"],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provisioner-checkout", type=Path, required=True)
    for option in ("identity-json", "version-json", "staging-dir", "asset-hashes-json",
                   "makepkg-path", "trusted-makepkg-sha256", "cas-sha", "build-sha",
                   "sdk-result-json", "signing-json"):
        p.add_argument("--" + option)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    result = assess(a.provisioner_checkout, identity_json=a.identity_json,
                    version_json=a.version_json, staging_dir=a.staging_dir,
                    asset_hashes_json=a.asset_hashes_json, makepkg_path=a.makepkg_path,
                    trusted_makepkg_sha256=a.trusted_makepkg_sha256,
                    cas_sha=a.cas_sha, build_sha=a.build_sha,
                    sdk_result_json=a.sdk_result_json, signing_json=a.signing_json)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(json.dumps({"status": result["status"], "missing_or_rejected": result["missing_or_rejected"]}))
    return 2  # A check-only preflight is never a packaging or Store authorization.


if __name__ == "__main__":
    raise SystemExit(main())
