"""Offline regressions for Factory -> GAME Provisioner v1.0 contract."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from package_intake_request import build_request, ACTIONS


class GameIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.slug = "arcade-puzzle-game"
        product = self.root / "products" / self.slug
        product.mkdir(parents=True)
        (self.root / "proposals").mkdir()
        self.manifest = product / "manifest.json"
        self.proposal = self.root / "proposals" / (self.slug + ".json")
        self.entry = product / "main.py"
        self.manifest.write_text(json.dumps({
            "slug": self.slug, "kind": "game", "entry": "main.py"
        }), encoding="utf-8")
        self.proposal.write_text(json.dumps({
            "slug": self.slug, "title": "Arcade Puzzle Game"
        }), encoding="utf-8")
        self.entry.write_text("print('game')\n", encoding="utf-8")

    def request(self, **kwargs):
        return build_request(
            self.root, kwargs.get("slug", self.slug),
            kwargs.get("request_id", "game-20261026-001"),
            kwargs.get("source_sha", "a" * 40))

    def test_exact_provisioner_package_job_contract(self):
        result = self.request()
        self.assertEqual(set(result), {
            "schema_version", "request_id", "product_type", "source_factory",
            "source_repository", "source_branch", "source_sha", "slug",
            "display_name", "target_owner", "dry_run", "requested_actions",
        })
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["product_type"], "GAME")
        self.assertEqual(result["source_factory"], "AI-Game-Factory")
        self.assertEqual(result["source_repository"],
                         "shihuiarenjinba-png/AI-Game-Factory")
        self.assertEqual(result["source_branch"], "codex/factory-autoloop-20261026")
        self.assertEqual(result["target_owner"], "shihuiarenjinba-png")
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["requested_actions"], ACTIONS)
        self.assertEqual(result["display_name"], "Arcade Puzzle Game")

    def test_rejects_app_or_mismatched_manifest(self):
        self.manifest.write_text(json.dumps({
            "slug": self.slug, "kind": "app", "entry": "main.py"
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.request()

    def test_rejects_wrong_proposal_slug(self):
        self.proposal.write_text(json.dumps({
            "slug": "different-product", "title": "Arcade Puzzle Game"
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.request()

    def test_rejects_missing_product_or_entry(self):
        self.entry.unlink()
        with self.assertRaisesRegex(ValueError, "entrypoint"):
            self.request()
        with self.assertRaises(ValueError):
            self.request(slug="../unsafe")

    def test_rejects_unsafe_sha_and_request_id(self):
        for value in ("0" * 40, "A" * 40, "a" * 39, "../bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.request(source_sha=value)
        with self.assertRaises(ValueError):
            self.request(request_id="../../other")

    def test_request_id_matches_live_provisioner_length_contract(self):
        # The executable Provisioner Job.validate requires 4..128 characters.
        # Previously Factory emitted 1..3 character IDs that later failed HOLD.
        for value in ("a", "ab", "abc", "a" * 129):
            with self.subTest(request_id=value), self.assertRaisesRegex(ValueError, "request_id"):
                self.request(request_id=value)
        for value in ("abcd", "a" * 128):
            with self.subTest(request_id=value):
                self.assertEqual(self.request(request_id=value)["request_id"], value)

    def test_rejects_control_and_blank_titles(self):
        for title in (" ", "bad\nname", "fake\u202eexe", " leading"):
            self.proposal.write_text(json.dumps({
                "slug": self.slug, "title": title
            }), encoding="utf-8")
            with self.subTest(title=title), self.assertRaisesRegex(ValueError, "display_name"):
                self.request()

    def test_missing_proposal_fails_closed(self):
        self.proposal.unlink()
        with self.assertRaises(ValueError):
            self.request()

    def test_cli_creates_only_dry_run_receipt(self):
        output = self.root / "request.json"
        result = subprocess.run([
            sys.executable, "package_intake_request.py",
            "--root", str(self.root), "--slug", self.slug,
            "--request-id", "game-20261026-001",
            "--source-sha", "a" * 40, "--output", str(output),
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(output.read_text(encoding="utf-8"))["dry_run"])
        self.assertEqual(set(p.name for p in self.root.iterdir()),
                         {"products", "proposals", "request.json"})

    def test_cli_refuses_symlink_output(self):
        target = self.root / "protected.json"
        target.write_text("protected", encoding="utf-8")
        output = self.root / "request.json"
        try:
            output.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        result = subprocess.run([
            sys.executable, "package_intake_request.py",
            "--root", str(self.root), "--slug", self.slug,
            "--request-id", "game-20261026-001",
            "--source-sha", "a" * 40, "--output", str(output),
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "protected")


if __name__ == "__main__":
    unittest.main()
