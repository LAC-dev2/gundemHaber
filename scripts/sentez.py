#!/usr/bin/env python3
"""Haftalik sentez (Claude API).

Gunluk analizler tek tek gunu anlatir; sentez bir haftaya bakip neyin
surekli, neyin tek seferlik oldugunu soyler: hangi dosya ilerledi, hangi
egilim guclendi, hafta icinde kaynaklar birbiriyle celisti mi.

  python3 scripts/sentez.py                    # son 7 gunun sentezi
  python3 scripts/sentez.py --kuru             # istek atmadan maliyet tahmini
  python3 scripts/sentez.py --gun 2026-09-21 --zorla

Girdi: data/analiz/*.json (gunluk analizler) + data/takip.json
Cikti: data/sentez/<bitis-gunu>.json, data/sentez-latest.json,
       data/sentez-index.json

Anahtar: ANTHROPIC_API_KEY ortam degiskeni.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ANALIZ = DATA / "analiz"
SENTEZ = DATA / "sentez"
TAKIP = DATA / "takip.json"

VARSAYILAN_MODEL = "claude-opus-5"
FIYAT = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-8": (5.0, 25.0),
}
EN_AZ_GUN = 3            # bu kadar gunluk analiz yoksa sentez uretme

SISTEM = """Sen Brüksel Hukuk Merkezi'nin izleme masasında çalışan bir hukuk analistisin.
Elinde son bir haftanın günlük brifingleri ve açık takip dosyaları var. Görevin
günleri tekrar etmek değil; haftanın tamamına bakıp örüntüyü çıkarmak.

Kurallar — bunlara kesinlikle uy:
1. YALNIZCA sana verilen günlük brifinglerdeki bilgiyi kullan. Yeni olay, isim,
   tarih, dosya numarası ya da alıntı uydurma. Günlük brifingler de kaynakların
   başlık/özetlerinden üretilmiştir; kesinlik iddia etme.
2. Her değerlendirmede dayandığın günleri YYYY-AA-GG biçiminde "gunler"
   alanında göster.
3. Haftayı gün gün özetleme. Aradığın şey şu: ne süregeliyor, ne yeni başladı,
   ne sessizleşti, hangi dosya ilerledi, hangi beklenti gerçekleşmedi.
4. Bir gelişme hafta içinde yalnızca bir gün göründüyse ve devamı gelmediyse
   bunu "tek seferlik" olarak işaretle; eğilim diye sunma.
5. Günlük brifinglerin "izlenecekler" başlıkları bir beklentiydi. Hafta içinde
   karşılığı gelmeyenleri açıkça yaz — gerçekleşmeyen beklenti de bilgidir.
