# Signal Sprint physical Windows QA — SHA-bound, read-only protocol

This procedure tests the GUI-executed EXE from stacked Draft PR #17, **not** the GDK package EXE. Never convert the Partner Center route from **GDK game** to ordinary MSIX, or interpret a successful QA receipt as CAS, GDK SDK, MSIXVC2, Store, or SALE_READY.

## Pinned source of truth

- Immutable source: c058cbf7fe38e02d929c67d047d717ff74bd522e (unchanged)
- Original request: game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e (unchanged)
- GUI build HEAD: 6f072dcf5369f7e56e235f7641d602e4fafc3417
- GUI workflow run: 41489911241
- QA Artifact: https://github.com/shihuiarenjinba-png/AI-Game-Factory/actions/runs/41489911241/artifacts/13164091404
- Exact SignalSprint.exe SHA-256: 95695560d524e70def41afa2de81eb9cf07f51862d40b9d5cef8624b528e4ea1
- Exact EXE length: 11,446,006 bytes
- Old GDK EXE SHA starts 9c31c363 and is not the physical GUI QA EXE.
- GitHub artifact expiry: 2026-11-16 17:20 UTC / 2026-11-17 02:20 JST. Obtain the original before expiry.

## On the physical Windows PC

1. Download GitHub Artifact #13164091404 and extract its outer ZIP into a dedicated QA directory. It contains the inner SignalSprint-physical-qa.zip. From the PR #17 branch, use Python 3.12 and Pillow==11.3.0. Do not install MSIX, change Code Integrity, disable antivirus/SmartScreen, or bypass enterprise security.
2. Verify the **inner** ZIP before extraction. In PowerShell:

    python qa/signal_sprint_physical_pc_qa.py --mode inspect --bundle .\qa-download\SignalSprint-physical-qa.zip --output .\qa-results\bundle-inspect.json

   Expected status: BUNDLE_CHECK_ONLY_PHYSICAL_QA_HOLD, meaning integrity checked but human QA still HOLD. Any hash, CRC, EXE, screenshot, run, or HEAD mismatch returns HOLD and exit code 2.
3. Extract the inner ZIP to a separate folder. Independently verify SignalSprint.exe SHA-256 and file length above. Launch it normally only if Windows security policy allows. If Code Integrity refuses the EXE, stop and record HOLD; **never bypass** security.
4. Set display resolution to **1024×768** using Windows Settings. Separately test **100%, 125%, 150%** actual OS display scaling. Test **EN and JP** at each scaling, for six distinct sessions. The QA script never changes OS DPI or display settings.
5. For each language/DPI, have a first-time human tester identify the goal, controls, and R-retry action within 30 seconds. Play to the 30-move loss, press R, make another move, check text/buttons and ask whether they would replay. Capture three **distinct unedited full-desktop 1024×768 PNGs** for each session: initial, lost, replay. Do not reuse images between sessions.
6. For each session, prepare answers JSON with every field a true/false boolean (false means failed or unverified):

    {
      "independent_first_time_tester": true,
      "purpose_understood_in_30s": true,
      "controls_understood_in_30s": true,
      "retry_understood_in_30s": true,
      "state_text_fully_visible": true,
      "controls_operable": true,
      "lost_after_30_moves": true,
      "r_retry_restarts": true,
      "replay_after_retry": true,
      "would_replay": true,
      "code_integrity_blocked": false
    }

   These are illustrative values, **not actual test results**. A tester must supply their own truthful observations.
7. Keep the exact Signal Sprint | JP or Signal Sprint | EN game window open. Record the JA/125% session (repeat with each language and DPI):

    python qa/signal_sprint_physical_pc_qa.py --mode record --bundle .\qa-download\SignalSprint-physical-qa.zip --language ja --target-dpi 125 --answers .\qa-results\answers-ja-125.json --screenshot-root .\qa-results\screenshots --screenshot-initial .\qa-results\screenshots\ja-125-initial.png --screenshot-lost .\qa-results\screenshots\ja-125-lost.png --screenshot-replay .\qa-results\screenshots\ja-125-replay.png --output .\qa-results\ja-125.json

   The script reads Windows system DPI, actual taskbar-excluding work area, game window rectangle, and **running process EXE SHA/length** using Windows APIs. It never starts the EXE. If the window is absent, policy blocks launch, OS DPI differs, EXE differs, or text/controls fail, status is HOLD. Otherwise the result is SESSION_HUMAN_REVIEW_REQUIRED, **never PASS**.
8. Aggregate all six session JSON files:

    python qa/signal_sprint_physical_pc_qa.py --mode aggregate --bundle .\qa-download\SignalSprint-physical-qa.zip --screenshot-root .\qa-results\screenshots --sessions .\qa-results\ja-100.json .\qa-results\en-100.json .\qa-results\ja-125.json .\qa-results\en-125.json .\qa-results\ja-150.json .\qa-results\en-150.json --output .\qa-results\physical-qa-summary.json

   Missing 125%/150% sessions, duplicate screenshot, forged release PASS, wrong EXE, Code Integrity refusal, or game window outside the work area produces HOLD. Even a complete matrix yields PHYSICAL_HUMAN_QA_EVIDENCE_REVIEW_REQUIRED, not Store certification.

## Limitations and ownership

The receipt binds GitHub Artifact ID, original request, immutable source, build HEAD, workflow run, EXE SHA/size, observed Windows DPI, live process path hash, window geometry, human answers and three screenshot hashes per session. Human claims and screenshots are not cryptographically attested by Windows and require independent review. No physical QA has been performed by adding this code. Until actual evidence arrives, physical 125%/150%, human QA, approved GDK assets, Version, CAS, SDK and MSIXVC2 remain HOLD.

Only GAME product QA files may change. Do not change the fixed game core/source, original request, Provisioner-game, 36 central ledger, other lanes, main/release, merge, force push, Store or CAS.
