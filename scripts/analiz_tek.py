#!/usr/bin/env python3
"""Tek bir haberi/belgeyi analiz eder (baglanti ya da yapistirilan metin).

Yerel uygulamadaki "Analiz et" bolumu bu modulu kullanir; komut satirindan da
calisir:

  python3 scripts/analiz_tek.py https://ornek.com/haber
  python3 scripts/analiz_tek.py --metin "yapistirilan metin…"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import extract as extract_text        # noqa: E402
import collect                                      # noqa: E402

VARSAYILAN_MODEL = os.environ.get("ANALIZ_MODEL", "claude-opus-5")
MAKS_METIN = 18000          # karakter; ~5 bin token
ALANLAR = [
    "AİHM başvuruları ve kararların icrası",
    "BM insan hakları mekanizmaları",
    "INTERPOL bildirimleri ve kırmızı bülten",
    "İade, adli yardım ve iltica",
    "Yaptırım listeleri ve malvarlığı dondurma",
    "Gülen hareketi/KHK dosyaları ve sınıraşan baskı",
    "İfade ve basın özgürlüğü",
    "Belçika ve AB mevzuatı",
    "İlgisiz",
]

SISTEM = """Sen Brüksel Hukuk Merkezi'nin izleme masasında çalışan bir hukuk analistisin.
Merkez; AİHM başvuruları, BM insan hakları mekanizmaları, INTERPOL bildirimleri,
iade–adli yardım–iltica dosyaları, yaptırım listeleri ve Gülen hareketi/KHK
kaynaklı sınıraşan baskı vakaları üzerinde çalışır.

Sana tek bir haber, karar ya da duyuru metni verilecek. Görevin bunu merkezin
dosyaları açısından değerlendirmek.

Kurallar:
1. YALNIZCA verilen metindeki bilgiyi kullan. Metinde olmayan olay, isim, tarih,
   dosya numarası, madde numarası veya alıntı uydurma. Metin eksikse "metinde
   yer almıyor" de.
2. Hukuki tavsiye, dava stratejisi veya başvuru önerisi yazma. İşin, gelişmeyi
   konumlandırmak ve hangi hukuki çerçeveye değdiğini göstermektir.
