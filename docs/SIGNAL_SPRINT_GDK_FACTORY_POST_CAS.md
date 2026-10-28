# Signal Sprint: Factory GDK post-CAS check-only gate

**Partner Center selection: GDK game.** This is not the generic MSIX handoff (`tools/msix_handoff.py`) and does not generate or submit a package. No new game is generated.

## Fixed source and artifact

- Factory: `shihuiarenjinba-png/AI-Game-Factory`
- Immutable source branch: `codex/game-signal-sprint-undo-20261027`
- Immutable source SHA: `c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Request ID: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Factory EXE artifact ID: `12706862577`; ZIP SHA-256 `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`
- Inner `SignalSprint.exe` SHA-256: `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad`
- GitHub Actions artifact expiry: **2026-11-01 03:18:51 UTC**. Preserve the exact ZIP bytes before expiry; a new build with different bytes is **not** a substitute.

## Operation (only after explicit, approved CAS)

1. Run `Repository-Provisioner-game/gdk_build_intake.py` check-only against the dedicated post-CAS Factory GDK build checkout and the exact pinned artifact ZIP. Save its machine-readable JSON stdout to a file **outside the checkout**.
2. On the same checkout run:

```bash
python tools/gdk_post_cas_gate.py \
  --factory-checkout /path/to/AI-Game-Factory-gdk-build \
  --provisioner-intake /path/to/provisioner-gdk-build-intake.json \
  --pinned-artifact-zip /path/to/signal-sprint-factory-exe-c058cbf7.zip
```

3. Expect `status=GDK_FACTORY_POST_CAS_CHECK_ONLY`, `next_stage=GDK_SDK_BUILD_PENDING`, `package_version=null`, and all real-package / E2E / Store flags `false`.
4. A later Windows GDK SDK builder must choose and review the package version separately, generate a **real GDK MSIXVC/MSIXVC2** using the **pinned EXE bytes**, and run Provisioner SDK pack, result-intake and E2E transfer checks. The 36-minute Windows/E2E owner handles the central ledger/queue. Do not route through the generic Factory MSIX workflow.

The gate rechecks the Provisioner intake schema, approved GDK Identity values, **the live immutable source branch ref still pointing to the fixed source SHA**, direct-parent CAS commit, committed approved Identity, **the original EXE signature provenance remaining `QA_UNSIGNED`**, dedicated build branch, every intermediate product-file change (including changes later reverted), exact ZIP and EXE hashes, CRC and provenance. It rejects dirty checkouts, mismatched Git heads, unknown intake fields, forged success flags, and modified Identity. It is **read-only** and cannot authorize CAS or Store submission.

## CI

`python -m unittest discover -s tests -v` runs synthetic local Git history and ZIP fixtures, including tamper-and-revert and wrong-branch rejection. These fixtures are not evidence of real CAS or GDK SDK packaging. Do not mark `CAS_RETURN_PASS`, `REAL_MSIX_PASS`, or `E2E PASS` based on this check-only gate.
