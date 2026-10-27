import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.msix_handoff import create_handoff

SHA="a"*40
BUILD_SHA="b"*40
XML=b'<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"><Identity Name="OkinawaDesktopTools.Demo" Publisher="CN=TEST" Version="1.0.0.0"/></Package>'

class FactoryTransportTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.kind=Path(__file__).resolve().parents[1].joinpath("factory/config.json")
        self.kind=json.loads(self.kind.read_text(encoding="utf-8"))["kind"]
        (self.root/"factory").mkdir()
        (self.root/"factory/config.json").write_text(json.dumps({"kind":self.kind}))
        self.prod=self.root/"products/demo-product"
        (self.prod/"store").mkdir(parents=True)
        (self.prod/"manifest.json").write_text(json.dumps({"slug":"demo-product","kind":self.kind}))
        self.approved={"reviewed":True,"source":"partner_center","store_id":"9PTESTING",
            "name":"OkinawaDesktopTools.Demo","publisher":"CN=TEST","version":"1.0.0.0",
            "request_id":"game-demo-"+SHA,"product_type":"GAME",
            "source_factory":"AI-Game-Factory",
            "source_repository":"shihuiarenjinba-png/AI-Game-Factory",
            "source_branch":"codex/game-signal-sprint-undo-20261027",
            "source_sha":SHA,"verified_source_sha":SHA,
            "package_sha256":"c"*64,
            "package_family_name":"OkinawaDesktopTools.Demo_abcdefghijklm",
            "package_sid":"S-1-15-2-1-2-3-4-5-6-7",
            "verified_by":"fixture-operator","evidence_url":"https://example.invalid/fixture"}
        self.save_approved()
        self.package=self.root/"sample.msix"
        with zipfile.ZipFile(self.package,"w") as zipfileout:
            zipfileout.writestr("AppxManifest.xml",XML)
            zipfileout.writestr("AppxBlockMap.xml",
                b'<BlockMap xmlns="http://schemas.microsoft.com/appx/2010/blockmap"/>')
            zipfileout.writestr("[Content_Types].xml",
                b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            zipfileout.writestr("demo.exe",b"windows test executable")

    def save_approved(self):
        (self.prod/"store/approved-identity.json").write_text(json.dumps(self.approved))

    def test_produces_handoff_with_actual_bytes(self):
        meta=create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)
        self.assertEqual(meta["type"],self.kind)
        self.assertEqual(meta["status"],"QA_UNSIGNED")
        saved=self.root/"exports/factory-msix-handoff"
        self.assertEqual((saved/"package.msix").read_bytes(),self.package.read_bytes())
        self.assertEqual(meta["package_sha256"],hashlib.sha256(self.package.read_bytes()).hexdigest())
        self.assertEqual(meta["source_sha"],SHA)
        self.assertEqual(meta["expected_head_sha"],SHA)
        self.assertEqual(meta["factory_head_sha"],BUILD_SHA)
        self.assertEqual(meta["request_id"],"game-demo-"+SHA)
        self.assertEqual(meta["product_type"],"GAME")
        self.assertEqual(meta["source_factory"],"AI-Game-Factory")
        self.assertEqual(meta["source_branch"],"codex/game-signal-sprint-undo-20261027")
        self.assertEqual(meta["store_id"],"9PTESTING")
        self.assertEqual(meta["preidentity_package_sha256"],"c"*64)
        self.assertEqual(meta["source_repository"],
                         "https://github.com/shihuiarenjinba-png/AI-Game-Factory")

    def test_wrong_verified_source_sha_fails(self):
        self.approved["verified_source_sha"]="d"*40
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"verified_source_sha"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_wrong_product_type_fails_closed(self):
        self.approved["product_type"]="APP"
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"product_type"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_missing_request_id_fails_closed(self):
        del self.approved["request_id"]
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"request_id"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_build_head_is_not_immutable_source_sha(self):
        with self.assertRaisesRegex(ValueError,"build HEAD must differ"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,SHA)

    def test_wrong_official_package_sid_fails_closed(self):
        self.approved["package_sid"]="S-1-15-2-NOTREAL"
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"package SID malformed"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_missing_local_package_sha_fails_closed(self):
        self.approved["package_sha256"]=None
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"local package SHA"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_no_partner_center_evidence_fails(self):
        self.approved["reviewed"]=False
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"approval"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_wrong_publisher_fails(self):
        self.approved["publisher"]="CN=FAKE"
        self.save_approved()
        with self.assertRaisesRegex(ValueError,"approved publisher"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_wrong_source_sha_fails(self):
        with self.assertRaisesRegex(ValueError,"Git source"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports","not-a-sha",BUILD_SHA)

    def test_kind_mismatch_fails(self):
        (self.prod/"manifest.json").write_text(json.dumps({"slug":"demo-product","kind":"unknown"}))
        with self.assertRaisesRegex(ValueError,"factory mismatch"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_invalid_msix_fails(self):
        self.package.write_bytes(b"not a msix")
        with self.assertRaisesRegex(ValueError,"invalid MSIX"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_generic_zip_with_only_manifest_is_not_msix(self):
        # Previously accepted a plain ZIP with an AppxManifest.xml.
        with zipfile.ZipFile(self.package,"w") as z:
            z.writestr("AppxManifest.xml",XML)
            z.writestr("demo.exe",b"not a packaged Windows executable")
        with self.assertRaisesRegex(ValueError,"required MSIX metadata missing"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_duplicate_casefolded_zip_members_hold(self):
        # Windows package member names are case-insensitive; never allow
        # ambiguous manifests that could be interpreted differently.
        with zipfile.ZipFile(self.package,"a") as z:
            z.writestr("APPXMANIFEST.XML",XML)
        with self.assertRaisesRegex(ValueError,"duplicate MSIX ZIP member"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_wrong_blockmap_root_holds(self):
        with zipfile.ZipFile(self.package,"w") as z:
            z.writestr("AppxManifest.xml",XML)
            z.writestr("AppxBlockMap.xml",b"<Package/>")
            z.writestr("[Content_Types].xml",b"<Types/>")
            z.writestr("demo.exe",b"test")
        with self.assertRaisesRegex(ValueError,"invalid MSIX metadata root"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

    def test_duplicate_bundle_fails(self):
        create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)
        with self.assertRaisesRegex(ValueError,"already exists"):
            create_handoff(self.root,"demo-product",self.package,self.root/"exports",SHA,BUILD_SHA)

if __name__=="__main__":unittest.main()