3. Emin olmadığın yerde emin olmadığını yaz; "guven" alanını dürüstçe doldur.
4. Metin merkezin alanlarıyla ilgisizse alan olarak "İlgisiz" seç ve kısa gerekçe yaz.
5. Türkçe, kuru ve mesleki bir dil kullan. Abartılı sıfat kullanma."""

SEMA = {
    "type": "object",
    "properties": {
        "baslik": {"type": "string", "description": "Metnin konusunu özetleyen kısa başlık"},
        "ozet": {"type": "string", "description": "3-5 cümlelik tarafsız özet"},
        "alan": {"type": "string", "description": "En ilgili çalışma alanı"},
        "ikincil_alanlar": {"type": "array", "items": {"type": "string"}},
        "degerlendirme": {"type": "string", "description": "Merkezin dosyaları açısından anlamı, 3-6 cümle"},
        "hukuki_cerceve": {
            "type": "array",
            "description": "Metinde adı geçen ya da doğrudan ilgili olan hukuki dayanaklar; metinde yoksa boş bırak",
            "items": {
                "type": "object",
                "properties": {
                    "dayanak": {"type": "string", "description": "Örn. AİHS m.8, INTERPOL Statüsü m.3"},
                    "ilgisi": {"type": "string"},
                    "metinde_geciyor": {"type": "boolean"},
                },
                "required": ["dayanak", "ilgisi", "metinde_geciyor"],
                "additionalProperties": False,
            },
        },
        "dikkat": {
            "type": "array",
            "description": "Doğrulanması gereken noktalar, belirsizlikler, eksik bilgiler",
            "items": {"type": "string"},
        },
        "izlenecekler": {"type": "array", "items": {"type": "string"}},
        "guven": {"type": "string", "enum": ["yüksek", "orta", "düşük"]},
        "guven_gerekcesi": {"type": "string"},
    },
    "required": ["baslik", "ozet", "alan", "ikincil_alanlar", "degerlendirme",
                 "hukuki_cerceve", "dikkat", "izlenecekler", "guven", "guven_gerekcesi"],
    "additionalProperties": False,
}


def metni_getir(url: str) -> tuple[str, str]:
    """Adresten okunabilir metni ve sayfa başlığını çıkarır."""
    ctype, govde = collect.fetch(url, 1_500_000)
    paragraflar = extract_text(govde, ctype)
    metin = "\n\n".join(p.lstrip("# ") for p in paragraflar)
    m = re.search(rb"<title[^>]*>(.*?)</title>", govde[:200_000], re.I | re.S)
    baslik = collect.clean(m.group(1).decode("utf-8", "replace"), 300) if m else ""
    if not metin:
        # metin çıkarılamadıysa en azından açıklama etiketini dene
        m2 = re.search(rb'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', govde, re.I)
        metin = collect.clean(m2.group(1).decode("utf-8", "replace"), 1000) if m2 else ""
    return baslik, metin


def analiz_et(url: str = "", metin: str = "", model: str = VARSAYILAN_MODEL) -> dict:
    """Tek metin analizi. Sonuç sözlüğü döndürür; hata durumunda {'hata': ...}."""
    baslik = ""
    if url and not metin:
        try:
            baslik, metin = metni_getir(url)
        except Exception as exc:
            return {"hata": f"Sayfa alınamadı: {type(exc).__name__}. "
                            f"Metni kopyalayıp yapıştırarak deneyebilirsin."}
    metin = (metin or "").strip()
    if len(metin) < 200:
        return {"hata": "Analiz için yeterli metin çıkarılamadı (en az 200 karakter). "
                        "Sayfa giriş istiyor ya da metni JavaScript ile basıyor olabilir; "
                        "metni kopyalayıp yapıştır."}
    kirpildi = len(metin) > MAKS_METIN
    metin = metin[:MAKS_METIN]

    try:
        import anthropic
    except ImportError:
        return {"hata": "anthropic paketi kurulu değil:  pip install anthropic"}
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return {"hata": "ANTHROPIC_API_KEY tanımlı değil. Uygulamayı anahtarla başlat: "
                        "ANTHROPIC_API_KEY=sk-ant-… python3 scripts/serve.py"}

    istem = (
        (f"Kaynak adres: {url}\n" if url else "")
        + (f"Sayfa başlığı: {baslik}\n" if baslik else "")
        + f"\nMerkezin çalışma alanları:\n" + "\n".join(f"- {a}" for a in ALANLAR)
        + "\n\nMETİN:\n" + metin
        + ("\n\n[metin uzunluk sınırı nedeniyle kısaltıldı]" if kirpildi else "")
        + "\n\nBu metni merkezin dosyaları açısından değerlendir."
    )

    client = anthropic.Anthropic()
    try:
        yanit = client.messages.create(
            model=model, max_tokens=6000, system=SISTEM,
            messages=[{"role": "user", "content": istem}],
            output_config={"format": {"type": "json_schema", "schema": SEMA}},
        )
    except anthropic.APIStatusError as hata:
        return {"hata": f"API hatası ({hata.status_code}): {hata.message}"}
    except anthropic.APIConnectionError as hata:
        return {"hata": f"Bağlantı hatası: {hata}"}

    if yanit.stop_reason == "refusal":
        return {"hata": "Model bu metni değerlendirmeyi reddetti."}

    veri = json.loads(next(b.text for b in yanit.content if b.type == "text"))
    g, c = ({"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0),
             "claude-haiku-4-5": (1.0, 5.0)}).get(model, (5.0, 25.0))
    veri.update({
        "url": url, "kaynak_baslik": baslik, "model": model,
        "olusturma": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "kirpildi": kirpildi,
        "maliyet_usd": round(yanit.usage.input_tokens / 1e6 * g
                             + yanit.usage.output_tokens / 1e6 * c, 4),
        "uyari": ("Bu değerlendirme verilen metne dayanarak yapay zekâ ile üretilmiştir; "
                  "hukuki tavsiye değildir ve birincil kaynakta doğrulanmadan dosyaya "
                  "esas alınamaz."),
    })
    return veri


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", default="")
    ap.add_argument("--metin", default="")
    ap.add_argument("--model", default=VARSAYILAN_MODEL)
    args = ap.parse_args()
    if not args.url and not args.metin:
        ap.error("bir adres ya da --metin gerekli")
    sonuc = analiz_et(args.url, args.metin, args.model)
    print(json.dumps(sonuc, ensure_ascii=False, indent=1))
    return 1 if "hata" in sonuc else 0


if __name__ == "__main__":
    sys.exit(main())
