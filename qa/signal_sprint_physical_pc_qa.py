"""Physical Windows first-30-second QA. Read-only: NEVER a GDK package gate."""
import argparse
import ctypes
import hashlib
import json
import platform
import zipfile
from pathlib import Path

ARTIFACT_ID = 13164091404
RUN = "41489911241"
HEAD = "6f072dcf5369f7e56e235f7641d602e4fafc3417"
SOURCE = "c058cbf7fe38e02d929c67d047d717ff74bd522e"
REQUEST = "game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e"
EXE_SHA = "95695560d524e70def41afa2de81eb9cf07f51862d40b9d5cef8624b528e4ea1"
EXE_SIZE = 11446006
QUESTIONS = ("independent_first_time_tester", "purpose_understood_in_30s",
             "controls_understood_in_30s", "retry_understood_in_30s",
             "state_text_fully_visible", "controls_operable",
             "lost_after_30_moves", "r_retry_restarts",
             "replay_after_retry", "would_replay")
MATRIX = {(lang, dpi) for lang in ("ja", "en") for dpi in (100, 125, 150)}
RELEASE = ("sale_ready", "cas_return_pass", "gdk_sdk_validated",
           "msixvc2_built", "store_submitted", "approved_gdk_package_exe")


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def lineage():
    return dict(artifact_id=ARTIFACT_ID, workflow_run_id=RUN,
                build_head_sha=HEAD, immutable_source_sha=SOURCE,
                original_request_id=REQUEST, exe_sha256=EXE_SHA,
                exe_size_bytes=EXE_SIZE, partner_center_route="GDK game",
                package_format="NOT_A_GDK_PACKAGE")


def bundle_errors(bundle):
    try:
        from signal_sprint_physical_qa_bundle import verify_real
        errors = list(verify_real(Path(bundle), HEAD, RUN))
        if errors:
            return errors
        with zipfile.ZipFile(bundle) as z:
            manifest = json.loads(z.read("manifest.json"))
            exe_size = z.getinfo("SignalSprint.exe").file_size
        for key, value in lineage().items():
            if key == "artifact_id":
                continue
            if manifest.get(key) != value:
                errors.append("BUNDLE_PIN_MISMATCH_" + key)
        if exe_size != EXE_SIZE:
            errors.append("BUNDLE_EXE_SIZE_MISMATCH")
        return sorted(set(errors))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile) as exc:
        return ["BUNDLE_UNVERIFIABLE_" + type(exc).__name__]


def observe(language):
    """Read Windows OS DPI, window rectangle and actual running EXE; never launch it."""
    if platform.system() != "Windows":
        raise RuntimeError("PHYSICAL_WINDOWS_REQUIRED")
    from ctypes import wintypes
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    u.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    u.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    u.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    u.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
    if u.GetAwarenessFromDpiAwarenessContext(u.GetThreadDpiAwarenessContext()) != 2:
        raise RuntimeError("DPI_AWARENESS_UNVERIFIED")
    u.GetDpiForSystem.restype = ctypes.c_uint
    raw_dpi = int(u.GetDpiForSystem())
    u.GetSystemMetrics.argtypes = [ctypes.c_int]
    u.GetSystemMetrics.restype = ctypes.c_int
    screen = [0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1)]
    class Rect(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
    def coords(r):
        return [r.left, r.top, r.right, r.bottom]
    area = Rect()
    u.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint,
                                        ctypes.c_void_p, ctypes.c_uint]
    u.SystemParametersInfoW.restype = wintypes.BOOL
    if not u.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
        raise RuntimeError("OS_WORKAREA_UNREADABLE")
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowW.restype = wintypes.HWND
    hwnd = u.FindWindowW(None, "Signal Sprint | " + ("JP" if language == "ja" else "EN"))
    if not hwnd:
        raise RuntimeError("GAME_WINDOW_ABSENT_OR_CODE_INTEGRITY_BLOCKED")
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.IsWindowVisible.restype = wintypes.BOOL
    u.IsIconic.argtypes = [wintypes.HWND]
    u.IsIconic.restype = wintypes.BOOL
    if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
        raise RuntimeError("GAME_WINDOW_HIDDEN")
    window = Rect()
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(Rect)]
    u.GetWindowRect.restype = wintypes.BOOL
    if not u.GetWindowRect(hwnd, ctypes.byref(window)):
        raise RuntimeError("WINDOW_BOUNDS_UNREADABLE")
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    handle = k.OpenProcess(0x1000, False, pid.value)
    if not handle:
        raise RuntimeError("GAME_PROCESS_ACCESS_HOLD")
    try:
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if not k.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            raise RuntimeError("RUNNING_EXE_PATH_UNREADABLE")
        exe = Path(path.value)
        exe_sha, exe_size = digest(exe), exe.stat().st_size
    finally:
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.CloseHandle(handle)
    if exe_sha != EXE_SHA or exe_size != EXE_SIZE:
        raise RuntimeError("RUNNING_EXE_NOT_EXACT_QA_ARTIFACT")
    return dict(source="windows-user32-live", raw_dpi=raw_dpi,
                os_dpi_percent=round(raw_dpi * 100 / 96),
                screen_bounds=screen, work_area_bounds=coords(area),
                window_bounds=coords(window), running_exe_sha256=exe_sha,
                running_exe_size_bytes=exe_size)


