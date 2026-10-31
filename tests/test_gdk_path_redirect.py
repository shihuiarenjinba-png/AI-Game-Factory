"""Factory GDK post-CAS gate must not trust redirected or changing input paths."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import gdk_post_cas_gate as gate


class FactoryGdkPathGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.intake = self.root / "intake.json"
        self.intake.write_text('{"status":"fixture"}', encoding="utf-8")
        self.artifact = self.root / "artifact.zip"
        self.artifact.write_bytes(b"invalid fixture: rejected before ZIP parse")

    def _simulate_linked_parent(self):
        original = Path.is_symlink
        parent = self.root

        def linked(component):
            return component == parent or original(component)

        return patch.object(Path, "is_symlink", linked)

    def test_unredirected_small_json_still_loads(self):
        self.assertEqual(gate.load_json(self.intake), {"status": "fixture"})

    def test_intake_linked_parent_is_rejected(self):
        with self._simulate_linked_parent():
            with self.assertRaisesRegex(gate.GateHold, "linked path component"):
                gate.load_json(self.intake)

    def test_artifact_linked_parent_is_rejected_before_zip_read(self):
        with self._simulate_linked_parent():
            with self.assertRaisesRegex(gate.GateHold, "linked path component"):
                gate.check_artifact(self.artifact)

    def test_artifact_junction_parent_is_rejected(self):
        parent = self.root

        def junction(component):
            return component == parent

        with patch.object(Path, "is_junction", junction, create=True):
            with self.assertRaisesRegex(gate.GateHold, "linked path component"):
                gate.check_artifact(self.artifact)

    def test_intake_change_during_read_is_rejected(self):
        original = Path.read_bytes
        target = self.intake

        def mutate(component):
            data = original(component)
            if component == target:
                component.write_bytes(data + b" ")
            return data

        with patch.object(Path, "read_bytes", mutate):
            with self.assertRaisesRegex(gate.GateHold, "changed during read"):
                gate.load_json(self.intake)


if __name__ == "__main__":
    unittest.main()
