"""Prevent accidental reactivation of paid model calls in the legacy cycle."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / ".github/workflows/factory-cycle.yml"
ACTIVE = ROOT / ".github/workflows/factory-autoloop.yml"


class NoPaidApiOrUnsafeWriteRegression(unittest.TestCase):
    def test_both_manual_entrypoints_are_model_api_free(self):
        for path in (LEGACY, ACTIVE):
            with self.subTest(workflow=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("OPENAI_API_KEY", source)
                self.assertNotIn("openai/codex-action", source)
                self.assertNotIn("openai-api-key:", source)
                self.assertNotIn("schedule:", source)
                self.assertIn("workflow_dispatch:", source)

    def test_legacy_cycle_cannot_write_or_create_prs(self):
        source = LEGACY.read_text(encoding="utf-8")
        self.assertIn("contents: read", source)
        self.assertNotIn("contents: write", source)
        self.assertNotIn("pull-requests: write", source)
        self.assertNotIn("gh pr create", source)
        self.assertNotIn("git push", source)
        self.assertIn("python -m unittest discover -s tests", source)

    def test_msix_export_remains_separate_and_windows_only(self):
        export = (ROOT / ".github/workflows/msix-export.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: windows-latest", export)
        self.assertIn("approved-identity.json", export)
        self.assertIn("actions/upload-artifact@v4", export)


if __name__ == "__main__":
    unittest.main()
