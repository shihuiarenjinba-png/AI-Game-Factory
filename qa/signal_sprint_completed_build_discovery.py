"""Deterministic exact-head selector for the Signal Sprint cloud build run.

The workflow polls GitHub Actions for a build of the same QA workflow HEAD.
This pure selector is deliberately separated so the cloud fixture can exercise
run filtering, retry ordering, and fail-closed metadata handling without a
live API or a physical Windows runner.
"""
from __future__ import annotations

import re

REPOSITORY = "shihuiarenjinba-png/AI-Game-Factory"
WORKFLOW_PATH = ".github/workflows/signal-sprint-cloud-build-proof.yml"
SHA40 = re.compile(r"^[a-f0-9]{40}$")


def _positive_integer(value: object, reason: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(reason)
    return value


def select_exact_head_build_run(
    runs: object,
    expected_head: object,
    repo: str = REPOSITORY,
) -> dict | None:
    """Return the newest exact-head push run; never fall back past its failure.

    A run is eligible only when repository, workflow path, event, and full
    40-character head SHA all match. Ordering is by workflow run number,
    then rerun attempt, then run ID. The caller decides whether the selected
    run is still in progress or completed successfully.
    """
    if not isinstance(expected_head, str) or SHA40.fullmatch(expected_head) is None:
        raise ValueError("EXPECTED_HEAD_INVALID")
    if not isinstance(repo, str) or not repo:
        raise ValueError("REPOSITORY_INVALID")
    if not isinstance(runs, list):
        raise ValueError("WORKFLOW_RUNS_INVALID")

    candidates: list[dict] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("head_sha") != expected_head:
            continue
        if run.get("path") != WORKFLOW_PATH:
            continue
        if run.get("event") != "push":
            continue
        repository = run.get("repository")
        if not isinstance(repository, dict) or repository.get("full_name") != repo:
            continue

        _positive_integer(run.get("id"), "BUILD_RUN_ID_INVALID")
        _positive_integer(run.get("run_number"), "BUILD_RUN_NUMBER_INVALID")
        _positive_integer(run.get("run_attempt"), "BUILD_RUN_ATTEMPT_INVALID")
        candidates.append(run)

    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (item["run_number"], item["run_attempt"], item["id"]),
    )
