# Signal Sprint: two real QA EXE lineages (check-only)

Read-only verification of **two different QA revisions** from the GitHub Actions archives downloaded on 2026-11-03 JST. These are **not** GDK package EXEs or MSIXVC2 builds. The original immutable source `c058cbf7fe38e02d929c67d047d717ff74bd522e` and request `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e` remain unchanged. Partner Center route remains `GDK_GAME` / `GDK game`.

| Binding | PR17 pinned physical protocol | PR18 new CI artifact |
|---|---|---|
| CI run | 41525954534 | 41536644056 |
| Build HEAD | `15b666871eb6749133df671ca1b271d89ecdf3ae` | `6ce4a9b47b55d865c33c7e0a50ffb18f5219c138` |
| QA EXE Artifact | 13180405918 | 13185196046 |
| GUI Artifact | 13180545199 | 13185220900 |
| Outer GitHub ZIP SHA-256 | `b3a57f479b987a6b32ea52bc3ba00fdd97cfc49ba06cc6f4771f257d8da0b78b` | `8fa5f5aad0f63abedc43b9c057f5ebb2c1e0350b0bf29055edda21cca797925a` |
| Inner QA ZIP SHA-256 | `08d9e565058275c4283a8975ec200ec7357f4b024b60e7b39edfd94b971060e3` | `7842e1f79770339629270562730b80443e202caf7bd5ad1bdd32047c10c7cddb` |
| Actual SignalSprint.exe SHA-256 | `6d63ff1a09386e7c1203827a4707893b2e93c025aca5bf6f6976edf04d4396e8` | `352b198c40fe5888af41047bd897e4357327c296691ccb77c7dae6a691da7a86` |
| Actual EXE length | 11,446,063 | 11,445,323 |

**Measured conclusion: DISTINCT_EXE_REVISIONS_VERIFIED.** Outer ZIPs were independently downloaded and their SHA-256 digests, nested ZIP CRCs, manifests, screenshot receipts and actual EXE bytes checked. The outer digest is **not** the EXE SHA; the original source SHA is **not** either build HEAD. Do not substitute the new artifact into the pinned PR17 protocol, and do not label it as the older EXE.

For local check-only re-verification, supply both downloaded *outer* GitHub Artifact ZIP files:

```sh
python qa/signal_sprint_dual_artifact_lineage.py --pinned pinned-13180405918.zip --candidate candidate-13185196046.zip --output dual-artifact-lineage.json
```

The validator requires exact outer and inner hashes, distinct run/HEAD, original source/request/route, byte-level EXE SHA and length, all screenshot hashes and the GUI initial/lost/replay phase hashes, release-gate HOLDs, real DPI 125/150 HOLD and UIAutomation text HOLD. A wrong archive, stale GDK EXE, ZIP CRC corruption, forged release PASS, or swapped GUI receipt yields `LINEAGE_HOLD` and exit 2. Synthetic negative fixtures never count as physical evidence. CI on Windows and Ubuntu re-downloads both exact artifacts and emits only a comparison receipt; it does not run EXEs.

**Physical Windows JA/EN × DPI 100/125/150 remains PHYSICAL_HOLD.** Initial 30 seconds, 30-move loss, R retry, restart and text clipping still require genuine human/OS evidence; no synthetic result may fill these gaps. Existing PR18 physical runbook remains pinned to Artifact 13180405918. Code Integrity bypass is forbidden. Approved GDK Version, four assets / six staging files, CAS, GDK SDK, signing, MSIXVC2 and sale readiness remain separate HOLD gates. Identity was already received; do not request it again.

Artifacts expire on 2026-11-16 UTC. After expiry, new CI runs must report unavailable evidence/HOLD rather than silently replacing either archive or manufacturing PASS. This is not a release/publish authorization.
