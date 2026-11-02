"""Fail-closed contract for independent first-30-second human QA.

A valid PLAN is never a human PASS. The pinned GitHub GUI artifact is evidence/
only; it does not contain the Windows EXE. A human observation needs byte-identical
EXE and screenshots independently verified against the pinned run receipt.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

FIXTURE = Path(__file__).with_name("signal_sprint_first30_human_fixture.json")
IMMUTABLE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
HEAD = "8e6a8c10a2678b76a2eddc897e5fea8cf7d5dc98"
RUN = "41470116296"
ARTIFACT = "13154872780"
SCREEN_FIELDS = {
    "en_initial": ("signal-sprint-en-window-initial.png", "en_window_sha256"),
    "jp_initial": ("signal-sprint-jp-window-initial.png", "jp_window_sha256"),
    "en_lost": ("signal-sprint-en-turn-30-expected-lost.png", "en_exhausted_window_sha256"),
    "jp_lost": ("signal-sprint-jp-turn-30-expected-lost.png", "exhausted_window_sha256"),
    "en_replay": ("signal-sprint-en-after-lost-replay-right.png", "en_replay_window_sha256"),
    "jp_replay": ("signal-sprint-jp-after-lost-replay-right.png", "replay_window_sha256"),
}
STEPS = ("blind_start", "en_initial", "jp_initial", "bounds",
         "en_loss_replay", "jp_loss_replay", "negative_cases", "consumer_value")
NEGATIVES = ("WRONG_GUI_EXE_SHA", "OLD_IMMUTABLE_ARTIFACT_SUBSTITUTED",
             "WINDOW_OVER_TASKBAR", "SCREENSHOT_SHA_CHANGED", "MISSING_JP_GLYPH",
             "MISSING_EN_STATUS", "UNRESPONSIVE_R", "PROMPTED_30_SECOND_ANSWER",
             "FALSE_DPI_125_150_PASS", "ORDINARY_MSIX_ROUTE",
             "UNAPPROVED_GDK_ASSET_VERSION_SDK_PASS")
SHA = re.compile(r"^[0-9a-f]{64}$")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_fixture(f):
    errors = []
    def check(ok, name):
        if not ok:
            errors.append(name)
    check(f.get("schema_version") == 1, "SCHEMA")
    check(f.get("registration") == "GDK_GAME" and f.get("partner_center_route") == "GDK game", "GDK_ROUTE")
    check(f.get("immutable_source_sha") == IMMUTABLE, "IMMUTABLE_DRIFT")
    check(f.get("pinned_revision_sha") == HEAD and f.get("pinned_revision_sha") != IMMUTABLE, "REVISION_DRIFT")
    check(f.get("pinned_windows_run_id") == RUN and f.get("pinned_artifact_id") == ARTIFACT, "ARTIFACT_DRIFT")
    check(f.get("artifact_url") == "https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/" + RUN + "/artifacts/" + ARTIFACT, "ARTIFACT_URL")
    check(f.get("evidence_kind") == "HUMAN_FIRST_30_SECONDS_QA_PLAN_NOT_EXECUTED", "FALSE_HUMAN_EVIDENCE")
    check(f.get("source_receipt") == "evidence/ui-revision-receipt.json", "RECEIPT_SOURCE")
    check(f.get("exe_sha256_binding") == "read_full_64_hex_from_source_receipt_and_hash_actual_exe", "EXE_SHA_NOT_BOUND")
    check("EVIDENCE_ONLY" in f.get("exe_availability", ""), "EXE_AVAILABILITY_NOT_DISCLOSED")
    d = f.get("reference_display", {})
    check(d.get("monitor") == [0, 0, 1024, 768] and d.get("work_area") == [0, 0, 1024, 720]
          and d.get("window") == [16, 16, 932, 675], "WINDOW_GEOMETRY")
    check(d.get("measured_os_dpi_percent") == 100 and
          d.get("dpi_125") == "HOLD_NOT_PHYSICALLY_MEASURED" and
          d.get("dpi_150") == "HOLD_NOT_PHYSICALLY_MEASURED", "FALSE_DPI_PASS")
    screens = f.get("screenshots", {})
    check(set(screens) == set(SCREEN_FIELDS), "SCREEN_SET")
    for key, (name, field) in SCREEN_FIELDS.items():
        entry = screens.get(key, {})
        check(entry.get("file") == name and entry.get("sha_receipt_field") == field
              and bool(entry.get("expected_visible")), "SCREEN_CONTRACT_" + key)
    steps = f.get("steps", [])
    check([s.get("id") for s in steps] == list(STEPS), "HUMAN_STEP_SEQUENCE")
    for s in steps:
        check(all(s.get(k) for k in ("instruction", "pass_if", "fail_if")), "STEP_MISSING_EXPECTATION_" + str(s.get("id")))
    check(set(f.get("negative_cases", [])) == set(NEGATIVES), "NEGATIVE_CASES")
    template = f.get("human_observation_template", {})
    check(template.get("status") == "HOLD_NOT_EXECUTED" and
          template.get("human_qa_pass") is False and template.get("sale_ready") is False, "FALSE_HUMAN_PASS")
    check(all(value is False for value in f.get("release_gates", {}).values()) and
          len(f.get("release_gates", {})) == 7, "FALSE_RELEASE_GATE")
    return errors


def validate_observation(f, obs, receipt=None, screenshots=None, exe=None):
    errors = validate_fixture(f)
    if obs is None:
        return errors, "HOLD_HUMAN_NOT_EXECUTED"
    if not isinstance(obs, dict):
        return errors + ["OBSERVATION_INVALID"], "HOLD"
    if receipt is None or screenshots is None or exe is None:
        return errors + ["PINNED_REAL_EXE_AND_SCREENSHOT_RECEIPT_REQUIRED"], "HOLD"
    for key, expected in (("revision_sha", HEAD), ("workflow_run_id", RUN),
                          ("immutable_source_sha", IMMUTABLE), ("registration", "GDK_GAME")):
        if str(receipt.get(key)) != expected:
            errors.append("SOURCE_RECEIPT_MISMATCH_" + key)
    digest = receipt.get("exe_sha256")
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        errors.append("SOURCE_EXE_SHA_INVALID")
    try:
        if not exe.is_file() or sha256(exe) != digest or exe.stat().st_size != receipt.get("exe_size_bytes"):
            errors.append("REAL_EXE_BYTES_MISMATCH")
    except OSError:
        errors.append("REAL_EXE_UNREADABLE")
    for key, (filename, field) in SCREEN_FIELDS.items():
        try:
            if sha256(screenshots / filename) != receipt.get(field):
                errors.append("SCREENSHOT_SHA_MISMATCH_" + key)
        except OSError:
            errors.append("SCREENSHOT_UNREADABLE_" + key)
    if obs.get("status") != "HUMAN_REPORTED_CHECK_ONLY" or obs.get("sale_ready") is not False:
        errors.append("FORBIDDEN_HUMAN_CERTIFICATION")
    if obs.get("exe_sha256") != digest or obs.get("pinned_revision_sha") != HEAD or str(obs.get("pinned_run_id")) != RUN:
        errors.append("HUMAN_EVIDENCE_LINEAGE_MISMATCH")
    if not obs.get("independent_first_time_tester") or not obs.get("tester") or not obs.get("device") or not obs.get("performed_at"):
        errors.append("INDEPENDENT_HUMAN_OBSERVATION_MISSING")
    if obs.get("os_dpi_percent") != 100 or obs.get("dpi_125") != "HOLD" or obs.get("dpi_150") != "HOLD":
        errors.append("PHYSICAL_DPI_UNVERIFIED")
    if not obs.get("verbatim_first30") or not obs.get("verbatim_replay_reason"):
        errors.append("FIRST30_OR_REPLAY_VALUE_NOT_DOCUMENTED")
    if set(obs.get("step_results", {})) != set(STEPS) or any(v != "PASS_HUMAN_OBSERVED" for v in obs.get("step_results", {}).values()):
        errors.append("HUMAN_STEPS_INCOMPLETE")
    if set(obs.get("negative_results", {})) != set(NEGATIVES) or any(v != "REJECTED_OR_OBSERVED" for v in obs.get("negative_results", {}).values()):
        errors.append("NEGATIVE_CASES_UNVERIFIED")
    return errors, "HUMAN_REPORTED_CHECK_ONLY_NOT_SALE_READY" if not errors else "HOLD"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--observation", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--exe", type=Path)
    args = parser.parse_args()
    try:
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        observation = json.loads(args.observation.read_text(encoding="utf-8")) if args.observation else None
        receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig")) if args.receipt else None
        errors, status = validate_observation(fixture, observation, receipt, args.screenshots, args.exe)
    except (OSError, ValueError, TypeError) as exc:
        errors, status = ["INPUT_UNREADABLE_" + type(exc).__name__], "HOLD"
    print(json.dumps({"status": status, "errors": errors, "human_qa_pass": False,
                      "sale_ready": False, "real_os_dpi_125_150": "HOLD"}, ensure_ascii=False))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
