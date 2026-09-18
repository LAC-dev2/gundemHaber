#!/usr/bin/env python3
"""Esik asildiginda uyari uret.

Site gun boyu sessizce dolar; bu betik "ne zaman bakmam gerekir" sorusunu
cevaplar. Gunluk analizi ve taramayi okur, asagidaki kurallardan biri
tutarsa uyari yazar:

  1. Acil alan   — INTERPOL, iade/adli yardim ya da yaptirim alanlarinda
                   one cikan bir gelisme varsa (bu alanlarda kayit nadirdir)
  2. Dosya hareketi — acik takip dosyalarindan biri kimildadiysa
  3. Cok kaynakli — ayni gelismeyi esik sayida kaynak verdiyse
  4. Kritik kayit  — oncelik "Kritik" ve kaniti birincil olan yeni kayitlar
  5. Izleme bozuldu — akis hatasi veren kaynak sayisi esigi astiysa

Ayni uyari iki kez gonderilmez: gonderilenler data/uyari-gecmis.json'da
tutulur. Cikti:
  data/uyari-son.json   sitede gosterilen guncel uyarilar
  --cikti <dosya>       Markdown ozet (GitHub issue / Telegram govdesi)

  python3 scripts/uyari.py                     # bugunu degerlendir
  python3 scripts/uyari.py --kuru              # gecmise yazma, yalniz goster
  python3 scripts/uyari.py --cikti uyari.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GECMIS = DATA / "uyari-gecmis.json"
SON = DATA / "uyari-son.json"

# Kayit nadir oldugu icin tek gelisme bile bakmayi hak eden alanlar
ACIL_ALAN_ANAHTARLARI = ("interpol", "iade", "adli yardım", "yaptırım", "malvarlığı")
KUME_ESIK = 4            # ayni gelismeyi kac kaynak verirse uyari
SAGLIK_ESIK = 8          # kac kaynak akis hatasi verirse "izleme bozuldu"
KRITIK_ESIK = 3          # gunde kac birincil-kritik kayit uyari sayilir
SITE = "https://lac-dev2.github.io/gundemHaber/"


def oku(yol: Path, varsayilan):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception:
        return varsayilan


def acil_alan(alan: str) -> bool:
    a = (alan or "").casefold()
    return any(k in a for k in ACIL_ALAN_ANAHTARLARI)


def uyarilari_bul(gun: str) -> list[dict]:
    analiz = oku(DATA / "analiz-latest.json", None)
    latest = oku(DATA / "latest.json", {"haberler": [], "kumeler": {}})
    saglik = oku(DATA / "health.json", {})
    cikti: list[dict] = []

    if analiz and analiz.get("gun") == gun:
        for o in analiz.get("one_cikanlar", []):
            if acil_alan(o.get("alan", "")):
                cikti.append({
                    "id": f"alan:{gun}:{o['baslik'][:60]}",
                    "tur": "acil alan", "duzey": "yüksek",
                    "baslik": o["baslik"], "alan": o.get("alan", ""),
                    "not": o.get("neden_onemli", ""), "kayitlar": o.get("kayitlar", []),
                })
        acik = {t["id"]: t for t in analiz.get("takip_acik", [])}
        hareketli = [s for s in analiz.get("sureklilik", [])
                     if s.get("durum") != "hareket yok"]
        # Kapanan dosya tek basina haber; kimildayan dosya degil. On iki acik
        # dosyayla her gun bes ayri "hareket" uyarisi gurultu oluyor: kapananlar
        # ayri ayri, otekiler tek satirda toplaniyor.
        kapanan = [s for s in hareketli if s.get("durum") == "kapandı"]
        kimildayan = [s for s in hareketli if s.get("durum") != "kapandı"]
        for s in kapanan:
            m = acik.get(s.get("id", ""))
            cikti.append({
                "id": f"takip:{gun}:{s.get('id', '')}",
                "tur": "dosya kapandı", "duzey": "yüksek",
                "baslik": (m["baslik"] if m else s.get("id", "")),
                "alan": (m.get("alan", "") if m else ""),
                "not": s.get("not", ""), "kayitlar": s.get("kayitlar", []),
            })
        if len(kimildayan) == 1:
            s = kimildayan[0]
            m = acik.get(s.get("id", ""))
            cikti.append({
                "id": f"takip:{gun}:{s.get('id', '')}",
                "tur": "dosya hareketi", "duzey": "orta",
                "baslik": (m["baslik"] if m else s.get("id", "")),
                "alan": (m.get("alan", "") if m else ""),
                "not": s.get("not", ""), "kayitlar": s.get("kayitlar", []),
            })
        elif kimildayan:
            basliklar = []
            for s in kimildayan:
                m = acik.get(s.get("id", ""))
                basliklar.append((m["baslik"] if m else s.get("id", ""))[:70])
            cikti.append({
                "id": f"takip:{gun}:toplu:{len(kimildayan)}",
                "tur": "dosya hareketi", "duzey": "orta",
                "baslik": f"{len(kimildayan)} takip dosyasında hareket var",
                "alan": "",
                "not": "; ".join(basliklar),
                "kayitlar": [k for s in kimildayan for k in s.get("kayitlar", [])][:8],
            })

    bugun = [h for h in latest.get("haberler", []) if h["tarih"][:10] == gun]
    kume_kayit: dict[str, list] = {}
    for h in bugun:
        if h.get("kume") is not None:
            kume_kayit.setdefault(str(h["kume"]), []).append(h)
    for no, bilgi in (latest.get("kumeler") or {}).items():
        if bilgi.get("kaynak", 0) < KUME_ESIK or no not in kume_kayit:
            continue
        ilk = kume_kayit[no][0]
        cikti.append({
            "id": f"kume:{gun}:{no}",
            "tur": "çok kaynaklı", "duzey": "orta",
            "baslik": ilk.get("baslik_tr") or ilk["baslik"],
            "alan": ilk.get("kategori", ""),
            "not": f"Aynı gelişmeyi {bilgi['kaynak']} ayrı kaynak verdi.",
            "kayitlar": [h["k"] for h in kume_kayit[no][:6]],
        })

    kritik = [h for h in bugun
              if h.get("oncelik") == "Kritik" and str(h.get("kanit", "")).startswith("Birincil")]
    if len(kritik) >= KRITIK_ESIK:
        cikti.append({
            "id": f"kritik:{gun}:{len(kritik)}",
            "tur": "kritik kayıt yoğunluğu", "duzey": "orta",
            "baslik": f"Bugün birincil kaynaktan {len(kritik)} kritik öncelikli kayıt geldi",
            "alan": "", "not": "; ".join((h.get("baslik_tr") or h["baslik"])[:80] for h in kritik[:4]),
            "kayitlar": [h["k"] for h in kritik[:6]],
        })

    bozuk = [v.get("ad", k) for k, v in saglik.items() if v.get("hata")]
    if len(bozuk) >= SAGLIK_ESIK:
        cikti.append({
            "id": f"saglik:{gun}:{len(bozuk)}",
            "tur": "izleme bozuldu", "duzey": "yüksek",
            "baslik": f"{len(bozuk)} kaynağın akışı hata veriyor",
            "alan": "kaynak sağlığı",
            "not": "Sessizleşen kaynak, çoğu zaman kırılmış bir akıştır: "
                   + ", ".join(bozuk[:6]) + ("…" if len(bozuk) > 6 else ""),
            "kayitlar": [],
        })
    return cikti


def markdown(uyarilar: list[dict], gun: str) -> str:
    satir = [f"## Gündem Takip — {gun} uyarıları", ""]
    for u in uyarilar:
        satir.append(f"### {u['baslik']}")
        satir.append(f"*{u['tur']} · {u['duzey']} düzey"
                     + (f" · {u['alan']}" if u.get("alan") else "") + "*")
        if u.get("not"):
            satir.append("")
            satir.append(u["not"])
        satir.append("")
    satir.append(f"[Günün analizini aç]({SITE}#analiz)")
    satir.append("")
    satir.append("_Bu uyarı, taranan kaynakların kendi başlık ve özetlerine dayanır; "
                 "birincil kaynakta doğrulanmadan dosyaya esas alınamaz._")
    return "\n".join(satir)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", default=None, help="YYYY-AA-GG (öntanımlı: bugün)")
    ap.add_argument("--kuru", action="store_true", help="geçmişe yazma, yalnızca göster")
    ap.add_argument("--cikti", default=None, help="Markdown özetin yazılacağı dosya")
    ap.add_argument("--hepsi", action="store_true", help="daha önce gönderilmişleri de göster")
    args = ap.parse_args()

    gun = args.gun or datetime.now(timezone.utc).date().isoformat()
    bulunan = uyarilari_bul(gun)
    gecmis = oku(GECMIS, {"gonderilen": []})
    gonderilen = set(gecmis.get("gonderilen", []))
    yeni = bulunan if args.hepsi else [u for u in bulunan if u["id"] not in gonderilen]

    SON.write_text(json.dumps(
        {"gun": gun, "olusturma": datetime.now(timezone.utc).isoformat(timespec="minutes"),
         "uyarilar": bulunan}, ensure_ascii=False, indent=1), encoding="utf-8")

    if not yeni:
        print(f"uyarı yok ({len(bulunan)} kural tuttu, hepsi daha önce gönderilmiş)"
              if bulunan else "uyarı yok")
        cikis = os.environ.get("GITHUB_OUTPUT")
        if cikis:
            Path(cikis).open("a", encoding="utf-8").write("uyari=hayir\n")
        return 0

    metin = markdown(yeni, gun)
    if args.cikti:
        Path(args.cikti).write_text(metin, encoding="utf-8")
    else:
        print(metin)

    if not args.kuru:
        gecmis["gonderilen"] = (gecmis.get("gonderilen", []) + [u["id"] for u in yeni])[-400:]
        gecmis["guncelleme"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
        GECMIS.write_text(json.dumps(gecmis, ensure_ascii=False, indent=1), encoding="utf-8")

    cikis = os.environ.get("GITHUB_OUTPUT")
    if cikis:
        with Path(cikis).open("a", encoding="utf-8") as f:
            f.write("uyari=evet\n")
            f.write(f"baslik=Uyarı · {gun} · {yeni[0]['baslik'][:60]}"
                    + (f" (+{len(yeni) - 1})" if len(yeni) > 1 else "") + "\n")
    print(f"uyarı: {len(yeni)} yeni ({len(bulunan)} toplam)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
