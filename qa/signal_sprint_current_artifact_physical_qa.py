"""Read-only physical Windows QA for the exact PR17 CI #41525954534 EXE.

This module deliberately does not launch executables, change DPI, bypass Code
Integrity, build GDK packages, perform CAS, or claim physical QA PASS.
"""
import argparse
import importlib.util
import hashlib
import json
import sys
import zipfile
from pathlib import Path

# Load an isolated copy so this profile NEVER mutates the old pinned protocol
# when both test modules are imported in the same unittest process.
_spec = importlib.util.spec_from_file_location(
    "_signal_sprint_current_artifact_base",
    Path(__file__).with_name("signal_sprint_physical_pc_qa.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

# Dedicated isolated profile; original module remains untouched.
base.ARTIFACT_ID = 13180405918
base.RUN = "41525954534"
base.HEAD = "15b666871eb6749133df671ca1b271d89ecdf3ae"
base.EXE_SHA = "6d63ff1a09386e7c1203827a4707893b2e93c025aca5bf6f6976edf04d4396e8"
base.EXE_SIZE = 11446063
INNER_ZIP_SHA = "08d9e565058275c4283a8975ec200ec7357f4b024b60e7b39edfd94b971060e3"
GUI_ARTIFACT_ID = 13180545199
OLD_QA_EXE_SHA = "95695560d524e70def41afa2de81eb9cf07f51862d40b9d5cef8624b528e4ea1"
OLD_GDK_EXE_SHA = "9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad"
EXTRA_ANSWERS = ("restart_state_reset_confirmed", "same_exe_through_all_phases")
PHASES = ("initial", "lost", "replay", "restart")


def bundle_errors(bundle):
    try:
        if base.digest(bundle) != INNER_ZIP_SHA:
            return ["CURRENT_QA_ARTIFACT_ZIP_SHA_MISMATCH"]
        errors = base.bundle_errors(bundle)
        if errors:
            return errors
        with zipfile.ZipFile(bundle) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("exe_sha256") in (OLD_QA_EXE_SHA, OLD_GDK_EXE_SHA):
                return ["LEGACY_OR_GDK_EXE_SUBSTITUTION"]
            if manifest.get("exe_sha256") != base.EXE_SHA:
                return ["CURRENT_QA_EXE_SHA_MISMATCH"]
        return []
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile) as exc:
        return ["BUNDLE_UNREADABLE_" + type(exc).__name__]


def extended_errors(session, root):
    if not isinstance(session, dict):
        return ["SESSION_NOT_OBJECT"]
    shots = session.get("screenshots")
    if not isinstance(shots, dict) or set(shots) != set(PHASES):
        return ["FOUR_PHASE_SCREENSHOTS_REQUIRED"]
    base_session = dict(session)
    base_session["screenshots"] = {key: shots[key] for key in PHASES[:3]}
    errors = base.check_session(base_session, root)
    restart = shots["restart"]
    if not isinstance(restart, dict):
        return sorted(set(errors + ["RESTART_SCREENSHOT_INVALID"]))
    path = restart.get("path")
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        errors.append("RESTART_SCREENSHOT_PATH_INVALID")
    else:
        try:
            root = Path(root).resolve(strict=True)
            candidate = root / path
            if candidate.is_symlink():
                return sorted(set(errors + ["RESTART_SCREENSHOT_UNSAFE"]))
            f = candidate.resolve(strict=True)
            if not f.is_relative_to(root) or f.stat().st_size > 20000000:
                errors.append("RESTART_SCREENSHOT_UNSAFE")
            elif base.digest(f) != restart.get("sha256"):
                errors.append("RESTART_SCREENSHOT_TAMPERED")
            else:
                from PIL import Image
                with Image.open(f) as im:
                    if im.format != "PNG" or im.size != (1024, 768):
                        errors.append("RESTART_SCREENSHOT_NOT_FULL_DESKTOP")
                    im.verify()
        except (OSError, ValueError, SyntaxError):
            errors.append("RESTART_SCREENSHOT_MISSING_OR_INVALID")
    if restart.get("sha256") in {shots[k].get("sha256") for k in PHASES[:3] if isinstance(shots[k], dict)}:
        errors.append("RESTART_SCREENSHOT_REUSED")
    answers = session.get("human_answers")
    if not isinstance(answers, dict) or any(answers.get(k) is not True for k in EXTRA_ANSWERS):
        errors.append("RESTART_HUMAN_EVIDENCE_HOLD")
    if session.get("gui_artifact_id") != GUI_ARTIFACT_ID:
        errors.append("GUI_ARTIFACT_BINDING_MISMATCH")
    if session.get("physical_qa_certified") is not False:
        errors.append("PHYSICAL_CERTIFICATION_FALSE_PASS")
    return sorted(set(errors))


def aggregate(sessions, root):
    errors = []
    base_sessions = []
    seen_screenshot_sha = set()
    for s in sessions:
        errors.extend(extended_errors(s, root))
        if isinstance(s, dict) and isinstance(s.get("screenshots"), dict):
            for shot in s["screenshots"].values():
                sha = shot.get("sha256") if isinstance(shot, dict) else None
                if not sha or sha in seen_screenshot_sha:
                    errors.append("REUSED_OR_MISSING_SCREENSHOT_BETWEEN_PHASES_OR_SESSIONS")
                seen_screenshot_sha.add(sha)
        if isinstance(s, dict) and isinstance(s.get("screenshots"), dict):
            t = dict(s)
            t["screenshots"] = {k: s["screenshots"][k] for k in PHASES[:3] if k in s["screenshots"]}
            base_sessions.append(t)
    if len(base_sessions) != len(sessions):
        errors.append("SESSION_INVALID")
    old = base.aggregate(base_sessions, root)
    errors.extend(old["errors"])
    # All synthetic/locally submitted human observations remain untrusted until independent review.
    return {**base.lineage(), "gui_artifact_id": GUI_ARTIFACT_ID,
            "status": "PHYSICAL_HOLD" if errors else "HUMAN_EVIDENCE_REVIEW_REQUIRED",
            "errors": sorted(set(errors)), "sessions": len(sessions),
            "physical_qa_certified": False, "sale_ready": False,
            "gdk_package_ready": False, "msixvc2_built": False,
            "limitations": ["Human answers and screenshots are not cryptographically attested",
                            "Physical OS DPI must be observed, not simulated",
                            "QA EXE is NOT a GDK package EXE"]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=("inspect", "record", "aggregate"))
    p.add_argument("--bundle", required=True, type=Path, help="INNER SignalSprint-physical-qa.zip, not the GitHub outer ZIP")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--language", choices=("ja", "en"))
    p.add_argument("--target-dpi", type=int, choices=(100, 125, 150))
    p.add_argument("--answers", type=Path)
    p.add_argument("--screenshot-root", type=Path)
    p.add_argument("--sessions", nargs="*", type=Path)
    for phase in PHASES:
        p.add_argument("--screenshot-" + phase, type=Path)
    a = p.parse_args(argv)
    report = {**base.lineage(), "gui_artifact_id": GUI_ARTIFACT_ID,
              "status": "PHYSICAL_HOLD", "errors": [], "physical_qa_certified": False,
              "sale_ready": False, "gdk_package_ready": False, "msixvc2_built": False}
    try:
        errors = bundle_errors(a.bundle)
        if errors:
            report["errors"] = errors
        elif a.mode == "inspect":
            report["errors"] = ["PHYSICAL_WINDOWS_HUMAN_QA_NOT_PERFORMED"]
        elif a.mode == "record":
            if not all((a.language, a.target_dpi, a.answers, a.screenshot_root,
                        *(getattr(a, "screenshot_" + phase) for phase in PHASES))):
                raise ValueError("RECORD_ARGUMENTS_MISSING")
            root = a.screenshot_root.resolve(strict=True)
            answers = base.read_json(a.answers)
            obs = base.observe(a.language)  # real Windows only; does not launch EXE
            shots = {}
            for phase in PHASES:
                f = getattr(a, "screenshot_" + phase).resolve(strict=True)
                shots[phase] = {"path": f.relative_to(root).as_posix(), "sha256": base.digest(f)}
            report.update(language=a.language, target_dpi_percent=a.target_dpi,
                          os_observation=obs, screenshots=shots,
                          code_integrity_blocked=answers.get("code_integrity_blocked"),
                          human_answers={k: answers.get(k) for k in (*base.QUESTIONS, *EXTRA_ANSWERS)},
                          release_gates={k: False for k in base.RELEASE},
                          status="SESSION_HUMAN_REVIEW_REQUIRED")
            report["errors"] = extended_errors(report, root)
            if report["errors"]:
                report["status"] = "PHYSICAL_HOLD"
        else:
            if not a.sessions or not a.screenshot_root:
                raise ValueError("AGGREGATE_ARGUMENTS_MISSING")
            report = aggregate([base.read_json(s) for s in a.sessions], a.screenshot_root)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        report["errors"] = [type(exc).__name__ + ": " + str(exc)]
        report["status"] = "PHYSICAL_HOLD"
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"status": report["status"], "errors": report["errors"]}, ensure_ascii=False))
    return 2 if report["status"] == "PHYSICAL_HOLD" else 0


if __name__ == "__main__":
    sys.exit(main())
