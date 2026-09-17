#!/usr/bin/env python3
"""Gunluk analiz uretimi (Claude API).

Taramadan cikan kayitlari, Bruksel Hukuk Merkezi'nin calisma alanlarina gore
degerlendiren gunluk bir brifing uretir: gunun ozeti, one cikan gelismeler ve
neden onemli olduklari, alan alan durum notlari, izlenecekler.

  python3 scripts/analiz.py                  # bugunun analizini uret
  python3 scripts/analiz.py --kuru           # istek atmadan maliyeti tahmin et
  python3 scripts/analiz.py --model claude-sonnet-5
  python3 scripts/analiz.py --gun 2026-09-16 --zorla

Anahtar: ANTHROPIC_API_KEY ortam degiskeni (ya da `ant auth login` profili).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ANALIZ = DATA / "analiz"
PAGES = DATA / "pages"
TAKIP = DATA / "takip.json"          # dosya takibi: açık maddeler ve seyri
GECMIS_GUN = 7                       # kaç günün analizi hafızaya verilir
TAM_METIN_UST = 15                   # kaç kayıt için uzun metin gönderilir

VARSAYILAN_MODEL = "claude-opus-5"
# 1M token basina USD (girdi, cikti)
FIYAT = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-8": (5.0, 25.0),
}

# Merkezin calisma alanlari (brusselslawoffice.com) + izleme dosyalari
ALANLAR = [
    "AİHM başvuruları ve kararların icrası",
    "BM insan hakları mekanizmaları",
    "INTERPOL bildirimleri ve kırmızı bülten",
    "İade, adli yardım ve iltica",
    "Yaptırım listeleri ve malvarlığı dondurma",
    "Gülen hareketi/KHK dosyaları ve sınıraşan baskı",
    "İfade ve basın özgürlüğü",
    "Belçika ve AB mevzuatı",
]

SISTEM = """Sen Brüksel Hukuk Merkezi'nin izleme masasında çalışan bir hukuk analistisin.
Merkez; AİHM başvuruları, BM insan hakları mekanizmaları, INTERPOL bildirimleri,
iade–adli yardım–iltica dosyaları, yaptırım listeleri ve Gülen hareketi/KHK
kaynaklı sınıraşan baskı vakaları üzerinde çalışır.

Görevin: günün taranmış kayıtlarını okuyup, merkezin dosyaları açısından ne
anlama geldiğini anlatan kısa bir brifing yazmak.

Kurallar — bunlara kesinlikle uy:
1. YALNIZCA sana verilen kayıtlardaki bilgiyi kullan. Kayıtlarda olmayan bir
   olay, isim, tarih, dosya numarası veya alıntı uydurma. Bilgi eksikse
   "kayıtlarda yalnızca başlık düzeyinde bilgi var" de.
2. Her değerlendirmede dayandığın kayıtları [k] anahtarlarıyla göster.
3. Kesinlik iddia etme. Bir çıkarım yapıyorsan "güven" alanını dürüstçe işaretle
   ve neye dayandığını yaz. Başlıklar kaynağın kendi ifadesidir; doğrulanmamıştır.
4. Hukuki tavsiye verme, strateji önerme, dava tavsiyesi yazma. Yaptığın iş
   gelişmeyi konumlandırmak ve neden izlenmesi gerektiğini söylemektir.
5. Türkçe yaz. Kısa, kuru, mesleki bir dil kullan; gazete üslubundan kaçın.
   Sıfat yığma, "kritik gelişme" gibi abartılı ifadeler kullanma.
6. Bir gelişme merkezin alanlarıyla ilgisizse listeleme. Az ve isabetli olsun.
7. Sana önceki günlerin başlıkları ve açık takip maddeleri verilecek. Bugünü
   dünden kopuk anlatma: süregelen bir olayda "kaçıncı gün", "önceki adıma göre
   ne değişti" bilgisini ver. Önceki günlerin verisi elinde yoktur; yalnızca
   başlıklarını görürsün, o yüzden oradan olgu üretme.
