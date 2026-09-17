#!/usr/bin/env python3
"""Gundem Takip - yerel uygulama.

Tek komutla: kaynaklari tarar, tam metin ve gorselleri diske indirir, siteyi
yerel sunucuda acar ve istenirse belirli araliklarla taramayi yineler.

  python3 scripts/serve.py                     # tara + tarayicida ac
  python3 scripts/serve.py --every 30          # 30 dakikada bir yeniden tara
  python3 scripts/serve.py --no-scan           # taramadan yalnizca sun
  python3 scripts/serve.py --port 9000 --full 80 --mirror 120
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if sys.version_info < (3, 9):
    raise SystemExit("Bu uygulama Python 3.9 veya uzerini gerektirir. "
                     f"Kurulu surum: {sys.version.split()[0]}")

ROOT = Path(__file__).resolve().parent.parent
COLLECT = ROOT / "scripts" / "collect.py"
LATEST = ROOT / "data" / "latest.json"


class Handler(SimpleHTTPRequestHandler):
    """Onbelleksiz servis + tek haber analizi ucu."""

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def do_POST(self):                      # noqa: N802 (http.server arayuzu)
        if self.path.rstrip("/") != "/api/analiz-et":
            self.send_error(404, "Bilinmeyen uc")
            return
        try:
            uzunluk = int(self.headers.get("Content-Length", 0))
            istek = json.loads(self.rfile.read(uzunluk) or b"{}")
        except Exception:
            self.cevapla({"hata": "İstek okunamadı."}, 400)
            return

        url = str(istek.get("url", "")).strip()
        metin = str(istek.get("metin", "")).strip()
        if url and not url.startswith(("http://", "https://")):
            self.cevapla({"hata": "Adres http:// veya https:// ile başlamalı."}, 400)
            return
        if not url and len(metin) < 200:
            self.cevapla({"hata": "Bir haber adresi ver ya da en az 200 karakter metin yapıştır."}, 400)
            return

        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from analiz_tek import analiz_et
            sonuc = analiz_et(url=url, metin=metin,
                              model=istek.get("model") or os.environ.get("ANALIZ_MODEL")
                              or "claude-opus-5")
        except Exception as exc:            # tek analiz hatasi sunucuyu dusurmesin
            sonuc = {"hata": f"Analiz sırasında hata: {type(exc).__name__}: {exc}"}
        self.cevapla(sonuc, 200 if "hata" not in sonuc else 502)

    def cevapla(self, veri: dict, kod: int = 200) -> None:
        govde = json.dumps(veri, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def log_message(self, fmt, *args):       # sunucu gurultusunu kis
        if "404" in (fmt % args):
            sys.stderr.write("  ! bulunamadi: %s\n" % (args[0] if args else ""))


def scan(opts: argparse.Namespace) -> None:
    cmd = [sys.executable, "-u", str(COLLECT),
           "--discover", str(opts.discover), "--news", str(opts.news),
           "--images", str(opts.images), "--full", str(opts.full),
           "--mirror", str(opts.mirror), "--workers", str(opts.workers)]
    print(f"\n[{datetime.now():%H:%M:%S}] tarama basladi…")
    started = time.time()
    try:
        subprocess.run(cmd, cwd=ROOT, check=False)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"  tarama hatasi: {exc}")
        return
    print(f"[{datetime.now():%H:%M:%S}] tarama bitti ({time.time() - started:.0f} sn)")


def data_age_minutes() -> float | None:
    if not LATEST.exists():
        return None
    try:
        stamp = json.loads(LATEST.read_text(encoding="utf-8"))["olusturma"]
        made = datetime.fromisoformat(stamp)
        if not made.tzinfo:
            made = made.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - made).total_seconds() / 60
    except Exception:
        return None


def loop(opts: argparse.Namespace) -> None:
    while True:
        time.sleep(opts.every * 60)
        scan(opts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Gundem Takip yerel uygulamasi")
    ap.add_argument("--port", type=int, default=8000,
                    help="0 verilirse bos bir portu isletim sistemi secer")
    ap.add_argument("--no-scan", dest="scan", action="store_false",
                    help="baslangicta tarama yapmadan yalnizca sun")
    ap.add_argument("--every", type=int, default=0,
                    help="dakika cinsinden yeniden tarama araligi (0 = kapali)")
    ap.add_argument("--stale", type=int, default=120,
                    help="veri bu kadar dakikadan eskiyse baslangicta tara")
    ap.add_argument("--no-open", dest="open", action="store_false",
                    help="tarayiciyi acma")
    ap.add_argument("--discover", type=int, default=40)
    ap.add_argument("--news", type=int, default=140)
    ap.add_argument("--images", type=int, default=90)
    ap.add_argument("--full", type=int, default=60)
    ap.add_argument("--mirror", type=int, default=120)
    ap.add_argument("--workers", type=int, default=20)
    opts = ap.parse_args()

    age = data_age_minutes()
    if opts.scan and (age is None or age > opts.stale):
        scan(opts)
    elif age is not None:
        print(f"veri {age:.0f} dakika onceki taramadan; yenisi icin "
              f"--stale 0 kullanabilirsin.")

    if opts.every:
        threading.Thread(target=loop, args=(opts,), daemon=True).start()
        print(f"otomatik tarama: her {opts.every} dakikada bir")

    # Port mesgulse (baska bir uygulama ya da ayni uygulamanin acik kopyasi)
    # sessizce bir sonrakini dene; kullaniciya hata yigini gostermeye gerek yok.
    server = None
    port = opts.port
    for candidate in range(opts.port, opts.port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate),
                                         partial(Handler, directory=str(ROOT)))
            port = server.server_address[1]   # --port 0 ise isletim sistemi secer
            break
        except OSError as exc:
            if exc.errno not in (48, 98, 10048):     # adres kullanimda
                raise
            print(f"  {candidate} portu meşgul; {candidate + 1} deneniyor…")
    if server is None:
        raise SystemExit(f"{opts.port}-{opts.port + 19} arasindaki portlarin hepsi "
                         "mesgul. --port ile baska bir port verebilirsin.")
    if port != opts.port:
        print(f"  (uygulama {port} portunda açıldı)")

    url = f"http://127.0.0.1:{port}/"
    anahtar = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    print(f"\nGündem Takip çalışıyor:  {url}")
    print("analiz ucu: " + ("açık (ANTHROPIC_API_KEY bulundu)"
                            if anahtar else
                            "kapalı — açmak için: ANTHROPIC_API_KEY=sk-ant-… ile başlat"))
    print("kapatmak için Ctrl+C\n")
    if opts.open:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nkapatiliyor…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
