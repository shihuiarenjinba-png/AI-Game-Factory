#!/usr/bin/env python3
"""Deterministic 24h cadence simulation; never verifies an external task run."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/factory-cycle.yml"


def inspect_schedule(source: str):
    match = re.search(r"^\s+- cron:\s*['\"]([^'\"]+)['\"]\s*$", source, re.M)
    if match is None:
        # ChatGPT Tasks schedules four hourly tasks at 00/15/30/45.
        # GitHub workflow_dispatch is the receiver, not the AI scheduler.
        if not re.search(r"^\s*workflow_dispatch:\s*$", source, re.M):
            raise ValueError("missing manual dispatch entry point")
        if re.search(r"^\s*schedule:\s*$", source, re.M):
            raise ValueError("unparseable GitHub cron; refuse to assume external control")
        minutes = [0, 15, 30, 45]
        cron = None
        schedule_source = "external_chatgpt_tasks_unverified"
    else:
        parts = match.group(1).split()
        if len(parts) != 5 or parts[1:] != ["*", "*", "*", "*"]:
            raise ValueError("unexpected schedule pattern")
        minutes = [int(m) for m in parts[0].split(",")]
        cron = match.group(1)
        schedule_source = "github_cron_config_only"

    if len(minutes) != 4 or len(set(minutes)) != 4 or any(m < 0 or m >= 60 for m in minutes):
        raise ValueError("expected exactly four unique minute positions")
    minutes.sort()
    ticks = [
        datetime(2026, 10, 26, hour, minute, tzinfo=timezone.utc)
        for hour in range(24) for minute in minutes
    ]
    if len(ticks) != 96:
        raise ValueError("expected 96 simulated ticks")
    for a, b in zip(ticks, ticks[1:]):
        if b - a != timedelta(minutes=15):
            raise ValueError("invalid 15-minute spacing")
    if ticks[0] + timedelta(days=1) - ticks[-1] != timedelta(minutes=15):
        raise ValueError("invalid midnight spacing")

    return {
        "kind": json.loads((ROOT / "factory/config.json").read_text())["kind"],
        "cron": cron,
        "schedule_source": schedule_source,
        "external_schedule_verified": False,
        "simulated_minutes": minutes,
        "simulated_timestamps_per_24h": 96,
        "actual_github_schedule_executed": False,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(inspect_schedule(WF.read_text()), indent=2))
    except ValueError as e:
        print("HOLD:", str(e), file=sys.stderr)
        sys.exit(2)
