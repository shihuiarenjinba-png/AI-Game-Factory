# Signal Sprint current-artifact physical Windows QA (check-only)

This is the **new** immutable review EXE from GitHub Actions run **41525954534** (build HEAD `15b666871eb6749133df671ca1b271d89ecdf3ae`), NOT the older pinned physical protocol. Neither EXE is a GDK package, approved CAS replacement, or MSIXVC2.

| Binding | Pinned value |
|---|---|
| CI executed EXE Artifact | 13180405918 |
| GUI screenshot Artifact | 13180545199 |
| Executed EXE SHA-256 | `6d63ff1a09386e7c1203827a4707893b2e93c025aca5bf6f6976edf04d4396e8` |
| EXE length | 11,446,063 bytes |
| INNER `SignalSprint-physical-qa.zip` SHA-256 | `08d9e565058275c4283a8975ec200ec7357f4b024b60e7b39edfd94b971060e3` |
| Immutable original source | `c058cbf7fe38e02d929c67d047d717ff74bd522e` |
| Original request | `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e` |
| Route | `GDK_GAME` / `GDK game` |
| GitHub artifact expiration | 2026-11-16 21:13 UTC |

Download Artifact 13180405918 from the GitHub Actions run, extract its **outer** archive and retain the **inner** `SignalSprint-physical-qa.zip` without modification. Before running the EXE, inspect:

```powershell
python qa/signal_sprint_current_artifact_physical_qa.py --mode inspect --bundle .\SignalSprint-physical-qa.zip --output .\qa-inspect.json
```

This intentionally emits `PHYSICAL_HOLD` (exit 2) even when the archive is valid: no real PC session has been performed. It also rejects a changed ZIP, old QA EXE, old GDK EXE, mismatched source/request/HEAD, corrupt screenshots, and false release gates. It never launches the EXE or changes Windows security settings.

For each of the six physical sessions (JA/EN × 100/125/150% **real OS DPI**) use the exact bundled EXE on a **1024×768 desktop with visible taskbar and 1024×720 usable area**. A human unfamiliar with the game must try to understand purpose/controls/retry within 30 seconds. Capture full-desktop PNGs at **initial**, **after all 30 moves are exhausted (lost)**, **after R retry and one move (replay)**, and **after closing and reopening the same EXE (restart)**. Record the human answers including `restart_state_reset_confirmed` and `same_exe_through_all_phases`; never fabricate answers. Ensure Code Integrity allows execution without bypassing protection.

Example recording after actual physical observations, with `answers.json` containing the existing ten human QA answers plus the two restart answers:

```powershell
python qa/signal_sprint_current_artifact_physical_qa.py --mode record --bundle .\SignalSprint-physical-qa.zip --output .\ja125.json --language ja --target-dpi 125 --answers .\answers.json --screenshot-root .\shots --screenshot-initial .\shots\ja125-initial.png --screenshot-lost .\shots\ja125-lost.png --screenshot-replay .\shots\ja125-replay.png --screenshot-restart .\shots\ja125-restart.png
```

The runner reads the actual Windows OS DPI, window bounds, running EXE path/SHA and screenshot hashes; it does not change DPI, launch an EXE, or automate human answers. Record only when the actual game window is visible and the matching EXE is running. An individual session can only be `SESSION_HUMAN_REVIEW_REQUIRED`, never `SALE_READY`.

After collecting six independently recorded sessions:

```powershell
python qa/signal_sprint_current_artifact_physical_qa.py --mode aggregate --bundle .\SignalSprint-physical-qa.zip --output .\physical-summary.json --screenshot-root .\shots --sessions .\ja100.json .\ja125.json .\ja150.json .\en100.json .\en125.json .\en150.json
```

Missing sessions, screenshots, true OS DPI, a fully visible work area, SHA binding, or human responses yield `PHYSICAL_HOLD`. Even a complete consistent submission only yields `HUMAN_EVIDENCE_REVIEW_REQUIRED`: human answers and screen captures are not cryptographically attested. The independent reviewer must verify the evidence before any physical QA judgment. **Formal CAS, approved GDK assets/version, SDK/toolchain, signing and MSIXVC2 are separate HOLD gates.** Never promote the review EXE into a package or use ordinary MSIX as a replacement.
