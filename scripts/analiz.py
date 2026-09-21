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
BIRINCIL = DATA / "birincil"         # AİHM kararlarının kendi metni
BIRINCIL_LISTE = DATA / "birincil-latest.json"
BIRINCIL_UST = 6                     # isteme kaç birincil belge girsin
GECMIS_GUN = 7                       # kaç günün analizi hafızaya verilir
TAM_METIN_UST = 15                   # kaç kayıt için uzun metin gönderilir

VARSAYILAN_MODEL = "claude-opus-5"
# 1M token basina USD (girdi, cikti)
FIYAT = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-fable-5-1": (10.0, 50.0),     # en yetenekli model, iki kat fiyat
    "claude-fable-5": (10.0, 50.0),
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
   olduğunu göster. Tek bir sayıya indirgeme.
11. MERKEZİN ALANLARI ÖNCE GELİR. Günün başlığı ve öne çıkan gelişmeler
   merkezin çalışma alanlarından birine ait olmalı. Merkezin dosyalarıyla
   ilgisi olmayan bir kayıt (genel bir Europol duyurusu, başka bir ülkeye
   dair rutin haber, teknik bir ağ toplantısı) manşet olamaz; en çok alan
   notlarında tek cümleyle geçer. Çekirdek alanlarda bugün yeni bir şey
   yoksa manşet, derinleştirdiğin dosyayı anlatsın.
12. DÜNÜN ANALİZİNİ TEKRAR ETME. Sana önceki günün öne çıkanları verilir.
   Aynı dosyayı yeniden yazıyorsan "yenilik" alanında bugün tam olarak neyin
   değiştiğini söyle (yeni sayı, yeni karar, yeni belge, yeni taraf). Hiçbir
   şey değişmediyse o gelişmeyi öne çıkarma; onun yerine "dosya_derinlesmesi"
   bölümünde bir dosyayı derinleştir: elimizde ne var, hangi belge eksik,
   hangi adım izlenmeli, merkezin hangi argümanına dayanak olur. Güncellenen
   sayı önemlidir ama yeni bir okuma daha değerlidir.
13. AYNI DOSYAYI YENİDEN DERİNLEŞTİRME. Hafızada "SON GÜNLERDE
   DERİNLEŞTİRİLEN DOSYALAR" listesi var; o listedeki bir dosyayı tekrar
   seçme, merkezin açık takip maddelerinden henüz derinleştirilmemiş
   birini al. Tek istisna: o dosyada bugün gerçekten yeni bir belge ya da
   usul adımı varsa — o zaman "elimizde" alanının İLK CÜMLESİ neyin yeni
   olduğunu söylesin, gerisi eski özetin tekrarı olmasın. Derinleştirmeye
   değer hiçbir dosya kalmadıysa listeyi boş bırak; aynı dosyayı yeniden
   yazmaktansa hiç yazmamak yeğdir.
10. Her kayıt "BUGÜNE AİT" ya da "ÖNCEKİ GÜNDEN" diye işaretlidir. Önceki
   günün kaydını bugünün gelişmesi gibi sunma. Bugüne ait kayıt azsa ya da
   yeni bir şey yoksa bunu açıkça söyle — "bugün şu dosyada yeni kayıt yok,
   sayılar dünkü düzeyde" demek, dünkü rakamları tekrar etmekten daha
   değerlidir. Günün başlığı bugün olan bir şeyi anlatmalı.