8. Kaynaklar aynı olayda farklı sayı, tarih ya da isim veriyorsa bunu açıkça
   yaz ("kaynaklar 53 ile 62 arasında sayı veriyor") ve hangisinin hangi kayıtta
   olduğunu göster. Tek bir sayıya indirgeme."""

SEMA = {
    "type": "object",
    "properties": {
        "sureklilik": {
            "type": "array",
            "description": ("Açık takip maddelerinin bugünkü durumu. Yalnızca sana verilen "
                            "takip maddeleri için satır yaz; kayıtlarda o maddeye ilişkin "
                            "bir şey yoksa durum 'hareket yok' olur ve not boş kalır."),
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Takip maddesinin id'si"},
                    "durum": {"type": "string", "enum": ["hareket var", "hareket yok", "kapandı"]},
                    "not": {"type": "string", "description": "Hareket varsa 1-3 cümle; yoksa boş"},
                    "kayitlar": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "durum", "not", "kayitlar"],
                "additionalProperties": False,
            },
        },
        "yeni_takip": {
            "type": "array",
            "description": ("Bugün açılması gereken yeni takip maddeleri (en fazla 4). "
                            "Zaten açık bir maddeyle aynı konuyu tekrarlamayan, "
                            "önümüzdeki günlerde seyri izlenmesi gerekenler."),
            "items": {
                "type": "object",
                "properties": {
                    "baslik": {"type": "string", "description": "Takip edilecek konu, tek cümle"},
                    "alan": {"type": "string"},
                    "neden": {"type": "string", "description": "Neden izlenmeli, 1-2 cümle"},
                    "kayitlar": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["baslik", "alan", "neden", "kayitlar"],
                "additionalProperties": False,
            },
        },
        "baslik": {"type": "string", "description": "Günün tek cümlelik başlığı, en fazla 90 karakter"},
        "brifing": {"type": "string", "description": "3-5 cümlelik genel değerlendirme"},
        "one_cikanlar": {
            "type": "array",
            "description": "En fazla 6 gelişme, önem sırasına göre",
            "items": {
                "type": "object",
                "properties": {
                    "baslik": {"type": "string"},
                    "alan": {"type": "string", "description": "İlgili çalışma alanı"},
                    "neden_onemli": {"type": "string", "description": "2-4 cümle; merkezin dosyaları açısından anlamı"},
                    "kayitlar": {"type": "array", "items": {"type": "string"}, "description": "Dayanılan kayıt anahtarları"},
                    "guven": {"type": "string", "enum": ["yüksek", "orta", "düşük"]},
                },
                "required": ["baslik", "alan", "neden_onemli", "kayitlar", "guven"],
                "additionalProperties": False,
            },
        },
        "alan_notlari": {
            "type": "array",
            "description": "Yalnızca o gün kayıt gelen alanlar",
            "items": {
                "type": "object",
                "properties": {
                    "alan": {"type": "string"},
                    "durum": {"type": "string", "enum": ["hareketli", "olağan", "sessiz"]},
                    "not": {"type": "string", "description": "1-3 cümle"},
                    "kayitlar": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["alan", "durum", "not", "kayitlar"],
                "additionalProperties": False,
            },
        },
        "izlenecekler": {
            "type": "array",
            "description": "Önümüzdeki günlerde takip edilmesi gereken 2-5 başlık",
            "items": {"type": "string"},
        },
    },
    "required": ["baslik", "brifing", "one_cikanlar", "alan_notlari", "izlenecekler",
                 "sureklilik", "yeni_takip"],
    "additionalProperties": False,
}


def kisalt(metin: str, n: int) -> str:
    metin = re.sub(r"\s+", " ", metin or "").strip()
    return metin[:n].rstrip() + ("…" if len(metin) > n else "")


def kayitlari_sec(haberler: list[dict], gun: str, adet: int) -> list[dict]:
    """Analize girecek kayıtlar: o gün ve bir önceki günün en yüksek puanlıları."""
    sinir = (datetime.fromisoformat(gun) - timedelta(days=1)).date().isoformat()
    havuz = [h for h in haberler if h["tarih"][:10] >= sinir]
    if not havuz:
        havuz = haberler[: adet * 2]
    # küme temsilcisi dışındaki tekrarları ele
    gorulen, secilen = set(), []
    for h in sorted(havuz, key=lambda x: x["puan"], reverse=True):
        if h.get("kume") is not None:
            if h["kume"] in gorulen:
                continue
            gorulen.add(h["kume"])
        secilen.append(h)
        if len(secilen) >= adet:
            break
    return secilen


def kayit_metni(h: dict, kumeler: dict, tam_metin: bool, uzun: bool = False) -> str:
    satir = [f"[{h['k']}] {h['bolge']} · {h.get('kategori', '')} · {h['kaynak']}"
             f" ({h.get('kanit', '')}, öncelik: {h.get('oncelik', '')}, {h['tarih'][:16]})",
             f"  BAŞLIK: {h['baslik']}"]
    if h.get("ozet"):
        satir.append(f"  ÖZET: {kisalt(h['ozet'], 300)}")
    if h.get("kume") is not None:
        bilgi = kumeler.get(str(h["kume"])) or kumeler.get(h["kume"])
        if bilgi:
            satir.append(f"  DOĞRULAMA: aynı gelişmeyi {bilgi['kaynak']} kaynak verdi")
    if tam_metin:
        sayfa = PAGES / f"{h['k']}.json"
        if sayfa.exists():
            try:
                paras = json.loads(sayfa.read_text(encoding="utf-8"))["paragraflar"]
                govde = " ".join(p for p in paras if not p.startswith("## "))
                satir.append(f"  METİN: {kisalt(govde, 2600 if uzun else 700)}")
            except Exception:
                pass
    return "\n".join(satir)


def gecmis_ozeti() -> str:
    """Onceki gunlerin basliklari: sureklilik icin hafiza."""
    gunler = sorted((p for p in ANALIZ.glob("*.json")), reverse=True)[:GECMIS_GUN]
    satirlar = []
    for yol in gunler:
        try:
            d = json.loads(yol.read_text(encoding="utf-8"))
        except Exception:
            continue
        basliklar = "; ".join(o["baslik"] for o in d.get("one_cikanlar", [])[:4])
        satirlar.append(f"- {d.get('gun', yol.stem)}: {d.get('baslik', '')}"
                        + (f" | öne çıkanlar: {basliklar}" if basliklar else ""))
    return "\n".join(satirlar)


def takip_oku() -> dict:
    if TAKIP.exists():
        try:
            return json.loads(TAKIP.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"maddeler": []}


def takip_ozeti(takip: dict) -> str:
    acik = [m for m in takip.get("maddeler", []) if m.get("durum") == "açık"]
    if not acik:
        return ""
    satirlar = []
    for m in acik:
        son = m.get("son_hareket") or m.get("acildi", "")
        satirlar.append(f"- [{m['id']}] ({m.get('alan', '')}) {m['baslik']} "
                        f"— açıldı {m.get('acildi', '')}, son hareket {son}")
    return "\n".join(satirlar)


def istem_yap(secilen: list[dict], kumeler: dict, gun: str, tam_metin: bool,
              gecmis: str = "", takip: str = "") -> str:
    bloklar = [kayit_metni(h, kumeler, tam_metin, uzun=(i < TAM_METIN_UST))
               for i, h in enumerate(sorted(secilen, key=lambda r: -r["puan"]))]
    return (
        f"Tarih: {gun}\n"
        + (f"\nÖNCEKİ GÜNLERİN BAŞLIKLARI (yalnızca süreklilik için; "
           f"buradan olgu üretme)\n{gecmis}\n" if gecmis else "")
        + (f"\nAÇIK TAKİP MADDELERİ (her biri için bugünkü durumu yaz)\n{takip}\n"
           if takip else "")
        + f"\nAşağıda son taramadan gelen {len(secilen)} kayıt var. Her kaydın başında "
        + "köşeli parantez içinde anahtarı yazıyor.\n\n"
        + "Merkezin çalışma alanları:\n" + "\n".join(f"- {a}" for a in ALANLAR) + "\n\n"
        + "KAYITLAR\n" + "\n\n".join(bloklar) + "\n\n"
        + "Bu kayıtlara dayanarak günün brifingini üret. Yalnızca verilen kayıtlardaki "
        + "bilgiyi kullan, her değerlendirmede dayandığın kayıt anahtarlarını ver ve "
        + "açık takip maddelerinin bugünkü durumunu yaz."
    )


def takip_guncelle(takip: dict, veri: dict, gun: str) -> dict:
    """Takip listesini gunun analiziyle gunceller: hareketleri isler, yeni
    maddeleri acar, uzun suredir hareketsiz maddeleri kapatir."""
    maddeler = takip.setdefault("maddeler", [])
    indeks = {m["id"]: m for m in maddeler}

    for satir in veri.get("sureklilik", []):
        m = indeks.get(satir.get("id", ""))
        if not m:
            continue
        if satir["durum"] == "kapandı":
            m["durum"] = "kapandı"
            m["kapandi"] = gun
        if satir["durum"] in ("hareket var", "kapandı") and satir.get("not", "").strip():
            m["son_hareket"] = gun
            m.setdefault("gelismeler", []).append(
                {"gun": gun, "not": satir["not"], "kayitlar": satir.get("kayitlar", [])})

    sayac = max((int(m["id"][1:]) for m in maddeler if m["id"][1:].isdigit()), default=0)
    for yeni in veri.get("yeni_takip", [])[:4]:
        sayac += 1
        maddeler.append({
            "id": f"t{sayac}", "baslik": yeni["baslik"], "alan": yeni.get("alan", ""),
            "neden": yeni.get("neden", ""), "acildi": gun, "durum": "açık",
            "son_hareket": gun, "kayitlar": yeni.get("kayitlar", []), "gelismeler": [],
        })

    for m in maddeler:                                  # hareketsiz maddeleri kapat
        if m.get("durum") != "açık":
            continue
        son = m.get("son_hareket") or m.get("acildi")
        try:
            gecen = (datetime.fromisoformat(gun) - datetime.fromisoformat(son)).days
        except Exception:
            continue
        if gecen > 45:
            m["durum"] = "kapandı"
            m["kapandi"] = gun
            m["kapanma_nedeni"] = "45 gündür hareket yok"

    takip["guncelleme"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    takip["acik"] = sum(1 for m in maddeler if m.get("durum") == "açık")
    TAKIP.write_text(json.dumps(takip, ensure_ascii=False, indent=1), encoding="utf-8")
    return takip


def maliyet(model: str, girdi: int, cikti: int) -> float:
    g, c = FIYAT.get(model, FIYAT[VARSAYILAN_MODEL])
    return girdi / 1e6 * g + cikti / 1e6 * c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("ANALIZ_MODEL") or VARSAYILAN_MODEL)
    ap.add_argument("--adet", type=int, default=45, help="analize girecek kayıt sayısı")
    ap.add_argument("--gun", default=None, help="YYYY-AA-GG (öntanımlı: bugün)")
    ap.add_argument("--kuru", action="store_true", help="istek atma, yalnızca istemi ve maliyet tahminini göster")
    ap.add_argument("--zorla", action="store_true", help="o güne ait analiz varsa üzerine yaz")
    ap.add_argument("--tam-metin", action="store_true", default=True)
    ap.add_argument("--kisa", dest="tam_metin", action="store_false", help="tam metinleri isteme (daha ucuz)")
    args = ap.parse_args()

    latest = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    gun = args.gun or datetime.now(timezone.utc).date().isoformat()
    hedef = ANALIZ / f"{gun}.json"
    if hedef.exists() and not args.zorla:
        print(f"{gun} analizi zaten var (--zorla ile yenilenir).")
        return 0

    secilen = kayitlari_sec(latest["haberler"], gun, args.adet)
    if len(secilen) < 3:
        print("Analiz için yeterli kayıt yok.")
        return 0
    takip = takip_oku()
    istem = istem_yap(secilen, latest.get("kumeler", {}), gun, args.tam_metin,
                      gecmis=gecmis_ozeti(), takip=takip_ozeti(takip))

    if args.kuru:
        print(istem[:4000])
        print(f"\n… istem {len(istem)} karakter (~{len(istem)//3.5:.0f} token), "
              f"{len(secilen)} kayıt, model {args.model}")
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
        print("Model isteği yanıtlamayı reddetti; analiz üretilmedi.")
        return 1

    metin = next((b.text for b in yanit.content if b.type == "text"), "")
    veri = json.loads(metin)

    kullanim = yanit.usage
    tutar = maliyet(args.model, kullanim.input_tokens, kullanim.output_tokens)
    veri.update({
        "gun": gun,
        "olusturma": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "model": args.model,
        "kayit_sayisi": len(secilen),
        "kullanilan_kayitlar": [h["k"] for h in secilen],
        "maliyet_usd": round(tutar, 4),
        "uyari": ("Bu değerlendirme, taranan kaynakların kendi başlık ve özetlerine dayanarak "
                  "yapay zekâ ile üretilmiştir; hukuki tavsiye değildir ve birincil kaynakta "
                  "doğrulanmadan dosyaya esas alınamaz."),
    })

    takip = takip_guncelle(takip, veri, gun)
    veri["takip_acik"] = [
        {"id": m["id"], "baslik": m["baslik"], "alan": m.get("alan", ""),
         "acildi": m.get("acildi", ""), "son_hareket": m.get("son_hareket", ""),
         "hareket_sayisi": len(m.get("gelismeler", []))}
        for m in takip["maddeler"] if m.get("durum") == "açık"
    ]

    ANALIZ.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "analiz-latest.json").write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    index = sorted((p.stem for p in ANALIZ.glob("*.json")), reverse=True)
    (DATA / "analiz-index.json").write_text(json.dumps(index), encoding="utf-8")

    hareketli = sum(1 for x in veri.get("sureklilik", []) if x["durum"] != "hareket yok")
    print(f"analiz: {gun} · {len(veri['one_cikanlar'])} öne çıkan · "
          f"{len(veri['alan_notlari'])} alan notu · "
          f"takip: {len(veri.get('takip_acik', []))} açık ({hareketli} hareket), "
          f"{len(veri.get('yeni_takip', []))} yeni")
    print(f"token: {kullanim.input_tokens} girdi / {kullanim.output_tokens} çıktı · "
          f"maliyet ≈ ${tutar:.3f} · model {args.model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
