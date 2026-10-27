"""Create MSIX transfer artifact for Windows-all-auto, never a Store submission."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

SLUG=re.compile(r"^[a-z][a-z0-9-]{3,39}$")
SHA40=re.compile(r"^[a-f0-9]{40}$")
OWNER="shihuiarenjinba-png"

def fail(reason):
    raise ValueError("FACTORY_HANDOFF_HOLD: "+reason)

def msix_data(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 300*1024*1024:
        fail("MSIX missing, symlinked or oversized")
    try:
        with zipfile.ZipFile(path) as z:
            entries=z.infolist()
            if not 1 <= len(entries) <= 2000:fail("unsafe MSIX file count")
            members={}
            for entry in entries:
                name=entry.filename.replace("\\","/")
                key=name.casefold()
                if (not name or name.startswith("/") or ".." in name.split("/") or
                    entry.file_size>300*1024*1024 or
                    (entry.compress_size and entry.file_size>100*entry.compress_size)):
                    fail("unsafe MSIX ZIP member")
                if key in members:
                    fail("duplicate MSIX ZIP member")
                members[key]=entry
            # A generic ZIP with a forged AppxManifest is not an MSIX.
            # MakeAppx emits these mandatory package metadata parts.
            metadata=(
                ("appxmanifest.xml","Package"),
                ("appxblockmap.xml","BlockMap"),
                ("[content_types].xml","Types"),
            )
            parsed={}
            for name,expected_root in metadata:
                member=members.get(name)
                if member is None or not 0<member.file_size<=2*1024*1024:
                    fail("required MSIX metadata missing: "+name)
                document=ET.fromstring(z.read(member))
                if document.tag.rsplit("}",1)[-1]!=expected_root:
                    fail("invalid MSIX metadata root: "+name)
                parsed[name]=document
            root=parsed["appxmanifest.xml"]
    except (zipfile.BadZipFile,ET.ParseError,KeyError,RuntimeError,OSError) as error:
        fail("invalid MSIX container: "+type(error).__name__)
    identity=next((x for x in root.iter() if x.tag=="Identity" or x.tag.endswith("}Identity")),None)
    if identity is None:fail("MSIX identity absent")
    fields={key:identity.attrib.get(key.title()) for key in ("name","publisher","version")}
    if not all(isinstance(v,str) and v for v in fields.values()):fail("MSIX identity fields incomplete")
    digest=sha256()
    with path.open("rb") as reader:
        for piece in iter(lambda:reader.read(1024*1024),b""):digest.update(piece)
    fields.update(package_sha256=digest.hexdigest(),package_bytes=path.stat().st_size)
    return fields

def approved_correlation(approved:dict,kind:str,source_sha:str,factory_head_sha:str)->dict:
    """Bind the original immutable GAME request to a separate MSIX build HEAD.

    The approved JSON is written only after Provisioner CAS against the
    source branch. Its package_sha256 is the *pre-Identity* local package,
    never the new MSIX digest.
    """
    if kind!="game":
        fail("unsupported Factory handoff lane")
    if not isinstance(source_sha,str) or not SHA40.fullmatch(source_sha):
        fail("invalid Git source commit")
    if not isinstance(factory_head_sha,str) or not SHA40.fullmatch(factory_head_sha):
        fail("invalid Factory build HEAD")
    if factory_head_sha==source_sha:
        fail("Identity return/build HEAD must differ from immutable source")
    exact={
        "product_type":"GAME",
        "source_factory":"AI-Game-Factory",
        "source_repository":OWNER+"/AI-Game-Factory",
        "source_sha":source_sha,
        "verified_source_sha":source_sha,
    }
    for field,value in exact.items():
        if approved.get(field)!=value:
            fail("approved immutable provenance mismatch: "+field)
    request_id=approved.get("request_id")
    if not isinstance(request_id,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{3,127}",request_id):
        fail("approved request_id missing or malformed")
    branch=approved.get("source_branch")
    if (not isinstance(branch,str) or
        not re.fullmatch(r"codex/[A-Za-z0-9._/-]+",branch) or
        ".." in branch or "//" in branch or branch.endswith(("/", ".")) or
        any(part.startswith(".") or part.endswith(".lock") for part in branch.split("/"))):
        fail("approved source_branch missing or unsafe")
    local_sha=approved.get("package_sha256")
    if not isinstance(local_sha,str) or not re.fullmatch(r"[a-f0-9]{64}",local_sha):
        fail("approved local package SHA-256 missing")
    store_id=approved.get("store_id")
    if not isinstance(store_id,str) or not re.fullmatch(r"[A-Za-z0-9]{8,32}",store_id):
        fail("approved Store ID missing or malformed")
    for field in ("name","publisher","version","package_family_name","package_sid",
                  "verified_by","evidence_url"):
        if not isinstance(approved.get(field),str) or not approved[field].strip():
            fail("approved official Identity provenance missing: "+field)
    if not re.fullmatch(r"[A-Za-z0-9._-]+_[a-z0-9]{13}",approved["package_family_name"]):
        fail("approved package family name malformed")
    if not re.fullmatch(r"S-1-15-2(?:-\d+){7}",approved["package_sid"]):
        fail("approved package SID malformed")
    return {
        "request_id":request_id,
        "product_type":"GAME",
        "source_factory":"AI-Game-Factory",
        "source_branch":branch,
        "expected_head_sha":source_sha,
        "factory_head_sha":factory_head_sha,
        "store_id":store_id,
        "preidentity_package_sha256":local_sha,
    }


def create_handoff(repo_root:Path,slug:str,package:Path,output:Path,
                   source_sha:str,factory_head_sha:str)->dict:
    if not isinstance(slug,str) or not SLUG.fullmatch(slug):fail("invalid product slug")
    config=json.loads((repo_root/"factory/config.json").read_text(encoding="utf-8"))
    kind=config.get("kind")
    if kind!="game":fail("GAME Factory kind missing")
    manifest_path=repo_root/"products"/slug/"manifest.json"
    app_manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if app_manifest.get("slug")!=slug or app_manifest.get("kind")!=kind:
        fail("product manifest / factory mismatch")
    approved_path=repo_root/"products"/slug/"store/approved-identity.json"
    if approved_path.is_symlink() or not approved_path.is_file() or approved_path.stat().st_size>32768:
        fail("official Identity approval input missing or unsafe")
    approved=json.loads(approved_path.read_text(encoding="utf-8"))
    if (not isinstance(approved,dict) or approved.get("reviewed") is not True or
        approved.get("source")!="partner_center"):
        fail("Partner Center approval not recorded")
    correlation=approved_correlation(approved,kind,source_sha,factory_head_sha)
    actual=msix_data(package)
    for field in ("name","publisher","version"):
        if approved.get(field)!=actual[field]:fail("MSIX identity differs from approved "+field)
    result={
       "schema_version":1,
       "source_repository":"https://github.com/"+OWNER+"/AI-Game-Factory",
       "source_sha":source_sha,"type":"game","slug":slug,
       "package":"package.msix","status":"QA_UNSIGNED",
       "package_sha256":actual["package_sha256"],
       "package_bytes":actual["package_bytes"],
       "identity":{k:actual[k] for k in ("name","publisher","version")},
       **correlation,
    }
    dest=output/"factory-msix-handoff"
    if dest.exists():fail("output artifact already exists")
    dest.mkdir(parents=True)
    try:
        shutil.copyfile(package,dest/"package.msix")
        (dest/"handoff.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        if msix_data(dest/"package.msix")["package_sha256"]!=actual["package_sha256"]:
            fail("copied MSIX hash mismatch")
    except BaseException:
        shutil.rmtree(dest,ignore_errors=True)
        raise
    return result

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--slug",required=True)
    parser.add_argument("--msix",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--repository-root",type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args(argv)
    try:
        head=subprocess.check_output(["git","rev-parse","HEAD"],
            cwd=args.repository_root,encoding="utf-8",timeout=8).strip()
        approved_path=args.repository_root/"products"/args.slug/"store/approved-identity.json"
        approved=json.loads(approved_path.read_text(encoding="utf-8"))
        source_sha=approved.get("source_sha")
        print(json.dumps(create_handoff(args.repository_root,args.slug,args.msix,
            args.output,source_sha,head),ensure_ascii=False))
        return 0
    except (OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired,KeyError) as exc:
        print("HOLD:",type(exc).__name__,str(exc)[:160],file=sys.stderr)
        return 2

if __name__=="__main__":raise SystemExit(main())
