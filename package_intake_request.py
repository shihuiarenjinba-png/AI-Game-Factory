"""Emit a strict GAME package-intake request for Repository-Provisioner-game.

Offline and read-only: no GitHub write, Windows build, Store lookup, or ID guess.
The supplied source SHA must be checked against the live branch before use.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

SCHEMA_VERSION = "1.0"
OWNER = "shihuiarenjinba-png"
FACTORY = "AI-Game-Factory"
BRANCH = "codex/factory-autoloop-20261026"
ACTIONS = [
    "BUILD_WINDOWS", "INSPECT_PACKAGE",
    "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN",
]
SLUG = re.compile(r"^[a-z][a-z0-9-]{3,39}$")
REQUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _reject_duplicate_fields(pairs):
    """Reject ambiguous JSON keys at every nesting level."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError("missing, linked, or oversized source JSON")
    value = json.loads(path.read_text(encoding="utf-8"),
                       object_pairs_hook=_reject_duplicate_fields)
    if not isinstance(value, dict):
        raise ValueError("source JSON must be an object")
    return value


def build_request(root: Path, slug: str, request_id: str, source_sha: str) -> dict:
    """Create the exact 12-field v1.0 contract accepted by package_job.py."""
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("invalid GAME slug")
    if not isinstance(request_id, str) or not REQUEST.fullmatch(request_id):
        raise ValueError("invalid request_id")
    if (not isinstance(source_sha, str) or not SHA40.fullmatch(source_sha)
            or source_sha == "0" * 40):
        raise ValueError("real lower-case 40-digit source SHA required")
    if (root / "products").is_symlink() or (root / "proposals").is_symlink():
        raise ValueError("linked Factory source directory")
    product = root / "products" / slug
    if product.is_symlink() or not product.is_dir():
        raise ValueError("GAME product directory missing")
    manifest = _read_json(product / "manifest.json")
    proposal = _read_json(root / "proposals" / (slug + ".json"))
    if (manifest.get("slug") != slug or manifest.get("kind") != "game"
            or manifest.get("entry") != "main.py"
            or proposal.get("slug") != slug):
        raise ValueError("Factory product/proposal identity mismatch")
    entry = product / "main.py"
    if entry.is_symlink() or not entry.is_file():
        raise ValueError("GAME entrypoint missing")
    title = proposal.get("title")
    if (not isinstance(title, str) or not 1 <= len(title) <= 100
            or title != title.strip()
            or not title.strip()
            or any(unicodedata.category(c) in ("Cc", "Cf") for c in title)):
        raise ValueError("unsafe GAME display_name")
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "product_type": "GAME",
        "source_factory": FACTORY,
        "source_repository": OWNER + "/" + FACTORY,
        "source_branch": BRANCH,
        "source_sha": source_sha,
        "slug": slug,
        "display_name": title,
        "target_owner": OWNER,
        "dry_run": True,
        "requested_actions": list(ACTIONS),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = build_request(args.root, args.slug, args.request_id, args.source_sha)
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            if args.output.is_symlink() or not args.output.parent.is_dir():
                raise ValueError("unsafe output path")
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
        return 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print("GAME_INTAKE_HOLD: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
