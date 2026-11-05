"""Fail when the core mentions a client by name.

The names themselves are not in this repo: .client-denylist holds the SHA-256 of each forbidden word (lower
case). Every tracked file is split into words, and every word is hashed and compared; text inside .xlsx, .docx
and .pptx files is read too. Git history is not checked.

  python scripts/check_client_names.py              # check the repo, exit 1 on a hit
  python scripts/check_client_names.py --hash Name  # print the line to add to .client-denylist
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DENYLIST = ROOT / ".client-denylist"
WORD = re.compile(rb"[a-z0-9]+(?:-[a-z0-9]+)*")
ZIPPED = {".xlsx", ".docx", ".pptx"}


def digest(word: str | bytes) -> str:
    w = word if isinstance(word, bytes) else word.encode()
    return hashlib.sha256(w.lower()).hexdigest()


def denied() -> set[str]:
    lines = DENYLIST.read_text(encoding="utf-8").splitlines() if DENYLIST.exists() else []
    return {ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")}


def contents(path: Path) -> list[bytes]:
    if path.suffix.lower() in ZIPPED:
        try:
            with zipfile.ZipFile(path) as z:
                return [z.read(n) for n in z.namelist() if n.endswith(".xml")]
        except zipfile.BadZipFile:
            pass
    return [path.read_bytes()]


def words(blob: bytes) -> set[bytes]:
    found = set()
    for w in WORD.findall(blob.lower()):
        found.add(w)
        found.update(w.split(b"-"))  # "acme-brain" also counts as "acme"
    return found


def check(files: list[Path], bad: set[str]) -> list[str]:
    hits = []
    for f in files:
        for blob in contents(f):
            for w in words(blob):
                if digest(w) in bad:
                    hits.append(f"{f.relative_to(ROOT)}: a client name (hash {digest(w)[:12]})")
                    break
    return sorted(set(hits))


def tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / p.decode() for p in out.split(b"\0") if p and (ROOT / p.decode()).is_file()]


def main(argv: list[str]) -> int:
    if argv[:1] == ["--hash"]:
        for name in argv[1:]:
            print(f"{digest(name)}  # added {name[:1]}...")
        return 0
    bad = denied()
    if not bad:
        print(".client-denylist is empty: nothing to check against", file=sys.stderr)
        return 1
    hits = check(tracked(), bad)
    for h in hits:
        print(h, file=sys.stderr)
    print(f"{len(hits)} file(s) mention a client by name" if hits else "no client names found")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
