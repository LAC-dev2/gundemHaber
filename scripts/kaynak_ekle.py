#!/usr/bin/env python3
"""Izleme envanterine yeni kaynak ekler.

Kaynak eklendiginde: sayfa basligi ve RSS/Atom akisi otomatik bulunur,
data/sources.json'a yazilir ve bir sonraki taramada izlenmeye baslar.

  python3 scripts/kaynak_ekle.py https://ornek.org/haberler \
      --ad "Örnek Kurum" --bolge Avrupa --kategori "İnsan hakları" \
      --oncelik Yüksek --siklik Günlük --anahtar "iade, INTERPOL"

GitHub konusu (issue) govdesinden eklemek icin:
  python3 scripts/kaynak_ekle.py --konu konu.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect                                        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KAYNAKLAR = ROOT / "data" / "sources.json"

BOLGELER = ("Türkiye", "Belçika", "Avrupa", "Dünya", "Kurumsal")
ONCELIKLER = ("Kritik", "Yüksek", "Orta", "Düşük")
SIKLIKLAR = ("Günlük", "Haftalık", "Aylık", "Dönemsel", "Yıllık", "Dosya bazlı")

# GitHub konu formundaki basliklar -> alan adlari
ALAN_ESLESME = {
    "kaynak adresi": "url", "kaynak adı": "ad", "bölge": "bolge",
    "kategori": "kategori", "kaynak türü": "tur", "öncelik": "oncelik",
    "tarama sıklığı": "siklik", "kanıt değeri": "kanit",
    "anahtar terimler": "anahtar", "neden izleniyor": "neden",
}


def konu_ayristir(govde: str) -> dict:
    """GitHub konu formu govdesini alanlara cevirir."""
    alanlar: dict[str, str] = {}
    for parca in re.split(r"^###\s+", govde, flags=re.M)[1:]:
        satirlar = parca.strip().split("\n", 1)
        baslik = satirlar[0].strip().lower()
        deger = (satirlar[1].strip() if len(satirlar) > 1 else "")
        if deger.lower() in ("_no response_", "_yanıt yok_", ""):
            deger = ""
        for etiket, alan in ALAN_ESLESME.items():
            if baslik.startswith(etiket):
                alanlar[alan] = deger
    return alanlar


def sayfa_bilgisi(url: str) -> tuple[str, str]:
    """Sayfa basligi ve varsa RSS/Atom akisi."""
    baslik = ""
    try:
        _, govde = collect.fetch(url, 300_000, 12)
        m = re.search(rb"<title[^>]*>(.*?)</title>", govde[:200_000], re.I | re.S)
        if m:
            baslik = collect.clean(m.group(1).decode("utf-8", "replace"), 120)
    except Exception:
        pass
    try:
        akis = collect.discover(url) or ""
    except Exception:
        akis = ""
    return baslik, akis


def ekle(veri: dict) -> dict:
    url = (veri.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"hata": "Geçerli bir adres gerekli (http:// veya https:// ile)."}

    kaynaklar = json.loads(KAYNAKLAR.read_text(encoding="utf-8"))
    alan_adi = url.split("/")[2].replace("www.", "")
    for k in kaynaklar["sources"]:
        for mevcut in k.get("links", []):
            if alan_adi and alan_adi in mevcut:
                return {"hata": f"Bu alan adı zaten izleniyor: {k['ad']} (kayıt {k['id']}).",
                        "mevcut": k["ad"]}

    baslik, akis = sayfa_bilgisi(url)
    kayit = {
        "id": max((k["id"] for k in kaynaklar["sources"]), default=0) + 1,
        "bolge": veri.get("bolge") if veri.get("bolge") in BOLGELER else "Dünya",
        "kategori": (veri.get("kategori") or "İnsan hakları").strip(),
        "ad": (veri.get("ad") or baslik or alan_adi).strip(),
        "tur": (veri.get("tur") or "Kaynak").strip(),
        "kanit": (veri.get("kanit") or "İkincil").strip(),
        "siklik": veri.get("siklik") if veri.get("siklik") in SIKLIKLAR else "Günlük",
        "oncelik": veri.get("oncelik") if veri.get("oncelik") in ONCELIKLER else "Orta",
        "neden": (veri.get("neden") or "").strip(),
        "anahtar": (veri.get("anahtar") or "").strip(),
        "links": [url],
    }
    kaynaklar["sources"].append(kayit)
    KAYNAKLAR.write_text(json.dumps(kaynaklar, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")

    # Bulunan akis, kesif onbellegine yazilsin ki ilk taramada kullanilsin
    if akis:
        onbellek_yol = ROOT / "data" / "feeds.json"
        onbellek = json.loads(onbellek_yol.read_text(encoding="utf-8")) if onbellek_yol.exists() else {}
        onbellek[url] = {"feed": akis, "checked": collect.NOW.isoformat(timespec="seconds")}
        onbellek_yol.write_text(json.dumps(onbellek, ensure_ascii=False, indent=0, sort_keys=True),
                                encoding="utf-8")
    return {"kayit": kayit, "akis": akis, "baslik": baslik}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", default="")
    ap.add_argument("--konu", help="GitHub konu gövdesini içeren dosya (- ile stdin)")
    for alan in ("ad", "bolge", "kategori", "tur", "kanit", "siklik", "oncelik", "anahtar", "neden"):
        ap.add_argument(f"--{alan}", default="")
    args = ap.parse_args()

    if args.konu:
        govde = sys.stdin.read() if args.konu == "-" else Path(args.konu).read_text(encoding="utf-8")
        veri = konu_ayristir(govde)
    else:
        veri = {a: getattr(args, a) for a in
                ("ad", "bolge", "kategori", "tur", "kanit", "siklik", "oncelik", "anahtar", "neden")}
        veri["url"] = args.url

    sonuc = ekle(veri)
    if "hata" in sonuc:
        print(f"HATA: {sonuc['hata']}")
        return 1
    k = sonuc["kayit"]
    print(f"eklendi: #{k['id']} · {k['ad']} · {k['bolge']} / {k['kategori']} · "
          f"{k['oncelik']} · {k['siklik']}")
    print("akış: " + (sonuc["akis"] or "bulunamadı (haber aramasıyla izlenecek)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