def check_session(s, root):
    errors = []
    if not isinstance(s, dict):
        return ["SESSION_NOT_OBJECT"]
    for key, value in lineage().items():
        if s.get(key) != value:
            errors.append("LINEAGE_" + key)
    key = (s.get("language"), s.get("target_dpi_percent"))
    if key not in MATRIX:
        errors.append("LANGUAGE_OR_DPI_INVALID")
    obs = s.get("os_observation")
    if not isinstance(obs, dict):
        obs = {}
    if obs.get("source") != "windows-user32-live":
        errors.append("LIVE_WINDOWS_OBSERVATION_MISSING")
    if (obs.get("raw_dpi") != {100: 96, 125: 120, 150: 144}.get(s.get("target_dpi_percent"))
            or obs.get("os_dpi_percent") != s.get("target_dpi_percent")):
        errors.append("ACTUAL_OS_DPI_MISMATCH")
    def rect(v):
        return (isinstance(v, list) and len(v) == 4 and
                all(type(x) is int for x in v) and v[0] < v[2] and v[1] < v[3])
    screen, area, window = (obs.get("screen_bounds"), obs.get("work_area_bounds"),
                            obs.get("window_bounds"))
    if screen != [0, 0, 1024, 768]:
        errors.append("SCREEN_NOT_1024X768")
    if not rect(screen) or not rect(area) or not (
            screen[0] <= area[0] < area[2] <= screen[2] and
            screen[1] <= area[1] < area[3] <= screen[3]):
        errors.append("WORKAREA_INVALID")
    if not rect(area) or not rect(window) or not (
            area[0] <= window[0] < window[2] <= area[2] and
            area[1] <= window[1] < window[3] <= area[3]):
        errors.append("WINDOW_OVERLAPS_TASKBAR_OR_OUTSIDE_WORKAREA")
    if obs.get("running_exe_sha256") != EXE_SHA or obs.get("running_exe_size_bytes") != EXE_SIZE:
        errors.append("RUNNING_EXE_WRONG")
    if s.get("code_integrity_blocked") is not False:
        errors.append("CODE_INTEGRITY_HOLD")
    if s.get("status") != "SESSION_HUMAN_REVIEW_REQUIRED":
        errors.append("SESSION_STATUS_FALSE_PASS")
    answers = s.get("human_answers")
    if not isinstance(answers, dict) or any(answers.get(k) is not True for k in QUESTIONS):
        errors.append("HUMAN_FIRST30_OR_REPLAY_HOLD")
    if s.get("release_gates") != {k: False for k in RELEASE}:
        errors.append("FORGED_RELEASE_GATE")
    shots = s.get("screenshots")
    if not isinstance(shots, dict) or set(shots) != {"initial", "lost", "replay"}:
        errors.append("THREE_SCREENSHOTS_REQUIRED")
    else:
        names = set()
        for shot in shots.values():
            if not isinstance(shot, dict):
                errors.append("SCREENSHOT_METADATA_INVALID")
                continue
            name = shot.get("path")
            if (not isinstance(name, str) or not name or Path(name).is_absolute()
                    or ".." in Path(name).parts or name in names):
                errors.append("SCREENSHOT_PATH_INVALID_OR_REUSED")
                continue
            names.add(name)
            file = root / name
            try:
                if (not file.is_file() or file.is_symlink() or file.stat().st_size > 20000000
                        or digest(file) != shot.get("sha256")):
                    errors.append("SCREENSHOT_MISSING_OR_TAMPERED")
                else:
                    from PIL import Image
                    with Image.open(file) as im:
                        if im.format != "PNG" or im.size != (1024, 768):
                            errors.append("SCREENSHOT_NOT_FULL_DESKTOP_PNG")
                        im.verify()
            except (OSError, ValueError, SyntaxError):
                errors.append("SCREENSHOT_INVALID")
    return sorted(set(errors))


