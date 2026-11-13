"""Re-download the 6 PEP source files at the pinned commit (they are already in data/raw/).

Usage (from starter/):  python scripts/fetch_corpus.py
Verifies each file against the SHA-256 recorded in data/corpus_sha256.txt.
"""
import hashlib
import json
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
cfg = json.loads((DATA / "corpus.json").read_text())
expected = dict(l.split()[::-1] for l in (DATA / "corpus_sha256.txt").read_text().splitlines() if l.strip())
for d in cfg["documents"]:
    name = Path(d["file"]).name
    url = f"https://raw.githubusercontent.com/python/peps/{cfg['snapshot']['commit']}/peps/{name}"
    body = urllib.request.urlopen(url, timeout=30).read()
    sha = hashlib.sha256(body).hexdigest()
    status = "OK" if expected.get(f"raw/{name}") == sha else "HASH MISMATCH"
    (DATA / d["file"]).write_bytes(body)
    print(f"{name}: {len(body)} bytes {status}")
