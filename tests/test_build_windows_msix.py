import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from tools.build_windows_msix import appx_manifest, verify_inputs

PNG=b"\x89PNG\r\n\x1a\n"+"".encode()
IDENTITY={"reviewed":True,"source":"partner_center","store_id":"9PTESTING",
          "name":"OkinawaDesktopTools.Demo","publisher":"CN=TEST","version":"1.0.0.0",
          "verified_by":"test-operator","evidence_url":"https://partner.microsoft.com/dashboard/products/example"}

class WindowsPackageContractTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.product=self.root/"products/demo-product"
        asset_dir=self.product/"store/assets"
        asset_dir.mkdir(parents=True)
        (self.product/"main.py").write_text("print('ok')")
        (self.product/"manifest.json").write_text(json.dumps({"slug":"demo-product","entry":"main.py"}))
        (self.product/"store/approved-identity.json").write_text(json.dumps(IDENTITY))
        for name in ("StoreLogo.png","Square150.png","Square44.png"):
            (asset_dir/name).write_bytes(PNG+b"not-valid-image-but-magic-header")

    def test_identity_produces_xml(self):
        xml=appx_manifest(IDENTITY,"demo-product.exe")
        root=ET.fromstring(xml)
        identity=next(x for x in root.iter() if x.tag.endswith("}Identity"))
        self.assertEqual(identity.attrib["Name"],IDENTITY["name"])
        self.assertEqual(identity.attrib["Publisher"],IDENTITY["publisher"])
        self.assertEqual(identity.attrib["Version"],IDENTITY["version"])

    def test_verified_identity_preflight(self):
        _,cfg=verify_inputs(self.root,"demo-product")
        self.assertEqual(cfg["store_id"],"9PTESTING")

    def test_missing_asset_holds(self):
        (self.product/"store/assets/StoreLogo.png").unlink()
        with self.assertRaisesRegex(ValueError,"asset missing"):
            verify_inputs(self.root,"demo-product")

    def test_no_human_review_holds(self):
        obj=dict(IDENTITY,reviewed=False)
        (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,"not verified"):
            verify_inputs(self.root,"demo-product")

    def test_identity_not_guessed(self):
        (self.product/"store/approved-identity.json").unlink()
        with self.assertRaisesRegex(ValueError,"do not invent"):
            verify_inputs(self.root,"demo-product")

    def test_invalid_version_holds(self):
        obj=dict(IDENTITY,version="1.0")
        (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,"Invalid verified version"):
            verify_inputs(self.root,"demo-product")

    def test_unverified_provenance_holds_before_build(self):
        for field in ("verified_by", "evidence_url"):
            with self.subTest(field=field):
                obj=dict(IDENTITY)
                obj.pop(field)
                (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
                with self.assertRaisesRegex(ValueError, "Partner Center"):
                    verify_inputs(self.root,"demo-product")

    def test_untrusted_partner_center_evidence_holds(self):
        obj=dict(IDENTITY,evidence_url="https://partner.microsoft.com.attacker.example/path")
        (self.product/"store/approved-identity.json").write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,"untrusted"):
            verify_inputs(self.root,"demo-product")

    def test_product_path_traversal_holds(self):
        with self.assertRaisesRegex(ValueError,"invalid product slug"):
            verify_inputs(self.root,"../demo-product")

    def test_symlinked_identity_holds(self):
        original=self.product/"store/approved-identity.json"
        backup=self.root/"backup.json"
        backup.write_bytes(original.read_bytes())
        original.unlink()
        try:
            original.symlink_to(backup)
        except (OSError,NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaisesRegex(ValueError,"do not invent"):
            verify_inputs(self.root,"demo-product")

if __name__=="__main__":unittest.main()
