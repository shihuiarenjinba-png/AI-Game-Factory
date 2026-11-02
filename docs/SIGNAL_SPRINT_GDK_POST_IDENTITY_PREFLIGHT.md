# Signal Sprint GDK post-Identity product preflight — check-only

This is a **read-only GAME-owned** check against the exact public Provisioner-game Draft PR #53 commit `ac4bd6d4fed975dae139a6638b0b7f78e09e6d71`. It does not execute Provisioner code, CAS, the GDK SDK, MakePkg, signing, Store, or any central ledger operation. The Partner Center product is **GDK game**, never generic MSIX.

Immutable source: `c058cbf7fe38e02d929c67d047d717ff74bd522e`. Original request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`. The previously received Identity is not requested again.

## Execute offline (expected exit code 2 = HOLD)

Use a local read-only checkout of PR #53 at the exact SHA:

```bash
python qa/signal_sprint_gdk_post_identity_preflight.py \
  --provisioner-checkout /path/to/PR53-exact-checkout \
  --output evidence/gdk-post-identity-preflight.json
```

Optional evidence inputs (none are synthesized): `--identity-json`, `--version-json`, `--staging-dir`, `--asset-hashes-json`, `--makepkg-path`, `--trusted-makepkg-sha256`, `--cas-sha`, `--build-sha`, `--sdk-result-json`, and `--signing-json`.

The version review JSON is exactly `{"package_version":"A.B.C.0","reviewed":true,"request_id":"game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e","source_sha":"c058cbf7fe38e02d929c67d047d717ff74bd522e"}`, replacing `A.B.C.0` with a separately reviewed actual version. This file **alone is not authorization**. The asset hash JSON maps each of the exact six GDK staging filenames to independently reviewed SHA-256 digests. A complete local manifest is only a byte snapshot, not a full PNG decode or artistic approval.

The output has one gate and a specific HOLD reason for each of: source/request/route, Identity exact fields, actual CAS/build Git provenance, Version review, six staging files/four PNGs, Windows SDK toolchain, SDK validation, signing, MSIXVC2 bytes, and physical human QA. Valid source/Identity/Version/hash records can be `CHECK_ONLY`, never `READY`. Overall status and process exit remain `HOLD` / 2. The CI expects this exact outcome and uploads the JSON as part of the Windows GUI evidence Artifact.

**Do not substitute** the current GUI QA EXE (Artifact #13175054438 or later) for the pinned original GDK executable `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`. The original GDK ZIP SHA is `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`. Those bytes, an independently verified Identity-only CAS, reviewed Version and artwork, Windows GDK SDK/toolchain, signing validation, and actual MSIXVC2 build are separate downstream prerequisites.

Physical Windows JA/EN × OS DPI 100/125/150 and first-time human QA remain HOLD. Windows Code Integrity restrictions must not be bypassed. Only GAME product QA changes are allowed; do not modify original source/request, Provisioner, 36 central ledger, main/release, merge, Store or CAS.