def aggregate(sessions, root):
    errors, seen, shots = [], set(), set()
    for session in sessions:
        if not isinstance(session, dict):
            errors.append("SESSION_NOT_OBJECT")
            continue
        key = (session.get("language"), session.get("target_dpi_percent"))
        if key in seen:
            errors.append("DUPLICATE_SESSION")
        seen.add(key)
        errors += check_session(session, root)
        for item in (session.get("screenshots") or {}).values():
            sha = item.get("sha256") if isinstance(item, dict) else None
            if sha in shots:
                errors.append("SCREENSHOT_REUSED_BETWEEN_SESSIONS")
            shots.add(sha)
    if seen != MATRIX:
        errors.append("INCOMPLETE_JA_EN_100_125_150")
    errors = sorted(set(errors))
    return {**lineage(), "status": "HOLD" if errors else "PHYSICAL_HUMAN_QA_EVIDENCE_REVIEW_REQUIRED",
            "errors": errors, "sessions": len(sessions), "physical_qa_certified": False,
            "sale_ready": False, "gdk_sdk_validated": False, "msixvc2_built": False,
            "limitations": ["Human observations are not cryptographically attested",
                            "QA EXE is NOT approved GDK EXE", "No Code Integrity bypass"]}


def read_json(path):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ValueError("DUPLICATE_JSON_KEY")
            out[k] = v
        return out
    if path.stat().st_size > 200000:
        raise ValueError("JSON_OVERSIZED")
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", required=True, choices=("inspect", "record", "aggregate"))
    p.add_argument("--bundle", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--language", choices=("ja", "en"))
    p.add_argument("--target-dpi", type=int, choices=(100, 125, 150))
    p.add_argument("--answers", type=Path)
    p.add_argument("--screenshot-root", type=Path)
    for phase in ("initial", "lost", "replay"):
        p.add_argument("--screenshot-" + phase, type=Path)
    p.add_argument("--sessions", nargs="*", type=Path)
    a = p.parse_args()
    report = {**lineage(), "status": "HOLD", "errors": []}
    try:
        errors = bundle_errors(a.bundle)
        if errors:
            report["errors"] = errors
        elif a.mode == "inspect":
            report["status"] = "BUNDLE_CHECK_ONLY_PHYSICAL_QA_HOLD"
        elif a.mode == "record":
            if not all((a.language, a.target_dpi, a.answers, a.screenshot_root,
                        a.screenshot_initial, a.screenshot_lost, a.screenshot_replay)):
                raise ValueError("RECORD_ARGUMENTS_MISSING")
            root = a.screenshot_root.resolve(strict=True)
            obs = observe(a.language)
            answers = read_json(a.answers)
            shots = {}
            for phase in ("initial", "lost", "replay"):
                path = getattr(a, "screenshot_" + phase).resolve(strict=True)
                shots[phase] = {"path": path.relative_to(root).as_posix(),
                                "sha256": digest(path)}
            report = {**lineage(), "language": a.language,
                      "target_dpi_percent": a.target_dpi, "os_observation": obs,
                      "screenshots": shots, "code_integrity_blocked": answers.get("code_integrity_blocked"),
                      "human_answers": {k: answers.get(k) for k in QUESTIONS},
                      "release_gates": {k: False for k in RELEASE},
                      "status": "SESSION_HUMAN_REVIEW_REQUIRED"}
            report["errors"] = check_session(report, root)
            if report["errors"]:
                report["status"] = "HOLD"
        else:
            if not a.sessions or not a.screenshot_root:
                raise ValueError("AGGREGATE_ARGUMENTS_MISSING")
            report = aggregate([read_json(f) for f in a.sessions], a.screenshot_root)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        report = {**lineage(), "status": "HOLD",
                  "errors": [type(exc).__name__ + ": " + str(exc)],
                  "sale_ready": False, "msixvc2_built": False}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "errors": report["errors"]}))
    return 2 if report["status"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
