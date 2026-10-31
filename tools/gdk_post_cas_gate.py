"""Signal Sprint only: verify a Provisioner GDK post-CAS intake before SDK build.

Read-only. This does not execute CAS, build an MSIXVC, or submit to Store.
The Provisioner intake is untrusted input; recheck the Git chain and exact
pinned EXE artifact rather than trusting its PASS-like status.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

SOURCE_SHA = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST_ID = "game-signal-sprint-" + SOURCE_SHA
SOURCE_REPO = "shihuiarenjinba-png/AI-Game-Factory"
SOURCE_BRANCH = "codex/game-signal-sprint-undo-20261027"
ARTIFACT_SHA = "e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412"
EXE_SHA = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
APPROVED_PATH = "products/signal-sprint/store/approved-identity.json"
IDENTITY = {
    "store_id": "9N21MJM7S57P",
    "name": "OkinawaDesktopTools.SignalSprint",
    "publisher": "CN=46263F21-A700-41DB-8C9B-114C22FB82FC",
    "publisher_display_name": "Okinawa Desktop Tools",
    "package_family_name": "OkinawaDesktopTools.SignalSprint_j8yefg9jgfh58",
    "package_sid": "S-1-15-2-1437967488-3265478925-1925977903-994526844-2895000717-1943620661-378024715",
    "xbox_title_id": "68721417",
    "xbox_scid": "00000000-0000-0000-0000-000068721417",
    "msa_app_id": "39852fc3-fa46-4bda-88aa-b35385488ced",
}
APPROVED_FIELDS = {
    "schema_version", "reviewed", "request_id", "product_type", "slug",
    "source_factory", "source_repository", "source_branch", "source_sha",
    "verified_source_sha", "package_sha256", "package_family_name",
    "package_sid", "signature_status", "store_id", "name", "publisher",
    "source", "identity_source", "provided_at", "packaging_family",
    "publisher_display_name", "xbox_title_id", "xbox_scid", "msa_app_id",
}
INTAKE_FIELDS = {
    "schema_version", "status", "next_stage", "packaging_family",
    "package_format", "request_id", "source_repository", "source_branch",
    "source_sha", "cas_commit_sha", "factory_head_sha", "identity",
    "pinned_exe", "package_version", "real_msixvc_built", "store_submitted",
}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
BUILD_BRANCH = re.compile(r"codex/game-signal-sprint-gdk-build-[a-z0-9][a-z0-9-]{0,79}\Z")


class GateHold(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise GateHold(reason)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def parse_json(data: bytes) -> dict:
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeError, ValueError) as exc:
        raise GateHold("invalid JSON input") from exc
    require(type(obj) is dict, "JSON root must be object")
    return obj


def reject_redirected_path(path: Path, label: str) -> None:
    """Fail closed for symlink/junction ancestors as well as the leaf.

    A clean leaf under a redirected parent is not trusted provenance. These
    checks are repeated after reading; they do not replace trusted storage
    against concurrent filesystem races.
    """
    for component in (path, *path.parents):
        try:
            linked = component.is_symlink()
            junction = getattr(component, "is_junction", lambda: False)()
        except (OSError, RuntimeError) as exc:
            raise GateHold(label + " path cannot be inspected") from exc
        require(not linked and not junction, label + " contains linked path component")


def load_json(path: Path) -> dict:
    reject_redirected_path(path, "Provisioner intake")
    require(path.is_file(), "missing or non-file JSON input")
    before = path.stat()
    require(0 < before.st_size <= 65536, "missing or oversized JSON input")
    raw = path.read_bytes()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and
            len(raw) == before.st_size,
            "Provisioner intake changed during read")
    reject_redirected_path(path, "Provisioner intake")
    return parse_json(raw)


def git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateHold("Git verification unavailable") from exc
    require(proc.returncode == 0, "Git verification failed: " + args[0])
    return proc.stdout.decode("utf-8").strip()


def changed_paths(repo: Path, commit: str) -> list[str]:
    """Read NUL-delimited literal Git names; quoted display paths are unsafe.

    Without -z, Git quotes non-ASCII/control characters and a leading quote
    can conceal a products/ prefix from the immutable-history guard.
    """
    raw = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-z", "-r", commit)
    require(not raw or raw.endswith("\x00"), "malformed Git changed-path inventory")
    names = raw[:-1].split("\x00") if raw else []
    require(all(names), "empty Git changed-path entry")
    return names


def check_git(repo: Path, cas: str, build: str) -> dict:
    require(repo.is_dir() and (repo / ".git").exists(), "Factory Git checkout missing")
    require(bool(SHA40.fullmatch(cas)) and bool(SHA40.fullmatch(build))
            and cas != SOURCE_SHA and build != SOURCE_SHA, "invalid CAS/build SHA")
    require(git(repo, "rev-parse", "refs/heads/" + SOURCE_BRANCH) == SOURCE_SHA,
            "immutable source branch moved")
    require(git(repo, "rev-parse", "HEAD") == build, "build HEAD mismatch")
    require(git(repo, "status", "--porcelain", "--untracked-files=all") == "", "build checkout is dirty")
    branch = git(repo, "symbolic-ref", "--short", "HEAD")
    require(bool(BUILD_BRANCH.fullmatch(branch)), "not a dedicated GDK build branch")
    cas_ref = "refs/heads/codex/game-signal-sprint-gdk-cas-" + SOURCE_SHA[:12]
    build_ref = "refs/heads/" + branch
    require(git(repo, "rev-parse", cas_ref) == cas, "dedicated CAS branch ref mismatch")
    require(git(repo, "rev-parse", build_ref) == build, "dedicated build branch ref mismatch")
    require(git(repo, "rev-list", "--parents", "-n", "1", cas).split() == [cas, SOURCE_SHA],
            "CAS must be single-parent child of immutable source")
    git(repo, "merge-base", "--is-ancestor", cas, build)
    require(changed_paths(repo, cas) == [APPROVED_PATH],
            "CAS changed non-Identity files")
    approved = parse_json(git(repo, "show", cas + ":" + APPROVED_PATH).encode())
    require(set(approved) == APPROVED_FIELDS, "approved Identity schema differs")
    expected = {"schema_version": "1.0", "reviewed": True,
                "request_id": REQUEST_ID, "product_type": "GAME", "slug": "signal-sprint",
                "source_factory": "AI-Game-Factory", "source_repository": SOURCE_REPO,
                "source_branch": SOURCE_BRANCH, "source_sha": SOURCE_SHA,
                "verified_source_sha": SOURCE_SHA, "package_sha256": EXE_SHA,
                "source": "partner_center_user_provided",
                "identity_source": "USER_PROVIDED_PARTNER_CENTER", "packaging_family": "GDK"}
    expected.update(IDENTITY)
    for key, value in expected.items():
        require(type(approved.get(key)) is type(value) and approved[key] == value,
                "approved Identity mismatch: " + key)
    require(type(approved.get("signature_status")) is str and
            approved["signature_status"] == "QA_UNSIGNED",
            "pinned EXE signature provenance must remain QA_UNSIGNED")
    require(isinstance(approved.get("provided_at"), str) and bool(re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)",
            approved["provided_at"])), "missing Identity provenance timestamp")
    require(git(repo, "rev-parse", cas + ":" + APPROVED_PATH) ==
            git(repo, "rev-parse", build + ":" + APPROVED_PATH),
            "post-CAS Identity bytes changed")
    require(parse_json(git(repo, "show", build + ":" + APPROVED_PATH).encode()) == approved,
            "post-CAS Identity modified")
    # Reject every intermediate change to product bytes, including a later revert.
    commits = git(repo, "rev-list", "--reverse", cas + ".." + build).splitlines()
    for commit in commits:
        parents = git(repo, "rev-list", "--parents", "-n", "1", commit).split()
        require(len(parents) == 2, "post-CAS merge commit requires review")
        for name in changed_paths(repo, commit):
            require(not name.startswith("products/") and name != APPROVED_PATH,
                    "post-CAS product change in history")
    # Re-read refs and checkout after history checks to reject stale receipts.
    require(git(repo, "rev-parse", "refs/heads/" + SOURCE_BRANCH) == SOURCE_SHA,
            "immutable source branch moved during verification")
    require(git(repo, "rev-parse", cas_ref) == cas,
            "dedicated CAS branch moved during verification")
    require(git(repo, "rev-parse", build_ref) == build and
            git(repo, "rev-parse", "HEAD") == build and
            git(repo, "symbolic-ref", "--short", "HEAD") == branch,
            "dedicated build branch moved during verification")
    require(git(repo, "status", "--porcelain", "--untracked-files=all") == "",
            "build checkout changed during verification")
    return {"branch": branch, "cas_commit_sha": cas, "factory_head_sha": build}


def check_artifact(path: Path) -> dict:
    reject_redirected_path(path, "Pinned EXE artifact")
    require(path.is_file() and 0 < path.stat().st_size < 100_000_000,
            "pinned EXE artifact unavailable")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ARTIFACT_SHA,
            "pinned ZIP SHA-256 mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            require(len(members) == 3 and {m.filename for m in members} == {
                "SignalSprint.exe", "provenance.json", "provisioner-request.json"},
                "pinned ZIP member set mismatch")
            for m in members:
                require(not m.is_dir() and m.file_size <= 40_000_000 and
                        not (m.create_system == 3 and
                             (m.external_attr >> 16) & 0o170000 == 0o120000),
                        "unsafe ZIP member")
            require(archive.testzip() is None, "pinned ZIP CRC mismatch")
            exe = archive.read("SignalSprint.exe")
            provenance = parse_json(archive.read("provenance.json"))
            request = parse_json(archive.read("provisioner-request.json"))
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as exc:
        raise GateHold("invalid pinned ZIP") from exc
    # Parse the same snapshot that was hashed; reject path replacement races.
    reject_redirected_path(path, "Pinned EXE artifact")
    require(path.is_file() and
            hashlib.sha256(path.read_bytes()).hexdigest() == ARTIFACT_SHA,
            "pinned ZIP changed during verification")
    reject_redirected_path(path, "Pinned EXE artifact")
    require(hashlib.sha256(exe).hexdigest() == EXE_SHA, "pinned EXE SHA mismatch")
    for record in (provenance, request):
        for key, expected in {"request_id": REQUEST_ID, "source_sha": SOURCE_SHA,
                              "source_repository": SOURCE_REPO,
                              "source_branch": SOURCE_BRANCH, "product_type": "GAME",
                              "slug": "signal-sprint"}.items():
            require(record.get(key) == expected, "artifact provenance mismatch: " + key)
    require(provenance.get("artifact_kind") == "EXE_QA_UNSIGNED" and
            provenance.get("executable_sha256") == EXE_SHA and
            provenance.get("executable") == "SignalSprint.exe" and
            request.get("dry_run") is True, "artifact provenance contract mismatch")
    return {"artifact_zip_sha256": ARTIFACT_SHA, "executable_sha256": EXE_SHA,
            "executable_bytes": len(exe), "executable": "SignalSprint.exe"}


def verify(repo: Path, intake_file: Path, artifact_file: Path) -> dict:
    intake = load_json(intake_file)
    require(set(intake) == INTAKE_FIELDS, "unexpected Provisioner intake schema")
    expected = {"schema_version": 1, "status": "GDK_BUILD_INPUT_CHECK_ONLY",
                "next_stage": "BUILD_GDK_MSIXVC_FROM_PINNED_EXE",
                "packaging_family": "GDK", "package_format": "MSIXVC_OR_MSIXVC2",
                "request_id": REQUEST_ID, "source_repository": SOURCE_REPO,
                "source_branch": SOURCE_BRANCH, "source_sha": SOURCE_SHA,
                "package_version": None, "real_msixvc_built": False,
                "store_submitted": False, "identity": IDENTITY}
    for key, value in expected.items():
        require(type(intake.get(key)) is type(value) and intake[key] == value,
                "Provisioner intake mismatch: " + key)
    chain = check_git(repo, intake["cas_commit_sha"], intake["factory_head_sha"])
    pinned = check_artifact(artifact_file)
    require(intake["pinned_exe"] == pinned,
            "Provisioner intake references different artifact bytes")
    return {"schema_version": 1, "status": "GDK_FACTORY_POST_CAS_CHECK_ONLY",
            "next_stage": "GDK_SDK_BUILD_PENDING", "packaging_family": "GDK",
            "request_id": REQUEST_ID, "source_sha": SOURCE_SHA,
            "source_repository": SOURCE_REPO, **chain, "pinned_exe": pinned,
            "package_version": None, "real_msixvc_built": False,
            "store_submitted": False, "windows_e2e_pass": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory-checkout", type=Path, required=True)
    parser.add_argument("--provisioner-intake", type=Path, required=True)
    parser.add_argument("--pinned-artifact-zip", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args.factory_checkout, args.provisioner_intake,
                        args.pinned_artifact_zip)
    except (GateHold, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc),
                          "next_stage": "REVIEW_GDK_POST_CAS_INPUT"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
