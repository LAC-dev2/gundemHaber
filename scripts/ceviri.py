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
             "hakkında", "davası", "kararı", "tutuklu", "gözaltı", "başvuru",
             # Turkce metinlerin cevirmene gonderilip "cevrilemedi" diye
             # isaretlenmesini onlemek icin genisletildi: Bianet'in
             # "Avrupa Konseyi'nden ... yonelik operasyonlara tepki"
             # basligi eski listeyle hicbir sozcuk tutturamiyordu.
             "anayasa", "mahkemesi", "yönelik", "tepki", "ilişkin", "yeni",
             "kişinin", "hakkinda", "avrupa", "konseyi", "bakanlar", "komitesi",
             "soruşturma", "soruşturması", "tutuklama", "serbest", "bırakıldı",
             "operasyon", "operasyonlara", "gözaltına", "alındı", "ihlal",
             "ihlali", "adalet", "bakanlığı", "savcılık", "savcılığı", "polis",
             "cezaevi", "avukat", "gazeteci", "milletvekili", "yasa", "kanun",
             "yönetmelik", "genelge", "resmî", "resmi", "gazete", "sayılı",
             "değişiklik", "yapılmasına", "dair", "kurulu", "bakanı", "türkiye"}

# Turkceye ozgu harfler. "İ" onemli: buyuk harfle yazilmis Turkce basliklarda
# (ornegin "ANAYASA MAHKEMESİ") tek Turkce isaret bu olabiliyor ve lower()
# onu "i + birlesen nokta"ya cevirdigi icin kucuk harf taramasinda kayboluyor.
CEVIRI_DENEME = 2        # "cevrilemedi" damgali kayit kac kez yeniden denenir

TR_HARF = "ıİğĞşŞ"

# Yabanci islev sozcukleri. Ikisi birden gecerse metin Turkce sayilmaz;
# boylece "Turkey detains 21 in Izmir" gibi Turkce ozel ad tasiyan
# Ingilizce basliklar ceviriden kacmiyor.
YABANCI_SOZCUK = {
    "the", "of", "and", "in", "on", "for", "with", "after", "over", "from",
    "to", "as", "by", "that", "is", "are", "was", "were", "has", "have",
    "der", "die", "das", "und", "für", "von", "mit", "ist", "im", "auf",
    "de", "la", "le", "les", "des", "du", "et", "en", "pour", "een", "van",
    "het", "op", "aan", "bij", "naar", "niet", "wordt", "werd",
}

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
6. Metin zaten Türkçeyse aynen bırak.
7. BAŞLIK TEK BAŞINA BİR AD YA DA KODSA (bir kişi adı — "Vladimir
   Kara-Murza"; bir kurum kısaltması — "CiTiP by CiTiP"; bir dosya kodu —
   "ECLI:NL:RBDHA:2026:27263") onu olduğu gibi geri verme. Özeti oku ve
   kaydın NE OLDUĞUNU söyleyen kısa bir Türkçe başlık yaz; adı da içinde
   koru. Örnek: özet bir USCIRF mağdur kaydıysa → "Maksim Khamatshin —
   USCIRF din özgürlüğü mağdur kaydı"; Freedom House profiliyse →
   "Carolina Barrero — Freedom House sınıraşan baskı profili". Özet yoksa
   ya da neyin kaydı olduğu çıkmıyorsa başlığı boş bırak; uydurma."""


def dil_tahmini(metin: str) -> str:
    """Kaba dil ayrimi: Turkce mi, degil mi.

    Tek bir Turkce harf yetmiyor: Ingilizce basliklarin coguna Turkce
    ozel ad giriyor ("Turkey detains 21 in Izmir..."). Once yabanci
    islev sozcuklerine bakiliyor; onlar varsa metin Turkce degildir.
    """
    low = metin.lower()
    sozcukler = set(re.findall(r"[a-zçğıöşü]+", low))
    if len(sozcukler & YABANCI_SOZCUK) >= 2:
        return "diger"
    if any(harf in metin for harf in TR_HARF):     # ham metinde ara: "İ" kaybolmasin
        return "tr"
    if len(sozcukler & TR_SOZCUK) >= 2:
        return "tr"
    # Turkce eklerin izi: tek basina zayif ama iki sozcukte gorulurse yeter
    ekli = sum(1 for w in sozcukler if len(w) > 5 and w.endswith(
        ("nin", "nın", "nun", "nün", "ler", "lar", "den", "dan", "tan", "ten",
         "sinde", "sında", "mesi", "ması", "lik", "lık", "luk", "lük")))
    return "tr" if ekli >= 2 else "diger"


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
        if not anahtar:
            continue
        kayitli = onbellek.get(anahtar)
        if kayitli is not None:
            # "cevrilemedi" kalici bir damgaydi; tek seferlik bir aksaklik
            # (yigin hatasi, eksik satir) kaydi sonsuza dek yabanci dilde
            # birakiyordu. Artik sinirli sayida yeniden deneniyor. Ozel
            # ad basliklari (kisi adlari) zaten degismeden donecegi icin
            # deneme hakki dolunca ozgun haliyle kaliyorlar.
            if not (kayitli.get("cevrilemedi")
                    and kayitli.get("deneme", 1) < CEVIRI_DENEME):
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
    hata_nedeni = ""

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
            # Nedeni yazmak sart: yalnizca sinif adi basiliyordu ve is akisi
            # da continue-on-error ile yesil kaldigi icin, kredi tukendiginde
            # ceviri iki gun boyunca sessizce durdu. Hesap/anahtar duzeyindeki
            # hatalarda kalan yiginlari denemenin de anlami yok.
            mesaj = getattr(hata, "message", None) or str(hata)
            print(f"::warning::çeviri yığını atlandı ({type(hata).__name__}): {mesaj}")
            kod = getattr(hata, "status_code", None)
            if kod in (400, 401, 402, 403) or "credit balance" in mesaj.lower():
                print(f"::error::çeviri durduruldu; kalan {len(bekleyen) - bas} kayıt "
                      f"çevrilmedi. Neden: {mesaj}")
                hata_nedeni = mesaj
                break
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
                onceki = onbellek.get(satir["k"]) or {}
                kayit["cevrilemedi"] = True
                kayit["deneme"] = onceki.get("deneme", 0) + 1
            onbellek[satir["k"]] = kayit
        girdi += yanit.usage.input_tokens
        cikti += yanit.usage.output_tokens
        print(f"  {bas + len(yigin)}/{len(bekleyen)} çevrildi")

    g, c = FIYAT.get(args.model, FIYAT[VARSAYILAN_MODEL])
    tutar = girdi / 1e6 * g + cikti / 1e6 * c
    print(f"çeviri bitti: {girdi} girdi / {cikti} çıktı token · ≈ ${tutar:.3f} · {args.model}")
    yaz(latest, latest_yol, onbellek)
    if hata_nedeni:
        return 1
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
