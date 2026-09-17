#!/usr/bin/env python3
"""Turkce olmayan kayitlarin baslik ve ozetlerini Turkceye cevirir.

Her kayit bir kez cevrilir ve data/ceviri.json onbellegine yazilir; sonraki
turlarda yalnizca yeni kayitlar icin istek atilir.

  python3 scripts/ceviri.py                 # yeni kayitlari cevir
  python3 scripts/ceviri.py --kuru          # istek atmadan sayiyi gor
  python3 scripts/ceviri.py --adet 200      # bu turda en fazla 200 kayit
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ONBELLEK = DATA / "ceviri.json"

VARSAYILAN_MODEL = os.environ.get("CEVIRI_MODEL") or "claude-haiku-4-5"
YIGIN = 20          # tek istekte kac kayit
FIYAT = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0),
         "claude-opus-5": (5.0, 25.0)}

TR_SOZCUK = {"ve", "için", "ile", "bir", "bu", "olarak", "karar", "mahkeme",
             "dava", "hak", "yargı", "göre", "sonra", "kişi", "yıl", "üzerine",
             "hakkında", "davası", "kararı", "tutuklu", "gözaltı", "başvuru"}

SISTEM = """Sen hukuk alanında çalışan bir çevirmensin. Sana haber, karar ve duyuru
başlıkları ile kısa özetleri verilecek; bunları Türkçeye çevireceksin.

Kurallar:
1. Anlamı değiştirme, ekleme yapma, yorum katma. Çeviri yap, özetleme.
2. Kurum ve mahkeme adlarını Türkçede yerleşik karşılıklarıyla ver
   (European Court of Human Rights → Avrupa İnsan Hakları Mahkemesi/AİHM,
   Council of Europe → Avrupa Konseyi, Conseil du contentieux des étrangers →
   Yabancılar İhtilafları Konseyi). Yerleşik karşılığı yoksa özgün adı koru.
3. Dava adlarını, kişi adlarını, dosya ve karar numaralarını olduğu gibi bırak.
4. Hukuk terimlerini Türk hukuk dilinde kullanılan karşılıklarıyla ver
   (detention → tutukluluk/gözaltı, bağlama göre; asylum → iltica;
   extradition → iade; appeal → istinaf/temyiz, bağlama göre).
