"""Cloud-safe negative fixtures for Signal Sprint evidence contracts; NOT GUI proof."""
import hashlib
import json
import unittest

SOURCE = "1a349faa41663c417c40710140a4d50c79b62b78"
PR30 = "a377043d3c9ab0c71d9a100cdb841dd7000313b9"
EXPECTED = {
    "EN": {"Start / Retry (R)", "Undo (U)", "Save (Ctrl+S)", "Load (L)", "日本語 (J)"},
    "JP": {"開始 / 再挑戦 (R)", "1手戻す (U)", "保存 (Ctrl+S)", "読込 (L)", "English (J)"},
}

def verify_build(exe: bytes, receipt: dict, expected_sha: str):
    actual = hashlib.sha256(exe).hexdigest()
    if not (len(expected_sha) == 64 and all(c in "0123456789abcdef" for c in expected_sha.lower())):
        raise ValueError("INVALID_EXPECTED_EXE_SHA256")
    if actual.lower() != expected_sha.lower():
        raise ValueError("EXE_SHA256_MISMATCH")
    if receipt.get("source_commit") != SOURCE:
        raise ValueError("BUILD_SOURCE_MISMATCH")
    if receipt.get("exe_sha256", "").lower() != actual:
        raise ValueError("BUILD_RECEIPT_EXE_SHA_MISMATCH")
    if not receipt.get("build_run_url"):
        raise ValueError("BUILD_RUN_PROVENANCE_MISSING")
    return "RECEIPT_MATCHED_NOT_INDEPENDENTLY_VERIFIED"

def verify_uia(receipt: dict):
    if receipt.get("status") != "PASS":
        raise ValueError("UIA_STATUS_NOT_PASS")
    evidence = receipt.get("evidence", [])
    if len(evidence) != 10:
        raise ValueError("BILINGUAL_BUTTON_COVERAGE_INCOMPLETE")
    for lang in ("EN", "JP"):
        rows = [r for r in evidence if r.get("language") == lang]
        if {r.get("name") for r in rows} != EXPECTED[lang] or len(rows) != 5:
            raise ValueError("BUTTON_EXACT_SET_MISMATCH:" + lang)
        if not any(r.get("lost_uia_nodes") for r in rows):
            raise ValueError("LOST_UIA_NOT_OBSERVED:" + lang)
        for r in rows:
            if not (r.get("invoked") is True and r.get("side_effect_verified") is True
                    and r.get("invoke_pattern") is True and r.get("focus") is True):
                raise ValueError("ACTION_NOT_VERIFIED:" + lang + "/" + r["name"])
    return True

class ContractFixtures(unittest.TestCase):
    def setUp(self):
        self.exe = b"fixture-exe-bytes-not-a-real-executable"
        self.sha = hashlib.sha256(self.exe).hexdigest()
        self.build = dict(source_commit=SOURCE, exe_sha256=self.sha,
                          build_run_url="https://github.com/example/actions/runs/1")
        self.uia = dict(status="PASS", evidence=[
            dict(language=lang, name=name, invoked=True, side_effect_verified=True,
                 invoke_pattern=True, focus=True,
                 lost_uia_nodes=["ControlType.Text:LOST" if lang == "EN" else "ControlType.Text:失敗"])
            for lang, names in EXPECTED.items() for name in sorted(names)
        ])

    def test_build_positive_but_not_independent(self):
        self.assertEqual(verify_build(self.exe, self.build, self.sha),
                         "RECEIPT_MATCHED_NOT_INDEPENDENTLY_VERIFIED")

    def test_build_negative(self):
        for change in ({"source_commit": PR30}, {"exe_sha256": "0"*64}, {"build_run_url": ""}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_build(self.exe, {**self.build, **change}, self.sha)
        with self.assertRaisesRegex(ValueError, "EXE_SHA256_MISMATCH"):
            verify_build(self.exe + b"changed", self.build, self.sha)

    def test_uia_positive_contract_only(self):
        self.assertTrue(verify_uia(self.uia))

    def test_uia_negative(self):
        import copy
        for mutation in ("missing", "no_lost", "no_effect", "no_invoke"):
            value = copy.deepcopy(self.uia)
            if mutation == "missing":
                value["evidence"].pop()
            elif mutation == "no_lost":
                for row in value["evidence"]:
                    if row["language"] == "JP":
                        row["lost_uia_nodes"] = []
            elif mutation == "no_effect":
                value["evidence"][0]["side_effect_verified"] = False
            else:
                value["evidence"][0]["invoked"] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify_uia(value)

if __name__ == "__main__":
    unittest.main()