9. BİRİNCİL BELGELER bölümünde AİHM kararlarının kendi metni verilir (HUDOC).
   Bunlar haber kayıtlarından üstündür: bir haber kararı yanlış aktarıyorsa
   kararın metnine uy ve farkı açıkça yaz. Birincil belgeye dayanan
   değerlendirmede güveni "yüksek" verebilirsin; haber başlığına dayananda
   veremezsin. Karar metninden alıntı yaparken madde numarasını, ihlal bulunup
   bulunmadığını ve hükmedilen tutarı metinde ne yazıyorsa öyle ver."""

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
        "birincil_notlar": {
            "type": "array",
            "description": ("BİRİNCİL BELGELER bölümünde verilen AİHM kararları için notlar. "
                            "Yalnızca sana verilen belgeler için satır yaz; belge yoksa boş dizi."),
            "items": {
                "type": "object",
                "properties": {
                    "itemid": {"type": "string", "description": "Belgenin HUDOC kimliği"},
                    "baslik": {"type": "string", "description": "Kararın konusu, tek cümle"},
                    "maddeler": {"type": "array", "items": {"type": "string"},
                                 "description": "İhlal incelenen maddeler, belgede yazdığı gibi"},
                    "ne_dedi": {"type": "string",
                                "description": "Mahkeme ne karar verdi: ihlal bulundu mu, hangi "
                                               "gerekçeyle, hükmedilen tutar. 2-4 cümle, metne bağlı"},
                    "merkez_icin": {"type": "string",
                                    "description": "Merkezin dosyaları açısından anlamı, 1-3 cümle"},
                    "haberle_fark": {"type": "string",
                                     "description": "Haber kayıtları kararı yanlış aktarıyorsa fark; "
                                                    "yoksa boş"},
                },
                "required": ["itemid", "baslik", "maddeler", "ne_dedi", "merkez_icin", "haberle_fark"],
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
                    "yenilik": {"type": "string", "maxLength": 300,
                                "description": ("Bu gelişme dünkü analizde de geçtiyse BUGÜN ne "
                                                "değişti (yeni sayı, karar, belge, taraf). İlk kez "
                                                "yazılıyorsa 'ilk kez' de. Tek cümle.")},
                    "ayrintilar": {
                        "type": "array",
                        "description": ("Kayıtlarda geçen somut veriler: sayı, tarih, isim, dosya "
                                        "numarası, tutar. Her madde tek satır ve kayda bağlı. "
                                        "Kayıtlarda somut veri yoksa boş dizi."),
                        "items": {"type": "string"},
                    },
                    "mekanizma": {"type": "string", "maxLength": 70,
                                  "description": ("KISA ETİKET (en fazla 70 karakter, cümle değil): "
                                                  "devrede olan hukuki mekanizma, örneğin "
                                                  "'AİHS md. 10' ya da 'INTERPOL kırmızı bülten'. "
                                                  "Kayıt anahtarı yazma, gerekçe yazma. "
                                                  "Kayıtlardan çıkmıyorsa boş bırak.")},
                    "karsi_okuma": {"type": "string",
                                    "description": ("Bu kayıtların KANITLAMADIĞI şey: hangi çıkarım "
                                                    "yapılamaz, ne doğrulanmamıştır. 1-2 cümle.")},
                    "kayitlar": {"type": "array", "items": {"type": "string"}, "description": "Dayanılan kayıt anahtarları"},
                    "guven": {"type": "string", "enum": ["yüksek", "orta", "düşük"]},
                },
                "required": ["baslik", "alan", "neden_onemli", "yenilik", "ayrintilar",
                             "mekanizma", "karsi_okuma", "kayitlar", "guven"],
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
        "dosya_derinlesmesi": {
            "type": "array",
            "description": ("Çekirdek alanlarda bugün yeni kayıt yoksa ya da gün zayıfsa, "
                            "merkezin açık dosyalarından BİRİNİ derinleştir. Gün doluysa "
                            "boş dizi bırak. En fazla bir madde."),
            "items": {
                "type": "object",
                "properties": {
                    "baslik": {"type": "string", "description": "Derinleştirilen dosya, tek cümle"},
                    "alan": {"type": "string"},
                    "elimizde": {"type": "string",
                                 "description": "Kayıtlardan ve belgelerden bugüne kadar bilinenler, 2-4 cümle"},
                    "eksik": {"type": "string",
                              "description": "Hangi belge ya da bilgi yok; neyi doğrulayamıyoruz, 1-3 cümle"},
                    "izlenecek_adim": {"type": "string",
                                       "description": "Sırada hangi usul adımı var, ne zaman beklenir, 1-2 cümle"},
                    "dayanak": {"type": "string",
                                "description": "Merkezin hangi argümanına dayanak olabilir, 1-2 cümle"},
                    "kayitlar": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["baslik", "alan", "elimizde", "eksik", "izlenecek_adim",
                             "dayanak", "kayitlar"],
                "additionalProperties": False,
            },
        },
        "kronoloji": {
            "type": "array",
            "description": ("Günün ana dosyasında (en çok kayıt gelen süregelen olay) adım adım "
                            "seyir. Önceki günlerin başlıklarından ve bugünün kayıtlarından "
                            "kurulabiliyorsa 3-6 adım; kurulamıyorsa boş dizi."),
            "items": {
                "type": "object",
                "properties": {
                    "tarih": {"type": "string", "description": "YYYY-AA-GG ya da kayıtta geçen tarih"},
                    "adim": {"type": "string", "description": "O tarihte ne oldu, tek cümle"},
                    "kayitlar": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["tarih", "adim", "kayitlar"],
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
                 "sureklilik", "yeni_takip", "birincil_notlar", "kronoloji",
                 "dosya_derinlesmesi"],
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


def kayit_metni(h: dict, kumeler: dict, tam_metin: bool, uzun: bool = False,
                gun: str = "") -> str:
    # Analize giren kayitlarin cogu onceki gunden devredebiliyor (18 Eylul'de
    # 45 kaydin yalnizca 12'si o gune aitti). Model hangisinin yeni oldugunu
    # tarihten cikarmak zorunda kalmasin diye acikca isaretliyoruz.
    yas = ""
    if gun:
        kgun = h["tarih"][:10]
        yas = " · BUGÜNE AİT" if kgun == gun else f" · ÖNCEKİ GÜNDEN ({kgun})"
    satir = [f"[{h['k']}] {h['bolge']} · {h.get('kategori', '')} · {h['kaynak']}"
             f" ({h.get('kanit', '')}, öncelik: {h.get('oncelik', '')}, {h['tarih'][:16]}){yas}",
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


def ilk_cumle(metin: str, n: int = 220) -> str:
    metin = re.sub(r"\s+", " ", metin or "").strip()
    nokta = metin.find(". ")
    if 0 < nokta < n:
        return metin[: nokta + 1]
    return kisalt(metin, n)


def gecmis_ozeti() -> str:
    """Onceki gunlerin analizleri: sureklilik ve TEKRAR ONLEME icin hafiza.

    Dun ne yazildigini yalnizca baslik duzeyinde gormek yetmiyordu; ayni
    dosya ertesi gun neredeyse ayni cumlelerle yeniden yaziliyordu. Bir
    onceki gunun one cikanlari, degerlendirmenin ilk cumlesiyle birlikte
    veriliyor ki model neyi tekrar etmemesi gerektigini bilsin.

    Derinlestirilen dosyalar ayri bir liste halinde veriliyor. Once
    yalnizca bir onceki gunun derinlesmesi gorunuyordu; 21 Eylul analizi
    bu yuzden 19 Eylul'de derinlestirilen Benli dosyasini neredeyse ayni
    icerikle yeniden derinlestirdi (arada 20 Eylul'un baska bir dosyayi
    almis olmasi yetmisti). Artik pencerenin tamami gosteriliyor."""
    gunler = sorted((p for p in ANALIZ.glob("*.json")), reverse=True)[:GECMIS_GUN]
    satirlar: list[str] = []
    derinlesenler: list[str] = []
    for sira, yol in enumerate(gunler):
        try:
            d = json.loads(yol.read_text(encoding="utf-8"))
        except Exception:
            continue
        gun = d.get("gun", yol.stem)
        if sira == 0:                       # en son gun: ayrintili
            satirlar.append(f"- {gun} (BİR ÖNCEKİ ANALİZ): {d.get('baslik', '')}")
            for o in d.get("one_cikanlar", []):
                satirlar.append(f"    · {o.get('baslik', '')} — "
                                f"{ilk_cumle(o.get('neden_onemli', ''))}")
        else:
            basliklar = "; ".join(o["baslik"] for o in d.get("one_cikanlar", [])[:4])
            satirlar.append(f"- {gun}: {d.get('baslik', '')}"
                            + (f" | öne çıkanlar: {basliklar}" if basliklar else ""))
        for dd in d.get("dosya_derinlesmesi", []) or []:
            derinlesenler.append(f"- {gun}: {dd.get('baslik', '')}")

    if derinlesenler:
        satirlar.append("")
        satirlar.append("SON GÜNLERDE DERİNLEŞTİRİLEN DOSYALAR — bunları yeniden "
                        "derinleştirme, başka bir dosya seç:")
        satirlar.extend(derinlesenler)
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


def birincil_blogu() -> str:
    """AIHM kararlarinin kendi metni: haber kayitlarindan ustun kaynak.

    birincil.py HUDOC'tan indirir; burada yalnizca okunur. Her belgeden
    olay ozeti ve hukum kismi verilir (ortasi atlanir)."""
    if not BIRINCIL_LISTE.exists():
        return ""
    try:
        liste = json.loads(BIRINCIL_LISTE.read_text(encoding="utf-8")).get("belgeler", [])
    except Exception:
        return ""
    bloklar = []
    for ozet in liste[:BIRINCIL_UST]:
        yol = BIRINCIL / f"{ozet['itemid']}.json"
        if not yol.exists():
            continue
        try:
            belge = json.loads(yol.read_text(encoding="utf-8"))
        except Exception:
            continue
        basliklar = [
            f"[{belge['itemid']}] {belge['kaynak']} · {belge['tur']} · {belge['tarih']}",
            f"  BELGE: {belge['ad']}",
        ]
        if belge.get("basvuru"):
            basliklar.append(f"  BAŞVURU NO: {belge['basvuru']}")
        if belge.get("maddeler"):
            basliklar.append(f"  MADDELER: {', '.join(belge['maddeler'])}")
        if belge.get("sonuc"):
            basliklar.append(f"  SONUÇ (HUDOC alanı): {kisalt(belge['sonuc'], 320)}")
        basliklar.append("  METİN:\n" + birincil_metin(belge.get("paragraflar", [])))
        bloklar.append("\n".join(basliklar))
    return "\n\n".join(bloklar)


def birincil_metin(paragraflar: list[str], bas: int = 900, son: int = 2400) -> str:
    """Olay ozeti (bas) ve hukum (son); ortadaki usul kismi atlanir."""
    metin = "\n".join(paragraflar)
    if len(metin) <= bas + son:
        return metin
    return metin[:bas].rstrip() + "\n[… ara bölümler atlandı …]\n" + metin[-son:].lstrip()


def istem_yap(secilen: list[dict], kumeler: dict, gun: str, tam_metin: bool,
              gecmis: str = "", takip: str = "", birincil: str = "") -> str:
    bloklar = [kayit_metni(h, kumeler, tam_metin, uzun=(i < TAM_METIN_UST), gun=gun)
               for i, h in enumerate(sorted(secilen, key=lambda r: -r["puan"]))]
    bugunku = sum(1 for h in secilen if h["tarih"][:10] == gun)
    return (
        f"Tarih: {gun}\n"
        f"Kayıtların {bugunku}/{len(secilen)} tanesi bugüne ait, kalanı önceki "
        f"günlerden devretti.\n"
        + (f"\nÖNCEKİ GÜNLERİN ANALİZLERİ — bunları TEKRAR ETME. Aynı dosyayı "
           f"yeniden yazıyorsan bugün ne değiştiğini söyle; hiçbir şey değişmediyse "
           f"öne çıkarma, derinleştir. (Buradan olgu üretme; yalnızca ne yazıldığını "
           f"gösterir.)\n{gecmis}\n" if gecmis else "")
        + (f"\nAÇIK TAKİP MADDELERİ (her biri için bugünkü durumu yaz)\n{takip}\n"
           if takip else "")
        + (f"\nBİRİNCİL BELGELER — mahkemenin kendi metni; haber kayıtlarından üstündür\n"
           f"{birincil}\n" if birincil else "")
        + f"\nAşağıda son taramadan gelen {len(secilen)} kayıt var. Her kaydın başında "
        + "köşeli parantez içinde anahtarı yazıyor.\n\n"
        + "Merkezin çalışma alanları:\n" + "\n".join(f"- {a}" for a in ALANLAR) + "\n\n"
        + "KAYITLAR\n" + "\n\n".join(bloklar) + "\n\n"
        + "Bu kayıtlara dayanarak günün brifingini üret. Yalnızca verilen kayıtlardaki "
        + "bilgiyi kullan, her değerlendirmede dayandığın kayıt anahtarlarını ver ve "
        + "açık takip maddelerinin bugünkü durumunu yaz. Birincil belge verildiyse "
        + "her biri için ayrı bir not yaz: mahkeme ne dedi, merkezin dosyaları için ne "
        + "anlama geliyor, haber kayıtları kararı doğru aktarmış mı."
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


DENETIM_YEDEK = "claude-haiku-4-5"   # denetim modeli erisilemezse

DENETIM_SISTEM = """Sen bir hukuk analizini denetleyen ikinci okuyucusun. Elinde bir
brifingin iddialari ve bu iddialarin dayandigi kayitlar var.

