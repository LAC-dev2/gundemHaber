#!/usr/bin/env python3
"""BHM Kaynak Izleme Merkezi HTML dosyasindaki gomulu JSON verisini
data/sources.json olarak disa aktarir.

Kullanim:  python3 scripts/import_sources.py <bhm-kaynak-izleme-merkezi.html>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sources.json"

KEEP = ("id", "bolge", "kategori", "alt", "ad", "tur", "kanit",
        "siklik", "oncelik", "neden", "anahtar", "links")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    m = re.search(r'<script[^>]+id="veri"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        print("Gomulu #veri JSON bulunamadi.")
        return 1
    data = json.loads(m.group(1))

    sources = [{k: s.get(k) for k in KEEP if s.get(k) not in (None, "")}
               for s in data["sources"]]
    out = {
        "sources": sources,
        "themes": data.get("themes", []),
        "social": data.get("social", []),
        "terms": data.get("terms", []),
        "alertTerms": (data.get("alerts") or {}).get("terimler", []),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"{len(sources)} kaynak -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