5. Başlıkta gazete üslubu kullanma; kaynak ne diyorsa onu Türkçede söyle.
6. Metin zaten Türkçeyse aynen bırak."""


def dil_tahmini(metin: str) -> str:
    """Kaba dil ayrimi: Turkce mi, degil mi."""
    low = metin.lower()
    if any(harf in low for harf in "ığş"):
        return "tr"
    sozcukler = set(re.findall(r"[a-zçğıöşü]+", low))
    return "tr" if len(sozcukler & TR_SOZCUK) >= 2 else "diger"


def kat(metin: str) -> str:
    """Karsilastirma icin sadelestirir: harf ve rakam disini atar."""
    return re.sub(r"[^a-z0-9çğıöşü]+", "", (metin or "").lower())


def dogrula(h: dict, baslik: str, ozet: str) -> tuple[str, str]:
    """Modelin ceviri yerine baslik tekrarlamasini ya da ceviriyi
    atlamasini yakalar. Kusurlu alani bos dondurur; arayuz o zaman
    ozgun metne duser, uydurma bir "Turkce" gostermez."""
    ozgun_b, ozgun_o = h.get("baslik") or "", h.get("ozet") or ""
    b, o = (baslik or "").strip(), (ozet or "").strip()

    if kat(b) == kat(ozgun_b):            # cevirmemis, aynen geri vermis
        b = ""
    if o:
        if kat(o) in (kat(b), kat(ozgun_b)):        # ozet yerine baslik yazmis
            o = ""
        elif not ozgun_o:                            # ozgun ozet yok, uydurmus
            o = ""
        elif len(ozgun_o) > 120 and len(o) < len(ozgun_o) * 0.35:
            o = ""                                   # ozetlemis, cevirmemis
    return b, o


def sema(n: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "ceviriler": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "k": {"type": "string"},
                        "baslik": {"type": "string"},
                        "ozet": {"type": "string"},
                    },
                    "required": ["k", "baslik", "ozet"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["ceviriler"],
        "additionalProperties": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=VARSAYILAN_MODEL)
    ap.add_argument("--adet", type=int, default=160, help="bu turda en fazla kaç yeni kayıt")
    ap.add_argument("--temizle", action="store_true",
                    help="mevcut onbellegi yeniden denetle, kusurlu cevirileri at")
    ap.add_argument("--kuru", action="store_true")
    args = ap.parse_args()

    latest_yol = DATA / "latest.json"
    latest = json.loads(latest_yol.read_text(encoding="utf-8"))
    onbellek = json.loads(ONBELLEK.read_text(encoding="utf-8")) if ONBELLEK.exists() else {}

    if args.temizle:
        kayitlar = {h["k"]: h for h in latest["haberler"] if h.get("k")}
        atilan = 0
        for k, kayit in list(onbellek.items()):
            if kayit.get("dil") != "diger" or not kayit.get("baslik"):
                continue
            h = kayitlar.get(k)
            if not h:
                continue
            b, o = dogrula(h, kayit.get("baslik", ""), kayit.get("ozet", ""))
            if b and o == kayit.get("ozet", ""):
                continue
            atilan += 1
            yeni_kayit = {"dil": "diger"}
            if b:
                yeni_kayit["baslik"] = b
                if o:
                    yeni_kayit["ozet"] = o
            else:
                yeni_kayit["cevrilemedi"] = True
            onbellek[k] = yeni_kayit
        print(f"önbellek denetimi: {atilan} kayıtta kusurlu çeviri düzeltildi")
        for h in latest["haberler"]:               # eski alanları da temizle
            kayit = onbellek.get(h.get("k") or "", {})
            if not kayit.get("baslik"):
                h.pop("baslik_tr", None)
            if not kayit.get("ozet"):
                h.pop("ozet_tr", None)
        yaz(latest, latest_yol, onbellek)
        return 0

    bekleyen = []
    for h in latest["haberler"]:
        anahtar = h.get("k")
        if not anahtar or anahtar in onbellek:
            continue
        if dil_tahmini(f"{h['baslik']} {h.get('ozet', '')}") == "tr":
            onbellek[anahtar] = {"dil": "tr"}          # çeviri gerekmiyor
            continue
        bekleyen.append(h)

    print(f"çevrilecek yeni kayıt: {len(bekleyen)} (önbellekte {len(onbellek)})")
    if args.kuru or not bekleyen:
        if args.kuru and bekleyen:
            g, c = FIYAT.get(args.model, FIYAT[VARSAYILAN_MODEL])
            tahmin = len(bekleyen) * 150 / 1e6 * g + len(bekleyen) * 150 / 1e6 * c
            print(f"kaba maliyet tahmini: ${tahmin:.3f} ({args.model})")
        yaz(latest, latest_yol, onbellek)
        return 0

    try:
        import anthropic
    except ImportError:
        print("anthropic paketi kurulu değil:  pip install anthropic")
        return 1
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("ANTHROPIC_API_KEY tanımlı değil; çeviri atlandı.")
        return 0

    client = anthropic.Anthropic()
    bekleyen = bekleyen[: args.adet]
    girdi = cikti = 0

    for bas in range(0, len(bekleyen), YIGIN):
        yigin = bekleyen[bas: bas + YIGIN]
        istem = "Aşağıdaki kayıtları Türkçeye çevir. Her kaydın anahtarını koru.\n\n" + "\n\n".join(
            f"[{h['k']}]\nBAŞLIK: {h['baslik']}\nÖZET: {(h.get('ozet') or '')[:400]}"
            for h in yigin)
        try:
            yanit = client.messages.create(
                model=args.model, max_tokens=8000, system=SISTEM,
                messages=[{"role": "user", "content": istem}],
                output_config={"format": {"type": "json_schema", "schema": sema(len(yigin))}},
            )
        except Exception as hata:                     # bir yığın düşerse diğerleri sürsün
            print(f"  yığın atlandı: {type(hata).__name__}")
            continue
        if yanit.stop_reason == "refusal":
            continue
        try:
            veri = json.loads(next(b.text for b in yanit.content if b.type == "text"))
        except Exception:
            continue
        yigin_ix = {h["k"]: h for h in yigin}
        for satir in veri.get("ceviriler", []):
            h = yigin_ix.get(satir.get("k", ""))
            if not h:
                continue
            b, o = dogrula(h, satir.get("baslik", ""), satir.get("ozet", ""))
            kayit = {"dil": "diger"}
            if b:
                kayit["baslik"] = b
                if o:
                    kayit["ozet"] = o
            else:
                kayit["cevrilemedi"] = True     # tekrar denenip durmasin
            onbellek[satir["k"]] = kayit
        girdi += yanit.usage.input_tokens
        cikti += yanit.usage.output_tokens
        print(f"  {bas + len(yigin)}/{len(bekleyen)} çevrildi")

    g, c = FIYAT.get(args.model, FIYAT[VARSAYILAN_MODEL])
    tutar = girdi / 1e6 * g + cikti / 1e6 * c
    print(f"çeviri bitti: {girdi} girdi / {cikti} çıktı token · ≈ ${tutar:.3f} · {args.model}")
    yaz(latest, latest_yol, onbellek)
    return 0


def yaz(latest: dict, yol: Path, onbellek: dict) -> None:
    """Onbellegi kaydeder ve kayitlara Turkce alanlarini isler."""
    ONBELLEK.write_text(json.dumps(onbellek, ensure_ascii=False, indent=0, sort_keys=True),
                        encoding="utf-8")
    cevrili = 0
    for h in latest["haberler"]:
        kayit = onbellek.get(h.get("k") or "")
        if not kayit:
            continue
        h["dil"] = kayit["dil"]
        if kayit.get("baslik"):
            h["baslik_tr"] = kayit["baslik"]
            if kayit.get("ozet"):
                h["ozet_tr"] = kayit["ozet"]
            else:
                h.pop("ozet_tr", None)
            cevrili += 1
        else:
            h.pop("baslik_tr", None)
            h.pop("ozet_tr", None)
    latest.setdefault("istatistik", {})["cevrili"] = cevrili
    latest["istatistik"]["ceviri_guncelleme"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    yol.write_text(json.dumps(latest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # bugünün arşiv dosyası da aynı alanları taşısın
    gun = datetime.now(timezone.utc).date().isoformat()
    arsiv = DATA / "archive" / f"{gun}.json"
    if arsiv.exists():
        try:
            d = json.loads(arsiv.read_text(encoding="utf-8"))
            for h in d.get("haberler", []):
                kayit = onbellek.get(h.get("k") or "") or {}
                if kayit.get("baslik"):
                    h["baslik_tr"] = kayit["baslik"]
                else:
                    h.pop("baslik_tr", None)         # denetimde atilan ceviri
                if kayit.get("baslik") and kayit.get("ozet"):
                    h["ozet_tr"] = kayit["ozet"]
                else:
                    h.pop("ozet_tr", None)
            arsiv.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        except Exception:
            pass
    print(f"Türkçe alanı işlenen kayıt: {cevrili}")


if __name__ == "__main__":
    sys.exit(main())
