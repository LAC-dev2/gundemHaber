#!/usr/bin/env python3
"""Ayni gunun ayni kayitlariyla farkli model/effort yapilandirmalarini karsilastirir.

"Ust model daha iyi sonuc verir mi" sorusunu gorusle degil olcumle
cevaplamak icin. Uretim analizini bozmaz: ciktilar data/kalite/ altina
yazilir.

  python3 scripts/kalite.py --varyant "opus5-max:claude-opus-5:max" \
                            --varyant "fable:claude-fable-5-1:high"
  python3 scripts/kalite.py --kuru          # istek atmadan maliyet tahmini

Her varyant icin uretilen analiz, uretimdekiyle ayni oz-denetimden
gecirilir; boylece "dayanakli iddia orani" varyantlar arasinda
karsilastirilabilir.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analiz                                          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KALITE = DATA / "kalite"


def olcumler(veri: dict) -> dict:
    """Ciktinin nesnel olculeri: neyin ne kadar somut oldugu."""
    metin_alanlari = [veri.get("brifing", "")]
    ayrinti_sayisi = 0
    karsi_okuma = 0
    for o in veri.get("one_cikanlar", []):
        metin_alanlari.append(o.get("neden_onemli", ""))
        metin_alanlari += list(o.get("ayrintilar", []))
        ayrinti_sayisi += len(o.get("ayrintilar", []))
        if (o.get("karsi_okuma") or "").strip():
            karsi_okuma += 1
    for b in veri.get("birincil_notlar", []):
        metin_alanlari.append(b.get("ne_dedi", ""))
    govde = " ".join(metin_alanlari)
    rakam = len(re.findall(r"\d", govde))
    atif = set(re.findall(r"\b[0-9a-f]{6,12}\b", json.dumps(veri, ensure_ascii=False)))
    den = veri.get("denetim") or {}
    kontrol = den.get("kontroller", [])
    dayanakli = sum(1 for k in kontrol if k["hukum"] == "dayanaklı")
    return {
        "one_cikan": len(veri.get("one_cikanlar", [])),
        "birincil_not": len(veri.get("birincil_notlar", [])),
        "kronoloji": len(veri.get("kronoloji", [])),
        "ayrinti_satiri": ayrinti_sayisi,
        "karsi_okuma": karsi_okuma,
        "govde_karakter": len(govde),
        "rakam": rakam,
        "rakam_yogunlugu": round(rakam / max(1, len(govde)) * 1000, 1),
        "atif_edilen_kayit": len(atif),
        "denetim_iddia": den.get("iddia_sayisi"),
        "denetim_dayanakli": dayanakli,
        "denetim_orani": round(dayanakli / len(kontrol), 2) if kontrol else None,
        "maliyet_usd": veri.get("maliyet_usd"),
    }


def uret(client, model: str, effort: str, istem: str) -> tuple[dict | None, str]:
    """Bir varyanti calistirir; (veri, hata) doner."""
    import anthropic
    cikti = {"format": {"type": "json_schema", "schema": analiz.SEMA}}
    if effort:
        cikti["effort"] = effort
    try:
        with client.messages.stream(
            model=model, max_tokens=32000, system=analiz.SISTEM,
            messages=[{"role": "user", "content": istem}],
            thinking={"type": "adaptive"},
            output_config=cikti,
        ) as akis:
            yanit = akis.get_final_message()
    except anthropic.APIStatusError as hata:
        return None, f"{hata.status_code}: {hata.message}"[:300]
    except Exception as hata:
        return None, f"{type(hata).__name__}: {hata}"[:300]

    if yanit.stop_reason in ("refusal", "max_tokens"):
        return None, f"yanıt {yanit.stop_reason}"
    try:
        veri = json.loads(next(b.text for b in yanit.content if b.type == "text"))
    except Exception as hata:
        return None, f"ayrıştırılamadı: {type(hata).__name__}"
    veri["model"] = model
    veri["effort"] = effort or "high"
    veri["token"] = {"girdi": yanit.usage.input_tokens, "cikti": yanit.usage.output_tokens}
    veri["maliyet_usd"] = round(
        analiz.maliyet(model, yanit.usage.input_tokens, yanit.usage.output_tokens), 4)
    return veri, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", default=None)
    ap.add_argument("--adet", type=int, default=45)
    ap.add_argument("--varyant", action="append", default=[],
                    help="etiket:model:effort (birden fazla verilebilir)")
    ap.add_argument("--denetim-model", default="claude-sonnet-5")
    ap.add_argument("--kuru", action="store_true")
    args = ap.parse_args()

    varyantlar = args.varyant or ["opus5-max:claude-opus-5:max",
                                  "fable51:claude-fable-5-1:high"]
    gun = args.gun or datetime.now(timezone.utc).date().isoformat()
    latest = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
    secilen = analiz.kayitlari_sec(latest["haberler"], gun, args.adet)
    takip = analiz.takip_oku()
    birincil = analiz.birincil_blogu()
    istem = analiz.istem_yap(secilen, latest.get("kumeler", {}), gun, True,
                             gecmis=analiz.gecmis_ozeti(),
                             takip=analiz.takip_ozeti(takip), birincil=birincil)
    print(f"gün {gun} · {len(secilen)} kayıt · istem {len(istem)} karakter "
          f"(~{len(istem)//3.5:.0f} token) · {len(varyantlar)} varyant")

    if args.kuru:
        for v in varyantlar:
            etiket, model, effort = (v.split(":") + ["", ""])[:3]
            print(f"  {etiket:12s} {model:22s} effort={effort or 'high'} "
                  f"≈ ${analiz.maliyet(model, len(istem)//3.5, 12000):.2f}")
        return 0

    import anthropic
    client = anthropic.Anthropic()
    KALITE.mkdir(parents=True, exist_ok=True)
    sonuclar = {}

    # Uretimdeki analiz karsilastirma tabani
    uretim = DATA / "analiz" / f"{gun}.json"
    if uretim.exists():
        taban = json.loads(uretim.read_text(encoding="utf-8"))
        sonuclar["üretim (opus5/high)"] = olcumler(taban)

    for v in varyantlar:
        etiket, model, effort = (v.split(":") + ["", ""])[:3]
        print(f"\n— {etiket}: {model} effort={effort or 'high'}")
        veri, hata = uret(client, model, effort, istem)
        if hata:
            print(f"  başarısız: {hata}")
            sonuclar[etiket] = {"hata": hata}
            continue
        print(f"  token {veri['token']['girdi']} girdi / {veri['token']['cikti']} çıktı "
              f"· ${veri['maliyet_usd']}")
        veri.setdefault("gun", gun)
        veri.setdefault("kullanilan_kayitlar", [h["k"] for h in secilen])
        denetim = analiz.denetim_yap(veri, secilen, latest.get("kumeler", {}), True,
                                     args.denetim_model, birincil,
                                     gecmis=analiz.gecmis_ozeti(),
                                     takip=analiz.takip_ozeti(takip))
        if denetim and not denetim.get("hata"):
            veri["denetim"] = denetim
            veri["maliyet_usd"] = round(veri["maliyet_usd"] + denetim.get("maliyet_usd", 0), 4)
            print(f"  denetim: {denetim['iddia_sayisi']} iddia, "
                  f"{sum(1 for k in denetim['kontroller'] if k['hukum'] != 'dayanaklı')} işaretli")
        elif denetim:
            print(f"  denetim yapılamadı: {denetim['hata']}")
        (KALITE / f"{gun}-{etiket}.json").write_text(
            json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
        sonuclar[etiket] = olcumler(veri)

    ozet = {"gun": gun, "olusturma": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "kayit_sayisi": len(secilen), "varyantlar": sonuclar}
    (KALITE / f"{gun}-ozet.json").write_text(json.dumps(ozet, ensure_ascii=False, indent=1),
                                             encoding="utf-8")

    basliklar = ["one_cikan", "birincil_not", "kronoloji", "ayrinti_satiri", "karsi_okuma",
                 "rakam", "rakam_yogunlugu", "atif_edilen_kayit", "denetim_orani", "maliyet_usd"]
    print("\n" + "-" * 78)
    print(f"{'varyant':22s}" + "".join(f"{b[:11]:>12s}" for b in basliklar[:5]))
    for ad, o in sonuclar.items():
        if "hata" in o:
            print(f"{ad:22s}  HATA: {o['hata'][:50]}")
            continue
        print(f"{ad:22s}" + "".join(f"{str(o[b]):>12s}" for b in basliklar[:5]))
    print()
    print(f"{'varyant':22s}" + "".join(f"{b[:11]:>12s}" for b in basliklar[5:]))
    for ad, o in sonuclar.items():
        if "hata" in o:
            continue
        print(f"{ad:22s}" + "".join(f"{str(o[b]):>12s}" for b in basliklar[5:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
