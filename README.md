# AI-Game-Factory

## Current operating model (2026-10-26)

This is the **ordinary/2D Windows game Factory**. The 3D pipeline is maintained separately in `3d-game-factory`; Windows applications use `AI-App-Factory`.

**No OpenAI API key or Codex GitHub Action is needed.** Research, design decisions, and code improvements are driven by ChatGPT scheduled tasks using the connected GitHub MCP. GitHub Actions only performs deterministic validation, Windows builds, and gated artifact export. The old `factory-cycle.yml` is a manual, read-only safety/CI entrypoint; it does not invoke an AI model, create products, or push branches. No GitHub Actions CRON is assumed to be a functioning ChatGPT agent.

## Source and review

- Develop on a `codex/*` work branch; never auto-write `main` or `release`, merge a PR, or submit to Microsoft Store.
- `factory.py` and `factory/state.json` provide the existing staged research/build/improvement prototype. The state machine and its mock tests are **not evidence of live autonomous generation**.
- `Repository-Provisioner-game` is the planned local intermediate worker: accept Factory name, slug, request ID, source repository/branch and exact source SHA; build/test a Windows package; obtain and verify already-issued official Microsoft Store identity from an authenticated Partner Center session; return an evidence-backed identity JSON to the correct Factory work branch. It must not guess a new Store ID from MSIX.
- The approved identity return contract is documented in `Windows-all-auto/docs/OFFICIAL_IDENTITY_RETURN_PROTOCOL.md`. The local worker implementation and full live return are not yet proven.

## Windows MSIX candidate path

1. A product must exist under `products/<slug>/` with matching `manifest.json` and `main.py`.
2. An authenticated operator/worker must verify official Partner Center product identity and write `products/<slug>/store/approved-identity.json` on the authorized work branch using the strict return contract. This file must contain `reviewed=true`, `source=partner_center`, `store_id`, `name`, `publisher`, and `version`.
3. Real PNG assets are required under `products/<slug>/store/assets/`: `StoreLogo.png`, `Square150.png`, and `Square44.png`.
4. The Windows `msix-export.yml` workflow runs PyInstaller and MakeAppx, compares the resulting MSIX identity with the approved data, and uploads a `factory-msix-handoff-<slug>` artifact with a checksum and source SHA. The artifact is for Windows-all-auto, **not** a certified Store submission.
5. Windows-all-auto must verify the actual package and provenance before local QA. A green Linux test alone is insufficient.

The Store ID is assigned by Microsoft Partner Center, not derived from an arbitrary package's PFN/SID. Until the official identity and source/QA evidence are available, the product stays **HOLD**. Signing, real Windows installation/UI QA, WACK, privacy/security declarations, licensing review, and Store submission are separately gated.

## Manual verification

```bash
python -m unittest discover -s tests -v
python -m py_compile factory.py scripts/simulate_clock.py
```

The following workflows are available for **manual validation**, not paid AI generation:

- `factory-autoloop.yml`: source/contract validation using GitHub Actions.
- `factory-cycle.yml`: retired legacy cycle replaced with a read-only validation gate.
- `factory-ci.yml`: regression suite.
- `msix-export.yml`: Windows MSIX export only when official identity and assets exist.

See `docs/MSIX_HANDOFF.md` for downstream artifact format. Product code, Windows install tests, Store identity retrieval and a full Factory-to-Windows-all-auto-to-local end-to-end test must be independently evidenced before reporting completion.
