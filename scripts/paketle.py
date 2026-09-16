#!/usr/bin/env python3
"""Paylasim paketleri uretir.

  python3 scripts/paketle.py            # tek dosyalik HTML (hicbir sey kurmadan acilir)
  python3 scripts/paketle.py --zip      # calistirilabilir surum (zip, Python gerekir)
  python3 scripts/paketle.py --gorsel 0 # gorselleri gomme (daha kucuk dosya)

Tek dosyalik HTML: stil, betik ve veri tek bir .html icine gomulur. Alici dosyayi
cift tiklar (iPhone'da Dosyalar uygulamasindan dokunur), tarayicida acilir.
Tarama yapmaz; paketi hazirladigin andaki gorunumu tasir.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import stat
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
DATA = ROOT / "data"
NOW = datetime.now()
TODAY = NOW.strftime("%Y-%m-%d")
STAMP = NOW.strftime("%Y-%m-%d-%H%M")      # her paket ayri ad: eskisiyle karismaz
FOLDER = f"gundem-takip-{STAMP}"           # zip icindeki kok klasor de damgali

ZIP_INCLUDE = ("index.html", "haber.html", "OKUBENI.md", "README.md",
               "Baslat.bat", "Baslat.command", "baslat.sh",
               "manifest.webmanifest", "icon.svg", "icon-180.png", "icon-512.png")
# macOS Arsiv Yardimcisi bu kipi geri yukler: cift tiklama calisir
EXECUTABLE = {"Baslat.command", "baslat.sh"}
APP = "Gündem Takip.app"      # Terminal acmadan calisan macOS sarmalayicisi
ZIP_DIRS = ("assets", "scripts")
ZIP_DATA = ("latest.json", "sources.json", "feeds.json", "archive-index.json",
            "health.json", "images.json", "gundem.xml")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def embed_images(rows: list[dict], budget: int, limit: int) -> int:
    """Yerel aynadaki kucuk gorselleri data: URI olarak gomer."""
    used = 0
    for row in rows:
        local = row.get("yerel")
        if not local:
            continue
        path = ROOT / local
        if not path.exists():
            continue
        size = path.stat().st_size
        if size > limit or used + size > budget:
            continue
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        row["yerel"] = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
        used += size
    return used


def surum() -> dict:
    return {"paket": NOW.isoformat(timespec="minutes"),
            "damga": NOW.strftime("%d.%m.%Y %H:%M")}


def build_html(args: argparse.Namespace) -> Path:
    latest = json.loads(read(DATA / "latest.json"))
    veri = {
        "data/latest.json": latest,
        "data/sources.json": json.loads(read(DATA / "sources.json")),
        "data/feeds.json": json.loads(read(DATA / "feeds.json")),
        "data/archive-index.json": [],      # paket kipinde arsiv gezinmesi kapali
        "data/surum.json": surum(),
    }
    pages = 0
    for row in latest.get("haberler", []):
        page = DATA / "pages" / f"{row.get('k')}.json"
        if row.get("k") and page.exists():
            veri[f"data/pages/{row['k']}.json"] = json.loads(read(page))
            pages += 1

    gomulu = embed_images(latest.get("haberler", []),
                          args.gorsel * 1_000_000, args.gorsel_limit * 1000) if args.gorsel else 0

    page_html = read(ROOT / "index.html")
    style = read(ROOT / "assets" / "style.css")
    app = read(ROOT / "assets" / "app.js")
    haber = read(ROOT / "assets" / "haber.js")

    notice = (
        '<div class="wrap"><p class="snapshot"><b>Paylaşım kopyası.</b> '
        f'{datetime.now():%d.%m.%Y %H:%M} taramasının görünümünü taşır; kendi kendine '
        'yenilenmez. Güncel tarama için uygulamanın kendisi çalıştırılır '
        '(<code>python3 scripts/serve.py</code>).</p></div>'
    )
    head_extra = (
        "<style>\n" + style + "\n"
        ".snapshot{background:var(--surface-2);border:1px solid var(--rule);"
        "border-left:4px solid var(--kr);border-radius:4px;padding:11px 15px;"
        "margin:18px 0 0;font-size:.85rem;color:var(--ink-2)}"
        ".snapshot b{color:var(--ink);font-weight:600}\n</style>\n"
        "<script>window.__VERI__=" + json.dumps(veri, ensure_ascii=False, separators=(",", ":")) + ";</script>"
    )

    out = page_html
    out = re.sub(r'\s*<link rel="stylesheet" href="assets/style\.css">', "", out)
    out = re.sub(r'\s*<link rel="manifest"[^>]*>', "", out)
    out = out.replace("</head>", head_extra + "\n</head>")
    out = out.replace('<main class="wrap">', notice + '\n<main class="wrap">', 1)
    out = out.replace('<script src="assets/app.js"></script>',
                      "<script>\n" + haber + "\n</script>\n<script>\n" + app + "\n</script>")

    DIST.mkdir(exist_ok=True)
    target = DIST / f"gundem-takip-{STAMP}.html"
    target.write_text(out, encoding="utf-8")
    mb = target.stat().st_size / 1e6
    print(f"tek dosya: {target.relative_to(ROOT)}  ({mb:.1f} MB · "
          f"{len(latest.get('haberler', []))} kayıt · {pages} tam metin · "
          f"{gomulu / 1e6:.1f} MB gömülü görsel)")
    return target


def build_zip(tam: bool = False, butce: int = 25) -> Path:
    """Calistirilabilir paket. tam=True ise indirilmis tam metinler ve
    gorseller de eklenir (alici ilk taramayi beklemeden dolu bir ekran gorur)."""
    DIST.mkdir(exist_ok=True)
    target = DIST / (f"gundem-takip-{STAMP}-tam.zip" if tam else f"gundem-takip-{STAMP}.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ZIP_INCLUDE:
            path = ROOT / name
            if not path.exists():
                continue
            if name in EXECUTABLE:
                info = zipfile.ZipInfo(f"{FOLDER}/{name}")
                info.external_attr = (stat.S_IFREG | 0o755) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, path.read_bytes())
            else:
                zf.write(path, f"{FOLDER}/{name}")
        for folder in ZIP_DIRS:
            for path in sorted((ROOT / folder).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    zf.write(path, f"{FOLDER}/{path.relative_to(ROOT)}")
        # macOS uygulama paketi: cift tiklanir, Terminal penceresi acilmaz
        mac = ROOT / "mac"
        if (mac / "gundem").exists():
            zf.writestr(f"{FOLDER}/{APP}/Contents/Info.plist",
                        (mac / "Info.plist").read_text(encoding="utf-8"))
            zf.writestr(f"{FOLDER}/{APP}/Contents/PkgInfo",
                        (mac / "PkgInfo").read_text(encoding="utf-8"))
            info = zipfile.ZipInfo(f"{FOLDER}/{APP}/Contents/MacOS/gundem")
            info.external_attr = (stat.S_IFREG | 0o755) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, (mac / "gundem").read_bytes())

        zf.writestr(f"{FOLDER}/data/surum.json",
                    json.dumps(surum(), ensure_ascii=False))
        for name in ZIP_DATA:
            path = DATA / name
            if path.exists():
                zf.write(path, f"{FOLDER}/data/{name}")
        if tam:
            sayfa = 0
            for path in sorted((DATA / "pages").glob("*.json")):
                zf.write(path, f"{FOLDER}/data/pages/{path.name}")
                sayfa += 1
            # gorseller: kucukten buyuge, butce dolana kadar
            gorsel, kullanilan = 0, 0
            for path in sorted((DATA / "img").glob("*"), key=lambda f: f.stat().st_size):
                size = path.stat().st_size
                if kullanilan + size > butce * 1_000_000:
                    break
                zf.write(path, f"{FOLDER}/data/img/{path.name}")
                gorsel += 1
                kullanilan += size
            print(f"  eklenen: {sayfa} tam metin, {gorsel} görsel "
                  f"({kullanilan / 1e6:.1f} MB)")
    print(f"çalıştırılabilir paket: {target.relative_to(ROOT)} "
          f"({target.stat().st_size / 1e6:.1f} MB)")
    return target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", action="store_true", help="calistirilabilir zip paketi de uret")
    ap.add_argument("--tam", action="store_true",
                    help="zip'e indirilmis tam metinleri ve gorselleri de koy")
    ap.add_argument("--zip-butce", type=int, default=25,
                    help="tam zip'e eklenecek gorseller icin MB butcesi")
    ap.add_argument("--gorsel", type=int, default=14,
                    help="gomulecek gorseller icin MB butcesi (0 = gomme)")
    ap.add_argument("--gorsel-limit", type=int, default=250,
                    help="gomulecek tek gorsel ust siniri (KB)")
    args = ap.parse_args()
    build_html(args)
    if args.zip or args.tam:
        build_zip(tam=args.tam, butce=args.zip_butce)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
