#!/usr/bin/env python3
"""En yuksek puanli kayitlarin tam metnini indirir (analiz icin).

collect.py'nin --full seceneginden farki: yeniden tarama yapmaz, mevcut
latest.json uzerinden calisir. Analiz adimindan hemen once cagrilir.

  python3 scripts/tam_metin.py --adet 18
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect                                        # noqa: E402
from extract import extract as extract_text           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PAGES = DATA / "pages"


def indir(row: dict) -> bool:
    hedef = PAGES / f"{row['k']}.json"
    if hedef.exists():
        return True
    try:
        ctype, govde = collect.fetch(row["url"], 1_200_000)
    except Exception:
        return False
    paragraflar = extract_text(govde, ctype)
    if not paragraflar:
        return False
    hedef.write_text(json.dumps({
        "k": row["k"], "baslik": row["baslik"], "kaynak": row["kaynak"],
        "url": row["url"], "tarih": row["tarih"],
        "kelime": sum(len(x.split()) for x in paragraflar),
        "paragraflar": paragraflar,
        "cekim": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adet", type=int, default=18)
    ap.add_argument("--gun", type=int, default=2, help="son kaç günün kayıtları")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    latest = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    sinir = (datetime.now(timezone.utc).date().toordinal() - args.gun)
    havuz = [h for h in latest["haberler"]
             if h.get("k") and h.get("url")
             and datetime.fromisoformat(h["tarih"]).date().toordinal() >= sinir]
    havuz.sort(key=lambda r: -r["puan"])

    PAGES.mkdir(parents=True, exist_ok=True)
    hedefler = [h for h in havuz if not (PAGES / f"{h['k']}.json").exists()][: args.adet]
    if not hedefler:
        print("tam metin: indirilecek yeni kayıt yok")
        return 0

    with cf.ThreadPoolExecutor(args.workers) as ex:
        basarili = sum(1 for ok in ex.map(indir, hedefler) if ok)
    print(f"tam metin: {basarili}/{len(hedefler)} indirildi "
          f"(toplam {len(list(PAGES.glob('*.json')))} sayfa)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
