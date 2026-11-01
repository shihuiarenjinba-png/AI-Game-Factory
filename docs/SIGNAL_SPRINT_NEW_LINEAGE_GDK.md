# Signal Sprint — immutable NEW build lineage (Draft, not old Artifact recovery)

This is a **new** request/build lineage for the **same** Signal Sprint game.
It does not modify the immutable source branch, recover the old expired
Artifact, or assert that the old EXE SHA authority conflict is resolved.

- Source repository: `shihuiarenjinba-png/AI-Game-Factory`
- Immutable source branch: `codex/game-signal-sprint-undo-20261027`
- Immutable source SHA: `c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Old request: `game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e`
- Old Artifact ID: `12706862577` (expired/404)
- Old ZIP SHA: `e48a0426595dc227988f12944921511a47d5c8feca8b063a161dd0dd61306412`
- Conflicting old EXE SHA candidates: `9c31c3633de0d9e248cd1642f9003962f4f117bf6780cf4fab9f66d1d73485ad` and `e8517df8cd31a40e5ce72afdd4e6a4d63626fb99f7ff8a4fa3296ff8deef05f4`.

## New lineage contract

`game-signal-sprint-new-lineage.yml` is **manual-only**. The workflow is
intended for review and eventual explicit dispatch after an authorized
workflow registration. GitHub generally requires a workflow_dispatch
workflow to exist on the default branch; a Draft PR alone is not permission
to merge or dispatch. No new Artifact is claimed until a real successful
run is observed.

A control/build checkout and the immutable source checkout are separate.
The source checkout is pinned by commit, not branch. The new run uses
`game-signal-sprint-<source_sha>-reissue-<build_id>-<run_id>` as its request
ID. The build ID must be 8–32 lowercase alphanumeric/hyphen characters.
The run ID comes from GitHub Actions, and the control HEAD is recorded as
`build_head_sha`, separate from `source_sha`. Never use the old request
or old ZIP as the new lineage.

The Windows EXE is built from the pinned source using the existing pinned
PyInstaller entrypoint. The receipt builder then creates an independent
`new-lineage.zip` containing the EXE, intake request, and provenance.
It independently records SHA-256 of the ZIP and of the EXE inside the ZIP.
The GitHub upload-artifact wrapper is **not** identical to this inner ZIP;
the GitHub Artifact ID must be captured and verified separately.

The receipt explicitly sets:
`legacy_artifact_recovered=false`,
`legacy_artifact_replaced=false`,
`github_evidence_verified=false`,
`cas_status=NOT_EXECUTED`, and
`msixvc2_status=NOT_BUILT`.
Do not change these claims merely because synthetic tests or CI pass.

## Required next independent gates

1. After a real new build, retrieve GitHub run/commit/artifact metadata and
   downloaded exact bytes. Feed these into the **existing**
   Repository-Provisioner-game PR #10 evidence validator, not a second
   implementation in Factory. Verify new run ID, build HEAD, Artifact ID,
   ZIP SHA, contained EXE SHA, provenance, and request ID independently.
2. Validate user approval/authority, GDK Identity and a separately approved
   Package Version; do not infer Version from Store ID, Title ID, or EXE.
3. Only then consider new-request CAS, GDK `MicrosoftGame.config` and
   MSIXVC2 via the post-CAS dedicated build branch.
4. Real GDK SDK build, Windows E2E, and Store submission remain separate
   gates. No Store upload, merge, or Identity lookup is authorized.

**Partner Center selection: GDK game.** Identity already received.
No change to Windows-all-auto central ledger (36-minute owner).
