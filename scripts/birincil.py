#!/usr/bin/env python3
"""Birincil belgeleri indirir: AIHM kararlari ve Resmi Gazete.

Tarama, kararlari *anlatan haberleri* topluyor; bu betik kararin
kendisini getirir. Analiz boylece ikincil bir aktarima degil, mahkemenin
kendi metnine dayanabilir.

Kaynaklar:
  * HUDOC (AIHM) — Turkiye aleyhine kararlar, kabul edilemezlik
    kararlari ve Bakanlar Komitesi kararlari; madde, sonuc ve basvuru
    numarasi ile birlikte tam metin.
  * Resmi Gazete — gunun sayisinin basliklari (erisilemezse atlanir).

  python3 scripts/birincil.py                  # son 14 gun, en fazla 8 belge
  python3 scripts/birincil.py --gun-sayisi 30 --adet 12
  python3 scripts/birincil.py --liste          # indirmeden neler var, goster

Cikti:
  data/birincil/<itemid>.json   belgenin tam metni
  data/birincil-latest.json     sitede ve analizde kullanilan ozet liste
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from html.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect                                        # noqa: E402
from extract import extract as extract_text           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BIRINCIL = DATA / "birincil"

HUDOC_SORGU = "https://hudoc.echr.coe.int/app/query/results"
HUDOC_METIN = "https://hudoc.echr.coe.int/app/conversion/docx/html/body?library=ECHR&id="
HUDOC_SAYFA = "https://hudoc.echr.coe.int/eng?i="

# Ingilizce belge turlerini tutuyoruz; ayni karar Fransizca ikizi ile
# geliyor (HFJUD/HFRES54) ve ikisini birden analize vermek gereksiz.
INGILIZCE = {
    "HEJUD": "karar",                 # judgment
    "HEDEC": "kabul edilebilirlik",   # decision
    "HERES54": "icra kararı",         # Committee of Ministers resolution
    "HECOM": "komisyon",
    "HEADM": "idari karar",
}
FRANSIZCA = {"HFJUD", "HFDEC", "HFRES54", "HFCOM", "HFADM"}

RG_GUNLUK = "https://www.resmigazete.gov.tr/eskiler/{y}/{a}/{y}{a}{g}.htm"


class HudocMetin(HTMLParser):
    """HUDOC belgesini metne cevirir.

    Genel ayiklayici yalnizca paragraflari aliyor; oysa kararin hukmu
    ("Holds that there has been a violation of Article 8...") <ol><li>
    listesinde duruyor ve en onemli kisim o. Bu yuzden li ogeleri de
    blok sayilir."""

    BLOK = {"p", "li", "h1", "h2", "h3", "h4", "td"}
    ATLA = {"style", "script", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parcalar: list[str] = []
        self.tampon: list[str] = []
        self.atla = 0

    def _bosalt(self) -> None:
        metin = re.sub(r"\s+", " ", "".join(self.tampon)).strip()
        self.tampon.clear()
        if len(metin) >= 25 and metin.lower() != (self.parcalar[-1].lower() if self.parcalar else None):
            self.parcalar.append(metin)

    def handle_starttag(self, tag, attrs):
        if tag in self.ATLA:
            self.atla += 1
        elif tag in self.BLOK:
            self._bosalt()
        elif tag == "br":
            self.tampon.append(" ")

    def handle_endtag(self, tag):
        if tag in self.ATLA:
            self.atla = max(0, self.atla - 1)
        elif tag in self.BLOK:
            self._bosalt()

    def handle_data(self, veri):
        if not self.atla:
            self.tampon.append(veri)

    def bitir(self) -> list[str]:
        self._bosalt()
        return self.parcalar


def hudoc_paragraflari(govde: bytes, ctype: str = "") -> list[str]:
    cozucu = HudocMetin()
    try:
        cozucu.feed(govde.decode("utf-8", "replace"))
    except Exception:
        return []
    return cozucu.bitir()


def hudoc_listesi(baslangic: str, uzunluk: int = 30) -> list[dict]:
    """Turkiye aleyhine son belgeler (madde ve sonuc bilgisiyle)."""
    sorgu = (f'contentsitename=ECHR AND respondent="TUR" '
             f'AND kpdate>="{baslangic}"')
    alanlar = "itemid,docname,doctype,kpdate,article,conclusion,appno,importance"
    url = (f"{HUDOC_SORGU}?query={urllib.parse.quote(sorgu)}"
           f"&select={alanlar}&sort=kpdate%20Descending&start=0&length={uzunluk}")
    try:
        _, govde = collect.fetch(url, 400_000, 25)
        veri = json.loads(govde)
    except Exception as hata:
        print(f"HUDOC listesi alinamadi: {type(hata).__name__}")
        return []

    cikti, gorulen = [], set()
    for satir in veri.get("results", []):
        s = satir.get("columns", {})
        tur = s.get("doctype", "")
        if tur in FRANSIZCA or tur not in INGILIZCE:
            continue
        imza = (s.get("appno", ""), s.get("kpdate", "")[:10], tur)
        if imza in gorulen:
            continue
        gorulen.add(imza)
        cikti.append({
            "itemid": s.get("itemid", ""),
            "ad": s.get("docname", ""),
            "tur": INGILIZCE[tur],
            "doctype": tur,
            "tarih": s.get("kpdate", "")[:10],
            "maddeler": [m for m in (s.get("article") or "").split(";") if m],
            "sonuc": s.get("conclusion", ""),
            "basvuru": s.get("appno", ""),
            "onem": s.get("importance", ""),
            "url": HUDOC_SAYFA + s.get("itemid", ""),
            "kaynak": "HUDOC / AİHM",
        })
    return cikti


def hudoc_metni(kayit: dict) -> dict | None:
    """Kararin tam metnini indirir; dosyada varsa yeniden indirmez."""
    hedef = BIRINCIL / f"{kayit['itemid']}.json"
    if hedef.exists():
        try:
            return json.loads(hedef.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        ctype, govde = collect.fetch(HUDOC_METIN + kayit["itemid"], 1_200_000, 30)
    except Exception as hata:
        print(f"  {kayit['itemid']}: metin alinamadi ({type(hata).__name__})")
        return None
    paragraflar = hudoc_paragraflari(govde, ctype)
    if not paragraflar:
        return None
    belge = dict(kayit)
    belge["paragraflar"] = paragraflar
    belge["kelime"] = sum(len(p.split()) for p in paragraflar)
    belge["indirme"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    BIRINCIL.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(belge, ensure_ascii=False, indent=1), encoding="utf-8")
    return belge


def hukum_ozeti(paragraflar: list[str], bas: int = 900, son: int = 2400) -> str:
    """Kararin analize verilecek kismi: olay ozeti (bas) ve hukum (son).

    Ortadaki usul ve icerik kisimlarini atlar; hukmun kendisi metnin
    sonunda ("FOR THESE REASONS, THE COURT ... Holds") yer alir."""
    metin = "\n".join(paragraflar)
    if len(metin) <= bas + son:
        return metin
    return metin[:bas].rstrip() + "\n[…]\n" + metin[-son:].lstrip()


def resmi_gazete(gun: str) -> list[dict]:
    """Gunun Resmi Gazete basliklari. Sertifika/erisim sorununda bos doner."""
    y, a, g = gun[:4], gun[5:7], gun[8:10]
    url = RG_GUNLUK.format(y=y, a=a, g=g)
    try:
        ctype, govde = collect.fetch(url, 600_000, 20)
    except Exception as hata:
        print(f"Resmi Gazete atlandi ({type(hata).__name__}): {url}")
        return []
    paragraflar = extract_text(govde, ctype, min_chars=120)
    basliklar = [p for p in paragraflar if 25 < len(p) < 300]
    if not basliklar:
        return []
    return [{
        "itemid": f"rg-{gun}",
        "ad": f"Resmî Gazete {gun}",
        "tur": "resmî yayın",
        "tarih": gun,
        "maddeler": [],
        "sonuc": "",
        "basvuru": "",
        "url": url,
        "kaynak": "Resmî Gazete",
        "paragraflar": basliklar[:60],
        "kelime": sum(len(p.split()) for p in basliklar[:60]),
    }]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun-sayisi", type=int, default=14, help="kaç günlük pencere")
    ap.add_argument("--adet", type=int, default=8, help="tam metni indirilecek belge sayısı")
    ap.add_argument("--liste", action="store_true", help="indirmeden listeyi göster")
    ap.add_argument("--resmi-gazete", action="store_true", default=True)
    ap.add_argument("--rg-yok", dest="resmi_gazete", action="store_false")
    args = ap.parse_args()

    bugun = datetime.now(timezone.utc).date()
    baslangic = (bugun - timedelta(days=args.gun_sayisi)).isoformat()
    liste = hudoc_listesi(baslangic)
    print(f"HUDOC: {baslangic} sonrası {len(liste)} belge (Türkiye)")
    for k in liste[:12]:
        print(f"  {k['tarih']} · {k['tur']} · {k['basvuru']} · {k['ad'][:56]}"
              + (f" · md. {','.join(k['maddeler'][:3])}" if k["maddeler"] else ""))
    if args.liste:
        return 0

    belgeler = []
    for kayit in liste[: args.adet]:
        belge = hudoc_metni(kayit)
        if belge:
            belgeler.append(belge)
    print(f"tam metin indirilen: {len(belgeler)}/{min(len(liste), args.adet)}")

    if args.resmi_gazete:
        belgeler += resmi_gazete(bugun.isoformat())

    ozet = [{
        "itemid": b["itemid"], "ad": b["ad"], "tur": b["tur"], "tarih": b["tarih"],
        "maddeler": b["maddeler"], "sonuc": b["sonuc"], "basvuru": b["basvuru"],
        "url": b["url"], "kaynak": b["kaynak"], "kelime": b["kelime"],
        "giris": " ".join(b["paragraflar"][:3])[:400],
    } for b in belgeler]
    (DATA / "birincil-latest.json").write_text(json.dumps(
        {"guncelleme": datetime.now(timezone.utc).isoformat(timespec="minutes"),
         "pencere_gun": args.gun_sayisi, "belgeler": ozet},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"birincil-latest.json: {len(ozet)} belge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
