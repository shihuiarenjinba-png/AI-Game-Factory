"""Synthetic negative tests: a new build must never masquerade as old ZIP/CAS."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import gdk_new_lineage_factory as m


class NewLineageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "source"
        self.control = self.root / "control"
        self.stage = self.root / "staging"
        for p in (self.source, self.control, self.stage):
            p.mkdir()
        self.exe = self.source / "SignalSprint.exe"
        self.exe.write_bytes(b"MZ" + b"X" * 120000)
        self.build_id = "sprint-reissue-001"
        self.run_id = "41360000000"
        self.head = "a" * 40
        self.request = m.new_request_id(self.build_id, self.run_id)
        self.intake = {
            "schema_version": "1.0", "request_id": self.request,
            "source_sha": m.SOURCE_SHA, "source_branch": m.SOURCE_BRANCH,
            "source_repository": m.REPOSITORY, "source_factory": "AI-Game-Factory",
            "product_type": "GAME", "slug": "signal-sprint", "dry_run": True,
            "display_name": "Signal Sprint - Offline Route Puzzle",
            "target_owner": "shihuiarenjinba-png",
            "requested_actions": [
                "BUILD_WINDOWS", "INSPECT_PACKAGE",
                "LOOKUP_OFFICIAL_IDENTITY", "PROPOSE_GITHUB_RETURN",
            ],
        }

    def context(self, **changes):
        args = dict(source_sha=m.SOURCE_SHA, source_head=m.SOURCE_SHA,
                    build_head=self.head, source_branch=m.SOURCE_BRANCH,
                    build_id=self.build_id, run_id=self.run_id,
                    source_dir=self.source, staging_dir=self.stage, control_dir=self.control)
        args.update(changes)
        return m.validate_context(**args)

    def bundle(self, **changes):
        args = dict(exe=self.exe, intake=self.intake, stage=self.stage,
                    request_id=self.request, build_id=self.build_id,
                    run_id=self.run_id, build_head=self.head)
        args.update(changes)
        return m.create_bundle(**args)

    def test_new_request_is_distinct(self):
        self.assertNotEqual(self.context(), m.OLD_REQUEST)

    def test_zip_exe_provenance_and_receipt_independent_digests(self):
        receipt = self.bundle()
        archive = self.stage / "new-lineage.zip"
        self.assertEqual(receipt["artifact_sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(receipt["executable_sha256"], hashlib.sha256(self.exe.read_bytes()).hexdigest())
        self.assertFalse(receipt["legacy_artifact_recovered"])
        self.assertFalse(receipt["legacy_artifact_replaced"])
        self.assertFalse(receipt["github_evidence_verified"])
        self.assertIsNone(receipt["github_artifact_id"])
        self.assertEqual(receipt["cas_status"], "NOT_EXECUTED")
        self.assertEqual(receipt["msixvc2_status"], "NOT_BUILT")
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(z.read("SignalSprint.exe"), self.exe.read_bytes())
            self.assertEqual(json.loads(z.read("provenance.json"))["request_id"], self.request)
            self.assertEqual(json.loads(z.read("provisioner-request.json"))["source_sha"], m.SOURCE_SHA)

    def test_old_request_rejected(self):
        with self.assertRaisesRegex(ValueError, "request ID"):
            self.bundle(request_id=m.OLD_REQUEST)
        with self.assertRaisesRegex(ValueError, "intake mismatch"):
            self.bundle(intake=dict(self.intake, request_id=m.OLD_REQUEST))

    def test_cross_product_and_source_rejected(self):
        for field, value in (("slug", "other-game"), ("product_type", "APP"),
                             ("source_repository", "other/repo"),
                             ("source_sha", "f" * 40),
                             ("source_branch", "main"), ("dry_run", False)):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "intake mismatch"):
                self.bundle(intake=dict(self.intake, **{field: value}))

    def test_intake_type_spoofing_and_unapproved_fields_rejected(self):
        for change in (
            {"dry_run": 1},
            {"requested_actions": ["BUILD_WINDOWS", "SUBMIT_STORE"]},
            {"display_name": "Other Game"},
            {"target_owner": "other"},
            {"cas_return_pass": True},
            {"github_evidence_verified": True},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "intake mismatch"):
                self.bundle(intake=dict(self.intake, **change))

    def test_missing_intake_fields_rejected(self):
        for field in ("target_owner", "display_name", "requested_actions"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "intake mismatch"):
                self.bundle(intake={k: v for k, v in self.intake.items() if k != field})

    def test_workflow_prebuild_and_receipt_guards(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/game-signal-sprint-new-lineage.yml").read_text()
        self.assertLess(workflow.index("Verify immutable source and distinct control HEAD"),
                        workflow.index("Build unsigned GAME EXE"))
        for expected in ("source checkout dirty before build",
                         "unproven evidence claim", "uploaded inner ZIP digest mismatch",
                         "lineage identity mismatch"):
            self.assertIn(expected, workflow)

    def test_bad_schema_rejected(self):
        with self.assertRaisesRegex(ValueError, "intake mismatch"):
            self.bundle(intake=dict(self.intake, schema_version="2.0"))

    def test_source_head_branch_and_build_head_mismatch_rejected(self):
        for change in ({"source_sha": "f" * 40}, {"source_head": "f" * 40},
                       {"build_head": m.SOURCE_SHA}, {"source_branch": "main"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.context(**change)

    def test_bad_build_and_run_ids_rejected(self):
        for value in ("old", "../unsafe", "UpperCase99", "a" * 33):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.new_request_id(value, self.run_id)
        for value in ("0", "abc", "-10", "1" * 21):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.new_request_id(self.build_id, value)

    def test_staging_in_factory_checkout_rejected(self):
        for stage in (self.source, self.control):
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "staging"):
                self.context(staging_dir=stage)
        nested = self.source / "gdk-staging"
        nested.mkdir()
        with self.assertRaisesRegex(ValueError, "staging"):
            self.context(staging_dir=nested)

    def test_overlapping_source_and_control_rejected(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.context(control_dir=self.source)

    def test_invalid_or_missing_exe_rejected(self):
        self.exe.write_bytes(b"NOTPE" + b"x" * 120000)
        with self.assertRaisesRegex(ValueError, "PE candidate"):
            self.bundle()
        self.exe.unlink()
        with self.assertRaisesRegex(ValueError, "EXE"):
            self.bundle()

    def test_output_is_never_overwritten(self):
        self.bundle()
        with self.assertRaisesRegex(ValueError, "overwritten"):
            self.bundle()

    def test_symlinked_exe_rejected(self):
        target = self.root / "real.exe"
        self.exe.rename(target)
        try:
            self.exe.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaisesRegex(ValueError, "linked"):
            self.bundle()

    def test_old_zip_digest_rejected(self):
        receipt = self.bundle()
        other = self.root / "another-stage"
        other.mkdir()
        with patch.object(m, "OLD_ZIP_SHA", receipt["artifact_sha256"]):
            with self.assertRaisesRegex(ValueError, "legacy ZIP reused"):
                self.bundle(stage=other)
        self.assertFalse((other / "new-lineage.zip").exists())

    def test_run_id_must_match_request(self):
        with self.assertRaisesRegex(ValueError, "request ID"):
            self.bundle(run_id="41360000001")

    def test_workflow_manual_only_and_pinned_source(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/game-signal-sprint-new-lineage.yml").read_text()
        for expected in ("workflow_dispatch:", m.SOURCE_SHA,
                         "persist-credentials: false", "new-lineage.zip"):
            self.assertIn(expected, workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("types: [edited]", workflow)
        self.assertIn("github.event.pull_request.number == 15", workflow)
        self.assertIn("github.event.changes.body.from != null", workflow)
        self.assertIn("[signal-sprint-build-once]", workflow)
        self.assertIn("github.event.pull_request.head.sha", workflow)
        self.assertNotIn("pull_request_target:", workflow)


if __name__ == "__main__":
    unittest.main()
