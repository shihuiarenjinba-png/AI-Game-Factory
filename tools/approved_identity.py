"""Validate the exact operator-reviewed Partner Center Identity return contract.

This is a provenance gate, not an online Partner Center verification. Only an
authenticated local Provisioner can establish that the evidence is genuine.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

STORE_ID = re.compile(r"^[A-Za-z0-9]{8,32}$")
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{2,49}$")
VERSION = re.compile(r"^\d{1,5}(?:\.\d{1,5}){3}$")
TRUSTED_HOSTS = {"partner.microsoft.com", "partnercenter.microsoft.com"}


def validate_approved_identity(value: object) -> dict:
    """Fail closed on missing/malformed official evidence before packaging."""
    if not isinstance(value, dict) or value.get("reviewed") is not True or value.get("source") != "partner_center":
        raise ValueError("Partner Center approval not verified")
    for field, pattern in (("store_id", STORE_ID), ("name", NAME), ("version", VERSION)):
        field_value = value.get(field)
        if not isinstance(field_value, str) or not pattern.fullmatch(field_value):
            raise ValueError("Invalid verified " + field)
    publisher = value.get("publisher")
    if (not isinstance(publisher, str) or not publisher.startswith("CN=")
            or not 3 < len(publisher) <= 512
            or any(ord(c) < 32 for c in publisher)):
        raise ValueError("Invalid verified publisher")
    verifier = value.get("verified_by")
    if (not isinstance(verifier, str) or not 3 <= len(verifier) <= 100
            or any(ord(c) < 32 for c in verifier)):
        raise ValueError("Partner Center verifier missing or unsafe")
    evidence = value.get("evidence_url")
    if not isinstance(evidence, str) or len(evidence) > 2048:
        raise ValueError("Partner Center evidence URL missing")
    parsed = urlparse(evidence)
    if (parsed.scheme != "https" or parsed.hostname not in TRUSTED_HOSTS
            or parsed.username or parsed.password or parsed.fragment):
        raise ValueError("Partner Center evidence URL untrusted")
    for field in ("display_name", "publisher_display_name"):
        optional = value.get(field)
        if optional is not None and (not isinstance(optional, str)
                or not 1 <= len(optional) <= 100
                or any(ord(c) < 32 for c in optional)):
            raise ValueError("Invalid optional " + field)
    return value
