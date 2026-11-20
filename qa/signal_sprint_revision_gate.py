"""Fail-closed ancestry gate for Signal Sprint product source and required UX revision.

This checks GitHub commit ancestry, not EXE contents or physical UIA.
"""
import argparse
import json
import os
import urllib.request

REPO = "shihuiarenjinba-png/AI-Game-Factory"
FROZEN_SOURCE = "1a349faa41663c417c40710140a4d50c79b62b78"
REQUIRED_REVISION = "9ccd7ff4389b3ca0e45c8407d7369a00f4302cf2"


def verify_revision(fetch, source=FROZEN_SOURCE, revision=REQUIRED_REVISION):
    if source != FROZEN_SOURCE:
        raise ValueError("FROZEN_SOURCE_MISMATCH")
    if revision != REQUIRED_REVISION:
        raise ValueError("REQUIRED_REVISION_MISMATCH")
    data = fetch(revision, source)
    if not isinstance(data, dict) or data.get("status") not in ("identical", "ahead"):
        raise ValueError("REVISION_NOT_IN_PRODUCT_SOURCE")
    base = data.get("merge_base_commit")
    if not isinstance(base, dict) or base.get("sha") != revision:
        raise ValueError("REVISION_NOT_IN_PRODUCT_SOURCE")
    return {"status": "PASS_REVISION_ANCESTRY_ONLY", "product_source": source,
            "required_revision": revision, "physical_gui_verified": False}


def github_compare(revision, source):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN_MISSING")
    url = f"https://api.github.com/repos/{REPO}/compare/{revision}...{source}"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "signal-sprint-revision-gate",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = verify_revision(github_compare)
        code = 0
    except Exception as exc:
        result = {"status": "FAIL", "error": str(exc),
                  "product_source": FROZEN_SOURCE, "required_revision": REQUIRED_REVISION,
                  "physical_gui_verified": False}
        code = 1
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(result["status"], result.get("error", ""))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