Gorevin tek sey: her iddianin kendisine gosterilen kayitlarla desteklenip
desteklenmedigini soylemek. Iddiayi guzellestirme, tamamlama, yeniden yazma.

Yalnizca OLGU iddialarini denetle: sayi, tarih, isim, dosya numarasi, tutar,
ne oldugu. Analistin degerlendirmesi olgu degildir ve denetlenmez:
"merkezin dosyalari icin ne anlama geliyor", onem sirasi, hangi mekanizmanin
devrede oldugu, izlenmesi gerektigi. Bunlari eksik dayanak sayma.

- "dayanaklı": iddiadaki olgular kayitlarda, birincil belgelerde ya da sana
  verilen onceki gun basliklarinda/takip maddelerinde yaziyor.
- "kısmen": ana olgu var ama iddia baska bir OLGU ekliyor ve o kayitlarda yok
  (ornegin kayitta olmayan bir sayi, tarih, isim) ya da sayi/tarih kayittan
  farkli.
- "dayanaksız": iddianin dayandigi olgu hicbir yerde yok.

Sureklilik iddialarinda (ornegin "dun 62 idi, bugun 82") onceki gun
basliklarina ve takip maddelerine bak: orada karsiligi varsa dayanaklidir.

Notu kisa yaz ve neyin eksik oldugunu soyle. Turkce yaz.