6. Hukuki tavsiye verme, strateji önerme. İşin gelişmeyi konumlandırmak.
7. Türkçe yaz. Kısa, kuru, mesleki bir dil kullan; gazete üslubundan kaçın.
   Sıfat yığma ve abartılı ifade yok."""

SEMA = {
    "type": "object",
    "properties": {
        "baslik": {"type": "string", "description": "Haftanın tek cümlelik başlığı, en fazla 90 karakter"},
        "ozet": {"type": "string", "description": "5-8 cümlelik haftalık değerlendirme"},
        "egilimler": {
            "type": "array",
            "description": ("Hafta boyunca birden fazla gün karşılığı olan örüntüler, "
                            "en fazla 5. Tek güne dayanan şeyleri buraya koyma."),
            "items": {
                "type": "object",
                "properties": {
                    "baslik": {"type": "string"},
                    "alan": {"type": "string"},
                    "yon": {"type": "string", "enum": ["güçleniyor", "sabit", "zayıflıyor"]},
                    "not": {"type": "string", "description": "2-4 cümle; hafta içinde nasıl seyretti"},
                    "gunler": {"type": "array", "items": {"type": "string"}},
                    "guven": {"type": "string", "enum": ["yüksek", "orta", "düşük"]},
                },
                "required": ["baslik", "alan", "yon", "not", "gunler", "guven"],
                "additionalProperties": False,
            },
        },
        "dosya_seyri": {
            "type": "array",
            "description": ("Açık takip dosyalarının hafta içindeki seyri. Yalnızca sana "
                            "verilen takip maddeleri için satır yaz."),
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "baslik": {"type": "string"},
                    "hareket": {"type": "string", "enum": ["ilerledi", "yerinde", "sessiz"]},
                    "not": {"type": "string", "description": "1-3 cümle; hareket yoksa boş"},
                    "gunler": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "baslik", "hareket", "not", "gunler"],
                "additionalProperties": False,
            },
        },
        "tek_seferlikler": {
            "type": "array",
            "description": "Hafta içinde bir gün görünüp devamı gelmeyen, yine de kayda değer gelişmeler (en fazla 4)",
            "items": {
                "type": "object",
                "properties": {
                    "baslik": {"type": "string"},
                    "gun": {"type": "string"},
                    "not": {"type": "string", "description": "1-2 cümle"},
                },
                "required": ["baslik", "gun", "not"],
                "additionalProperties": False,
            },
        },
        "karsilanmayan_beklentiler": {
            "type": "array",
            "description": ("Günlük brifinglerde 'izlenecek' denip hafta içinde karşılığı "
                            "gelmeyen başlıklar (en fazla 4)"),
            "items": {
                "type": "object",
                "properties": {
                    "beklenti": {"type": "string"},
                    "gun": {"type": "string", "description": "Beklentinin yazıldığı gün"},
                    "not": {"type": "string", "description": "1-2 cümle; hâlâ izlenmeli mi"},
                },
                "required": ["beklenti", "gun", "not"],
                "additionalProperties": False,
            },
        },
        "onumuzdeki_hafta": {
            "type": "array",
            "description": "Önümüzdeki hafta izlenmesi gereken 3-5 başlık",
            "items": {"type": "string"},
        },
    },
    "required": ["baslik", "ozet", "egilimler", "dosya_seyri", "tek_seferlikler",
                 "karsilanmayan_beklentiler", "onumuzdeki_hafta"],
    "additionalProperties": False,
}


def gunluk_analizler(bitis: str, gun_sayisi: int) -> list[dict]:
    """Bitis gunu dahil, geriye dogru gun_sayisi gunluk analizler."""
    baslangic = (datetime.fromisoformat(bitis) - timedelta(days=gun_sayisi - 1)).date().isoformat()
    cikti = []
    for yol in sorted(ANALIZ.glob("*.json")):
        if not (baslangic <= yol.stem <= bitis):
            continue
        try:
            cikti.append(json.loads(yol.read_text(encoding="utf-8")))
        except Exception:
            continue
    return cikti


def gun_blogu(d: dict) -> str:
    gun = d.get("gun", "")
    satir = [f"=== {gun} · {d.get('baslik', '')}", f"BRİFİNG: {d.get('brifing', '')}"]
    for o in d.get("one_cikanlar", []):
        satir.append(f"- ÖNE ÇIKAN [{o.get('alan', '')}, güven: {o.get('guven', '')}] "
                     f"{o.get('baslik', '')} :: {o.get('neden_onemli', '')}")
    for a in d.get("alan_notlari", []):
        if a.get("durum") == "sessiz":
            continue
        satir.append(f"- ALAN [{a.get('alan', '')}, {a.get('durum', '')}] {a.get('not', '')}")
    for s in d.get("sureklilik", []):
        if s.get("durum") == "hareket yok":
            continue
        satir.append(f"- TAKİP [{s.get('id', '')}, {s.get('durum', '')}] {s.get('not', '')}")
    izle = d.get("izlenecekler", [])
    if izle:
        satir.append("- İZLENECEK DENİLDİ: " + " | ".join(izle))
    return "\n".join(satir)


def takip_blogu() -> str:
    if not TAKIP.exists():
        return ""
    try:
        takip = json.loads(TAKIP.read_text(encoding="utf-8"))
    except Exception:
        return ""
    satir = []
    for m in takip.get("maddeler", []):
        if m.get("durum") != "açık":
            continue
        satir.append(f"- [{m['id']}] ({m.get('alan', '')}) {m['baslik']} — açıldı "
                     f"{m.get('acildi', '')}, son hareket {m.get('son_hareket', '')}, "
                     f"{len(m.get('gelismeler', []))} kayıtlı hareket")
    return "\n".join(satir)


def istem_yap(gunler: list[dict], takip: str, baslangic: str, bitis: str) -> str:
    return (
        f"Dönem: {baslangic} – {bitis} ({len(gunler)} günlük brifing)\n\n"
        + (f"AÇIK TAKİP DOSYALARI (her biri için haftalık seyri yaz)\n{takip}\n\n"
           if takip else "")
        + "GÜNLÜK BRİFİNGLER\n\n" + "\n\n".join(gun_blogu(d) for d in gunler) + "\n\n"
        + "Bu brifinglere dayanarak haftanın sentezini üret. Günleri tekrar etme; "
        + "süregelen örüntüyü, ilerleyen dosyaları, gerçekleşmeyen beklentileri yaz. "
        + "Her değerlendirmede dayandığın günleri ver."
    )


def maliyet(model: str, girdi: int, cikti: int) -> float:
    g, c = FIYAT.get(model, FIYAT[VARSAYILAN_MODEL])
    return girdi / 1e6 * g + cikti / 1e6 * c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("SENTEZ_MODEL") or VARSAYILAN_MODEL)
    ap.add_argument("--gun", default=None, help="dönemin son günü YYYY-AA-GG (öntanımlı: bugün)")
    ap.add_argument("--pencere", type=int, default=7, help="kaç günlük dönem (öntanımlı: 7)")
    ap.add_argument("--kuru", action="store_true", help="istek atma, istemi ve maliyet tahminini göster")
    ap.add_argument("--zorla", action="store_true", help="o döneme ait sentez varsa üzerine yaz")
    args = ap.parse_args()

    bitis = args.gun or datetime.now(timezone.utc).date().isoformat()
    hedef = SENTEZ / f"{bitis}.json"
    if hedef.exists() and not args.zorla:
        print(f"{bitis} sentezi zaten var (--zorla ile yenilenir).")
        return 0

    gunler = gunluk_analizler(bitis, args.pencere)
    if len(gunler) < EN_AZ_GUN:
        print(f"Sentez için yeterli günlük analiz yok ({len(gunler)}/{EN_AZ_GUN}).")
        return 0

    baslangic = gunler[0].get("gun", "")
    istem = istem_yap(gunler, takip_blogu(), baslangic, bitis)

    if args.kuru:
        print(istem[:4000])
        print(f"\n… istem {len(istem)} karakter (~{len(istem)//3.5:.0f} token), "
              f"{len(gunler)} gün, model {args.model}")
        print(f"kaba maliyet tahmini: ${maliyet(args.model, len(istem)//3.5, 2500):.3f}")
        return 0

    try:
        import anthropic
    except ImportError:
        print("anthropic paketi kurulu değil:  pip install anthropic")
        return 1

    client = anthropic.Anthropic()
    try:
        yanit = client.messages.create(
            model=args.model,
            max_tokens=8000,
            system=SISTEM,
            messages=[{"role": "user", "content": istem}],
            output_config={"format": {"type": "json_schema", "schema": SEMA}},
        )
    except anthropic.APIStatusError as hata:
        print(f"API hatası ({hata.status_code}): {hata.message}")
        return 1
    except anthropic.APIConnectionError as hata:
        print(f"Bağlantı hatası: {hata}")
        return 1

    if yanit.stop_reason == "refusal":
        print("Model isteği yanıtlamayı reddetti; sentez üretilmedi.")
        return 1

    veri = json.loads(next((b.text for b in yanit.content if b.type == "text"), ""))
    kullanim = yanit.usage
    tutar = maliyet(args.model, kullanim.input_tokens, kullanim.output_tokens)
    veri.update({
        "baslangic": baslangic,
        "bitis": bitis,
        "gun_sayisi": len(gunler),
        "kullanilan_gunler": [d.get("gun", "") for d in gunler],
        "olusturma": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "model": args.model,
        "maliyet_usd": round(tutar, 4),
        "uyari": ("Bu sentez, günlük brifinglerin kendisine dayanarak yapay zekâ ile "
                  "üretilmiştir; hukuki tavsiye değildir ve birincil kaynakta "
                  "doğrulanmadan dosyaya esas alınamaz."),
    })

    SENTEZ.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "sentez-latest.json").write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    index = sorted((p.stem for p in SENTEZ.glob("*.json")), reverse=True)
    (DATA / "sentez-index.json").write_text(json.dumps(index), encoding="utf-8")

    print(f"sentez: {baslangic} – {bitis} · {len(veri['egilimler'])} eğilim · "
          f"{len(veri['dosya_seyri'])} dosya · "
          f"{len(veri['karsilanmayan_beklentiler'])} karşılanmayan beklenti")
    print(f"token: {kullanim.input_tokens} girdi / {kullanim.output_tokens} çıktı · "
          f"maliyet ≈ ${tutar:.3f} · model {args.model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
