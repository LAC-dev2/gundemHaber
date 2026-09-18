#!/usr/bin/env python3
"""Gunun analizi yapilmadiysa yapilmasini ister.

GitHub zamanlanmis kosulari en iyi caba ile calistirir; bu depoda gecikme
duzenli olarak 3-4,5 saat. Bu betik saat tutturmaya calismaz: calistigi
anda yayindaki analizin tarihine bakar, bugune ait analiz yoksa is
akisini tetikler. Bilgisayarin gun icinde bir kez acilmasi yeter.

  python3 scripts/tetikle.py            # gerekiyorsa tetikle
  python3 scripts/tetikle.py --kuru     # yalnizca durumu soyle
  python3 scripts/tetikle.py --zorla    # analiz varsa da yeniden uret

Anahtar: repo uzerinde "actions: write" yetkisi olan bir GitHub jetonu.
Sirayla su yerlere bakilir:
  GUNDEM_TOKEN ortam degiskeni
  GITHUB_TOKEN ortam degiskeni
  ~/.gundem_token dosyasi (tek satir)

macOS'ta her acilista ve saatte bir denemek icin (bilgisayar acikken):
  ~/Library/LaunchAgents/com.bhm.gundem.tetikle.plist  — README'de ornek var
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEPO = os.environ.get("GUNDEM_DEPO") or "LAC-dev2/gundemHaber"
DAL = os.environ.get("GUNDEM_DAL") or "claude/trusting-ritchie-qqutwf"
IS_AKISI = "tarama.yml"
YAYIN = f"https://raw.githubusercontent.com/{DEPO}/{DAL}/data"
EN_ERKEN = int(os.environ.get("ANALIZ_EN_ERKEN") or 6)     # UTC


def jeton() -> str | None:
    for ad in ("GUNDEM_TOKEN", "GITHUB_TOKEN"):
        deger = os.environ.get(ad)
        if deger:
            return deger.strip()
    dosya = Path.home() / ".gundem_token"
    if dosya.exists():
        return dosya.read_text(encoding="utf-8").strip() or None
    return None


def yayindaki(ad: str) -> dict | None:
    try:
        istek = urllib.request.Request(f"{YAYIN}/{ad}?t={datetime.now().timestamp():.0f}",
                                       headers={"User-Agent": "gundem-tetikle"})
        with urllib.request.urlopen(istek, timeout=20) as yanit:
            return json.loads(yanit.read(2_000_000))
    except Exception as hata:
        print(f"{ad} okunamadi: {type(hata).__name__}")
        return None


def tetikle(token: str, girdiler: dict) -> bool:
    govde = json.dumps({"ref": DAL, "inputs": girdiler}).encode()
    istek = urllib.request.Request(
        f"https://api.github.com/repos/{DEPO}/actions/workflows/{IS_AKISI}/dispatches",
        data=govde, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json",
                 "User-Agent": "gundem-tetikle"})
    try:
        with urllib.request.urlopen(istek, timeout=25) as yanit:
            return yanit.status in (201, 204)
    except urllib.error.HTTPError as hata:
        ayrinti = hata.read(2000).decode("utf-8", "replace")
        print(f"tetikleme basarisiz ({hata.code}): {ayrinti[:300]}")
        if hata.code in (401, 403):
            print("Jeton 'actions: write' yetkisi tasimali ve depoya erisebilmeli.")
        return False
    except Exception as hata:
        print(f"tetikleme basarisiz: {type(hata).__name__}: {hata}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="tetiklemeden yalnızca durumu söyle")
    ap.add_argument("--zorla", action="store_true", help="analiz varsa da yeniden üret")
    args = ap.parse_args()

    simdi = datetime.now(timezone.utc)
    bugun = simdi.date().isoformat()
    analiz = yayindaki("analiz-latest.json")
    durum = yayindaki("analiz-durum.json") or {}
    var = bool(analiz and analiz.get("gun") == bugun)

    print(f"bugün: {bugun} · yayındaki analiz: {analiz.get('gun') if analiz else '—'}"
          f" · son deneme: {durum.get('durum', '—')} ({durum.get('zaman', '—')})")

    if var and not args.zorla:
        print("bugünün analizi yayında; tetiklemeye gerek yok.")
        return 0
    if not args.zorla and simdi.hour < EN_ERKEN:
        print(f"saat {simdi:%H:%M} UTC — günün kayıtları henüz gelmedi, "
              f"analiz en erken {EN_ERKEN:02d}:00 UTC'de üretilir. Beklemede.")
        return 0
    if args.kuru:
        print("kuru koşu: tetiklenecekti.")
        return 0

    token = jeton()
    if not token:
        print("Jeton yok. GUNDEM_TOKEN ya da ~/.gundem_token gerekli.")
        return 1

    girdiler = {"discover": "60", "analiz": "evet",
                "analiz_yenile": "evet" if args.zorla else "hayir"}
    if tetikle(token, girdiler):
        print("tarama + analiz tetiklendi. Sonuç birkaç dakika içinde yayına girer.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