Bicim: her iddia icin tek bir satir. Iddianin metnini tekrar yazma,
kayitlari yeniden anlatma, gerekce siralamasi yapma. "dayanakli"
buldugun iddiada notu bos birak. En fazla iki cumle."""

DENETIM_SEMA = {
    "type": "object",
    "properties": {
        "kontroller": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "hukum": {"type": "string", "enum": ["dayanaklı", "kısmen", "dayanaksız"]},
                    "not": {"type": "string", "maxLength": 400,
                            "description": "En fazla 2 cümle; dayanaklıysa boş"},
                },
                "required": ["id", "hukum", "not"],
                "additionalProperties": False,
            },
        },
        "genel": {"type": "string", "description": "Denetimin tek cümlelik sonucu"},
    },
    "required": ["kontroller", "genel"],
    "additionalProperties": False,
}


ANAHTAR_DESENI = re.compile(r"\b[0-9a-f]{6,12}\b")


def metindeki_anahtarlar(metin: str, gecerli: set[str]) -> list[str]:
    """Iddia metninde atif yapilan kayit anahtarlari.

    Denetleyiciye yalnizca alan olarak bildirilen kayitlari gondermek
    yetmiyor: brifing metnin icinde baska kayitlara da atif yapabiliyor
    ve o kayitlar gonderilmezse denetim onlari "listede yok" diye
    isaretliyordu."""
    return [a for a in dict.fromkeys(ANAHTAR_DESENI.findall(metin or "")) if a in gecerli]


def iddialari_topla(veri: dict) -> list[dict]:
    """Denetlenecek iddialar: metin, dayandigi kayitlar ve bir kimlik."""
    gecerli = set(veri.get("kullanilan_kayitlar", []))
    brifing = veri.get("brifing", "")
    brifing_kayit = metindeki_anahtarlar(brifing, gecerli) or list(gecerli)[:12]
    iddialar = [{"id": "brifing", "metin": brifing, "kayitlar": brifing_kayit}]
    for i, o in enumerate(veri.get("one_cikanlar", []), 1):
        metin = o.get("neden_onemli", "")
        if o.get("ayrintilar"):
            metin += " AYRINTILAR: " + " | ".join(o["ayrintilar"])
        tam = f"{o.get('baslik', '')} :: {metin}"
        kayitlar = list(dict.fromkeys(list(o.get("kayitlar", []))
                                      + metindeki_anahtarlar(tam, gecerli)))
        iddialar.append({"id": f"one{i}", "metin": tam, "kayitlar": kayitlar})
    for i, b in enumerate(veri.get("birincil_notlar", []), 1):
        iddialar.append({"id": f"bir{i}",
                         "metin": f"{b.get('baslik', '')} :: {b.get('ne_dedi', '')}",
                         "kayitlar": [b.get("itemid", "")]})
    return [x for x in iddialar if x["metin"].strip()]


def denetim_yap(veri: dict, secilen: list[dict], kumeler: dict, tam_metin: bool,
                model: str, birincil: str, gecmis: str = "", takip: str = "") -> dict:
    """Ikinci gecis: iddialari kayitlara karsi denetler.

    Butun kayitlari degil, yalnizca iddialarin gosterdigi kayitlari
    gonderir; hem daha ucuz hem daha odakli."""
    import anthropic

    iddialar = iddialari_topla(veri)
    if not iddialar:
        return {"hata": "denetlenecek iddia bulunamadı"}
    gosterilen = {k for i in iddialar for k in i["kayitlar"]}
    kayit_ix = {h["k"]: h for h in secilen}
    bloklar = [kayit_metni(kayit_ix[k], kumeler, tam_metin, uzun=True)
               for k in gosterilen if k in kayit_ix]

    istem = (
        "İDDİALAR\n" + "\n\n".join(
            f"[{i['id']}] {i['metin']}\n  gösterdiği kayıtlar: "
            f"{', '.join(i['kayitlar']) or '(yok)'}" for i in iddialar)
        + "\n\nKAYITLAR\n" + "\n\n".join(bloklar)
        + (f"\n\nBİRİNCİL BELGELER\n{birincil}" if birincil else "")
        + (f"\n\nÖNCEKİ GÜNLERİN BAŞLIKLARI (süreklilik iddialarının dayanağı)\n{gecmis}"
           if gecmis else "")
        + (f"\n\nAÇIK TAKİP MADDELERİ\n{takip}" if takip else "")
        + "\n\nHer iddia için hüküm ver. Yalnızca olgu eksikliğini işaretle; "
        + "analistin değerlendirmesini eksik dayanak sayma."
    )
    istemci = anthropic.Anthropic()

    def cagir(m: str):
        # Denetim mekanik bir kontrol: her iddiayi kayitlarla karsilastirip
        # uc hukumden birini vermek. Derin dusunmeye ihtiyaci yok ve
        # dusunme token'lari max_tokens'a sayiliyor; effort "low" ile hem
        # sinira takilmiyor hem ucuzluyor.
        return istemci.messages.create(
            model=m, max_tokens=16000, system=DENETIM_SISTEM,
            messages=[{"role": "user", "content": istem}],
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": DENETIM_SEMA}},
        )

    try:
        yanit = cagir(model)
    except anthropic.APIStatusError as hata:
        # Model bu hesapta yoksa (404) ya da erisim yoksa (403) yedege dus:
        # denetim, analizin tamamini bosa dusurmeyecek kadar onemli.
        print(f"denetim modeli {model} basarisiz ({hata.status_code}): {hata.message}")
        if hata.status_code in (403, 404) and model != DENETIM_YEDEK:
            try:
                yanit = cagir(DENETIM_YEDEK)
                model = DENETIM_YEDEK
                print(f"denetim yedek modelle yapildi: {DENETIM_YEDEK}")
            except Exception as ikinci:
                print(f"denetim atlandi: {type(ikinci).__name__}: {ikinci}")
                return {"hata": f"{type(ikinci).__name__}: {ikinci}"[:300]}
        else:
            return {"hata": f"{hata.status_code}: {hata.message}"[:300]}
    except Exception as hata:
        print(f"denetim atlandi: {type(hata).__name__}: {hata}")
        return {"hata": f"{type(hata).__name__}: {hata}"[:300]}
    if yanit.stop_reason in ("refusal", "max_tokens"):
        print(f"denetim atlandi: {yanit.stop_reason}")
        return {"hata": f"yanıt {yanit.stop_reason}"}
    try:
        sonuc = json.loads(next(b.text for b in yanit.content if b.type == "text"))
    except Exception as hata:
        print(f"denetim yaniti ayristirilamadi: {type(hata).__name__}")
        return {"hata": f"yanıt ayrıştırılamadı: {type(hata).__name__}"}
    sonuc["model"] = model
    sonuc["maliyet_usd"] = round(maliyet(model, yanit.usage.input_tokens,
                                         yanit.usage.output_tokens), 4)
    sonuc["iddia_sayisi"] = len(iddialar)
    print(f"denetim token: {yanit.usage.input_tokens} girdi / "
          f"{yanit.usage.output_tokens} çıktı")
    return sonuc


def durum_yaz(gun: str, durum: str, mesaj: str = "") -> None:
    """Son denemenin sonucu. Is akisinda analiz adimi hatayi yutuyor
    (taramayi bozmasin diye); bu dosya sayesinde neden uretilmedigi
    yayinda gorunur."""
    (DATA / "analiz-durum.json").write_text(json.dumps({
        "gun": gun, "durum": durum, "mesaj": mesaj,
        "zaman": datetime.now(timezone.utc).isoformat(timespec="minutes"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")


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
    ap.add_argument("--en-erken", type=int,
                    default=int(os.environ.get("ANALIZ_EN_ERKEN") or 6),
                    help=("UTC saati; bundan önce analiz üretilmez. Günün kayıtları "
                          "sabah 06:00 UTC'den (TR 09:00) sonra geliyor; daha erken "
                          "üretilen analiz neredeyse boş bir güne bakar ve gün boyu "
                          "yenilenmez. 0 verilirse kontrol kapanır."))
    ap.add_argument("--tam-metin", action="store_true", default=True)
    ap.add_argument("--kisa", dest="tam_metin", action="store_false", help="tam metinleri isteme (daha ucuz)")
    ap.add_argument("--birincil", action="store_true", default=True,
                    help="AİHM karar metinlerini isteme kat (öntanımlı)")
    ap.add_argument("--birincil-yok", dest="birincil", action="store_false")
    ap.add_argument("--denetim-model", default=os.environ.get("DENETIM_MODEL") or "claude-sonnet-5",
                    help="öz-denetim geçişinin modeli")
    ap.add_argument("--denetim", action="store_true", default=True,
                    help="analizden sonra iddiaları kayıtlara karşı denetle (öntanımlı)")
    ap.add_argument("--denetim-yok", dest="denetim", action="store_false")
    ap.add_argument("--yalniz-denetim", action="store_true",
                    help="analizi yeniden üretme; var olanı denetleyip sonucu işle")
    args = ap.parse_args()

    latest = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    gun = args.gun or datetime.now(timezone.utc).date().isoformat()
    hedef = ANALIZ / f"{gun}.json"
    if hedef.exists() and not args.zorla and not args.yalniz_denetim:
        print(f"{gun} analizi zaten var (--zorla ile yenilenir).")
        return 0

    # Gunun kayitlari henuz gelmemisse uretme: erken uretilen analiz gun
    # boyu "zaten var" diye atlanir ve gun bos bir analizle gecer.
    simdi = datetime.now(timezone.utc)
    if (not args.zorla and not args.gun and not args.yalniz_denetim
            and args.en_erken and simdi.hour < args.en_erken):
        bekleyen = sum(1 for h in latest["haberler"] if h["tarih"][:10] == gun)
        durum_yaz(gun, "erken",
                  f"saat {simdi:%H:%M} UTC; analiz en erken {args.en_erken:02d}:00 UTC'de "
                  f"üretilir (şu an güne ait {bekleyen} kayıt var)")
        print(f"saat {simdi:%H:%M} UTC — analiz en erken {args.en_erken:02d}:00 UTC'de "
              f"üretilir; güne ait {bekleyen} kayıt var. Atlandı.")
        return 0

    if args.yalniz_denetim:
        if not hedef.exists():
            print(f"{gun} analizi yok; denetlenecek bir şey de yok.")
            return 1
        veri = json.loads(hedef.read_text(encoding="utf-8"))
        secilen = [h for h in latest["haberler"] if h["k"] in set(veri.get("kullanilan_kayitlar", []))]
        print(f"yalnız denetim: {len(veri.get('one_cikanlar', []))} öne çıkan, "
              f"{len(veri.get('birincil_notlar', []))} birincil not, "
              f"{len(secilen)}/{len(veri.get('kullanilan_kayitlar', []))} kayıt bulundu")
        denetim = denetim_yap(veri, secilen, latest.get("kumeler", {}), args.tam_metin,
                              args.denetim_model, birincil_blogu() if args.birincil else "",
                              gecmis=gecmis_ozeti(), takip=takip_ozeti(takip_oku()))
        if denetim.get("hata"):
            print(f"::warning::öz-denetim yapılamadı: {denetim['hata']}")
            veri["denetim_hata"] = denetim["hata"]
            durum_yaz(gun, "denetim yapılamadı", denetim["hata"])
        elif denetim:
            veri["denetim"] = denetim
            veri["maliyet_usd"] = round(veri.get("maliyet_usd", 0) + denetim.get("maliyet_usd", 0), 4)
            veri.pop("denetim_hata", None)
            sorunlu = [k for k in denetim["kontroller"] if k["hukum"] != "dayanaklı"]
            print(f"denetim ({denetim['model']}): {denetim['iddia_sayisi']} iddia, "
                  f"{len(sorunlu)} işaretlendi · +${denetim.get('maliyet_usd', 0):.3f}")
            durum_yaz(gun, "tamam", f"denetim eklendi: {denetim['iddia_sayisi']} iddia, "
                                    f"{len(sorunlu)} işaretlendi")
        else:
            durum_yaz(gun, "denetim boş", "denetim geçişi hiçbir sonuç döndürmedi")
            print("::warning::denetim boş döndü.")
            return 1
        hedef.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
        (DATA / "analiz-latest.json").write_text(json.dumps(veri, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
        return 0

    secilen = kayitlari_sec(latest["haberler"], gun, args.adet)
    if len(secilen) < 3:
        print("Analiz için yeterli kayıt yok.")
        return 0
    takip = takip_oku()
    birincil = birincil_blogu() if args.birincil else ""
    istem = istem_yap(secilen, latest.get("kumeler", {}), gun, args.tam_metin,
                      gecmis=gecmis_ozeti(), takip=takip_ozeti(takip), birincil=birincil)

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
        # Akis kullaniyoruz: cikti sinirini yukseltmek gerekiyor (17 Eylul
        # kosusu 16.000'in 15.554'unu kullandi; dusunme token'lari da buna
        # sayiliyor) ve akis olmadan uzun yanitlar HTTP zaman asimina
        # takilabiliyor. get_final_message() tam yaniti veriyor.
        with client.messages.stream(
            model=args.model,
            max_tokens=48000,
            system=SISTEM,
            messages=[{"role": "user", "content": istem}],
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": SEMA}},
        ) as akis:
            yanit = akis.get_final_message()
    except anthropic.APIStatusError as hata:
        durum_yaz(gun, "api hatası", f"{hata.status_code}: {hata.message}")
        print(f"::error::API hatası ({hata.status_code}): {hata.message}")
        return 1
    except anthropic.APIConnectionError as hata:
        durum_yaz(gun, "bağlantı hatası", str(hata))
        print(f"::error::Bağlantı hatası: {hata}")
        return 1

    if yanit.stop_reason == "refusal":
        durum_yaz(gun, "reddedildi", "Model isteği yanıtlamayı reddetti.")
        print("Model isteği yanıtlamayı reddetti; analiz üretilmedi.")
        return 1
    if yanit.stop_reason == "max_tokens":
        durum_yaz(gun, "kesildi",
                  f"Yanıt çıktı sınırına takıldı ({yanit.usage.output_tokens} token). "
                  "max_tokens büyütülmeli ya da şema küçültülmeli.")
        print("::error::Yanıt çıktı sınırında kesildi; analiz yazılmadı.")
        return 1

    metin = next((b.text for b in yanit.content if b.type == "text"), "")
    try:
        veri = json.loads(metin)
    except json.JSONDecodeError as hata:
        durum_yaz(gun, "ayrıştırılamadı",
                  f"Yanıt geçerli JSON değil ({hata}); {len(metin)} karakter geldi.")
        print(f"::error::Yanıt ayrıştırılamadı: {hata}")
        return 1

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

    if args.denetim:
        denetim = denetim_yap(veri, secilen, latest.get("kumeler", {}), args.tam_metin,
                              args.denetim_model, birincil,
                              gecmis=gecmis_ozeti(), takip=takip_ozeti(takip))
        if denetim.get("hata"):
            print(f"::warning::öz-denetim yapılamadı: {denetim['hata']}")
            veri["denetim_hata"] = denetim["hata"]
        elif denetim:
            veri["denetim"] = denetim
            tutar += denetim.get("maliyet_usd", 0)
            veri["maliyet_usd"] = round(tutar, 4)
            sorunlu = [k for k in denetim["kontroller"] if k["hukum"] != "dayanaklı"]
            print(f"denetim ({denetim['model']}): {denetim['iddia_sayisi']} iddia, "
                  f"{len(sorunlu)} işaretlendi · +${denetim.get('maliyet_usd', 0):.3f}")

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

    d = veri.get("denetim") or {}
    durum_yaz(gun, "tamam",
              f"{len(veri.get('one_cikanlar', []))} öne çıkan, "
              f"{len(veri.get('birincil_notlar', []))} birincil belge, "
              f"${veri.get('maliyet_usd', 0)}"
              + (f", denetim: {d.get('iddia_sayisi')} iddia" if d else
                 f", denetim yok ({veri.get('denetim_hata', 'sebep bilinmiyor')})"))

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
