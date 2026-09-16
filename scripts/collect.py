#!/usr/bin/env python3
"""BHM Gundem Takip - kaynak tarayici.

data/sources.json icindeki kaynaklarin RSS/Atom akislarini bulur, tarar ve
site tarafindan okunan data/latest.json + data/archive/YYYY-MM-DD.json
dosyalarini uretir.

  python3 scripts/collect.py              # normal tarama
  python3 scripts/collect.py --discover 0 # yeni akis arama yapmadan tara
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import html
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import extract as extract_text   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ARCHIVE = DATA / "archive"
PAGES = DATA / "pages"          # yerel uygulama: tam metin
IMGDIR = DATA / "img"           # yerel uygulama: gorsel aynasi

UA = "Mozilla/5.0 (compatible; BHM-GundemBot/1.0; +https://github.com/LAC-dev2/gundemHaber)"
HEADERS = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "tr,en;q=0.8"}
TIMEOUT = 25
DISCOVER_TIMEOUT = 10        # kesif isteklerinde kisa zaman asimi
DISCOVER_BUDGET = 45         # tek kaynak icin kesif sure butcesi (sn)
WINDOW_DAYS = 21          # latest.json icinde tutulan gun sayisi
MAX_ITEMS = 900           # latest.json ust siniri
MAX_PER_FEED = 25
CANDIDATES = ("/feed/", "/rss", "/feed", "/rss.xml", "/atom.xml", "/index.xml",
              "/?feed=rss2", "/en/rss", "/feeds/posts/default", "/news/rss",
              "/rss/", "/en/feed/")
# Elle dogrulanmis kurumsal akislar (otomatik kesif bu adresleri bulamiyor)
SEED_FEEDS = (
    "https://www.europarl.europa.eu/rss/doc/press-releases/en.xml",
    "https://fra.europa.eu/en/rss.xml",
    "https://ec.europa.eu/commission/presscorner/api/rss?language=en",
    "https://edri.org/feed/",
    "https://ecre.org/feed/",
    "https://verfassungsblog.de/feed/",
    "https://strasbourgobservers.com/feed/",
    "https://www.statewatch.org/feed/",
    "https://www.article19.org/feed/",
    "https://www.frontlinedefenders.org/en/rss.xml",
    "https://cpj.org/feed/",
    "https://www.hrw.org/rss/news",
    "https://www.amnesty.org/en/rss/",
    "https://www.icj.org/feed/",
    "https://www.icc-cpi.int/rss.xml",
    "https://www.lawyersforlawyers.org/en/feed/",
    "https://www.tihv.org.tr/feed/",
    "https://www.evrensel.net/rss/haber.xml",
    "https://turkishminute.com/feed/",
    "https://www.nordicmonitor.com/feed/",
    "https://tr724.com/feed/",
    "https://boldmedya.com/feed/",
)
# RSS yayini olmayan kaynaklar icin alan adina kilitli haber aramasi
NEWS_BASE = "https://news.google.com/rss/search?q={q}&hl=tr&gl=TR&ceid=TR:tr"
NEWS_PRIORITIES = ("Kritik", "Yüksek")
NEWS_FREQUENCIES = ("Günlük", "Haftalık")


def source_terms(src: dict) -> list[str]:
    """Kaynagin anahtar terimlerini listeler."""
    raw = re.split(r"[,;/]", (src.get("anahtar") or ""))
    return [t.strip() for t in raw if len(t.strip()) > 4][:4]


def news_url(src: dict, domain: str) -> str:
    """Alan adina kilitli, kaynagin anahtar terimleriyle daraltilmis arama."""
    terms = source_terms(src)
    query = f"site:{domain}"
    if terms:
        joined = " OR ".join(f'"{t}"' if " " in t else t for t in terms)
        query += f" ({joined})"
    return NEWS_BASE.format(q=urllib.parse.quote(query))

RECHECK_FOUND_DAYS = 30   # bulunan akis ne kadar sonra yeniden dogrulanir
RECHECK_NONE_DAYS = 21    # bulunamayan kaynak ne kadar sonra yeniden aranir

NOW = datetime.now(timezone.utc)
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE   # kamu kurumlarinin eksik sertifika zincirleri


# --------------------------------------------------------------------------- ag
def fetch(url: str, limit: int = 1_500_000, timeout: int = TIMEOUT) -> tuple[str, bytes]:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
        return resp.headers.get("Content-Type", ""), resp.read(limit)


def looks_like_feed(body: bytes) -> bool:
    head = body[:3000].lower()
    return (b"<rss" in head or b"<rdf:rdf" in head
            or (b"<feed" in head and b"xmlns" in head))


def discover(url: str) -> str | None:
    """Bir sayfadan RSS/Atom akisini bulmaya calisir (zaman butcesi ile)."""
    deadline = time.monotonic() + DISCOVER_BUDGET
    try:
        _, body = fetch(url, 400_000, DISCOVER_TIMEOUT)
    except Exception:
        body = b""
    if body and looks_like_feed(body):
        return url
    if body:
        for tag in re.findall(rb"<link[^>]+>", body[:200_000], re.I):
            low = tag.lower()
            if b"alternate" in low and (b"rss" in low or b"atom" in low):
                m = re.search(rb"""href=["']([^"']+)""", tag, re.I)
                if m:
                    return urllib.parse.urljoin(url, html.unescape(m.group(1).decode("utf-8", "replace")))
    parts = urllib.parse.urlparse(url)
    if not parts.scheme:
        return None
    base = f"{parts.scheme}://{parts.netloc}"
    for cand in CANDIDATES:
        if time.monotonic() > deadline:
            break
        try:
            _, body = fetch(base + cand, 200_000, DISCOVER_TIMEOUT)
        except Exception:
            continue
        if looks_like_feed(body):
            return base + cand
    return None


# ------------------------------------------------------------------- ayristirma
def _text(el) -> str:
    return "".join(el.itertext()) if el is not None else ""


TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def clean(raw: str, limit: int = 320) -> str:
    txt = WS.sub(" ", html.unescape(TAG.sub(" ", raw or ""))).strip()
    return txt[:limit].rstrip() + ("…" if len(txt) > limit else "")


# Akis ozetlerinin basina takilan arayuz/CMS kaliplari
NOISE_PREFIXES = re.compile(
    r"^(?:click to expand|image|language\s+english|summary|press release"
    r"|read more|lire la suite|share this|type\s|page blocks)\b[\s:–—-]*", re.I)
BYLINE_ONLY = re.compile(r"^[\w.\-' ]{1,40},?\s*\d{1,2}[/.]\d{1,2}[/.]\d{2,4}"
                         r"(?:\s*[-–]\s*\d{1,2}[:.]\d{2})?\s*$")


def tidy_summary(text: str, title: str) -> str:
    """Ozetten baslik tekrarini, CMS kaliplarini ve yalin imza satirlarini ayiklar."""
    out = text.strip()
    if out[:40] and out.lower().startswith(title[:40].lower()):
        out = out[len(title):].lstrip(" -–—:·|").strip()
    for _ in range(4):
        trimmed = NOISE_PREFIXES.sub("", out).strip()
        if trimmed == out:
            break
        out = trimmed
    if BYLINE_ONLY.match(out) or len(out) < 25:
        return ""
    return out


DATE_FORMATS = ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M %z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def parse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    raw = re.sub(r"\s+", " ", raw).replace("GMT", "+0000").replace("UTC", "+0000")
    raw = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", raw)
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


JUNK_TITLE = re.compile(r"^[\d\W_]+$")


FOLD = str.maketrans("çğıöşüâîûÇĞİÖŞÜÂÎÛ", "cgiosuaiucgiosuaiu")


def fold(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.translate(FOLD).lower())


def useful_title(title: str, source_name: str = "") -> bool:
    """Numara, dosya kimligi ve yalnizca kaynak adini tekrarlayan basliklari ayiklar."""
    if len(title) < 12 or JUNK_TITLE.match(title) or URLISH_TITLE.search(title):
        return False
    core = fold(title)
    return bool(core) and core not in fold(source_name)


def strip_publisher(title: str) -> str:
    """Google News basliklarindaki ' - Yayin adi' kuyrugunu atar."""
    head, sep, tail = title.rpartition(" - ")
    return head.strip() if sep and len(tail) < 40 and head.strip() else title


IMG_IN_HTML = re.compile(rb"""<img[^>]+src=["']([^"']+)""", re.I)
OG_IMAGE = re.compile(
    rb"""<meta[^>]+(?:property|name)=["'](?:og:image(?::secure_url)?|twitter:image)["'][^>]*>""",
    re.I)
CONTENT_ATTR = re.compile(rb"""(?:content|value)=["']([^"']+)""", re.I)


# Logo, paylasim karti ve yer tutucu gorselleri haber gorseli sayilmaz
IMG_BLOCK = re.compile(r"(?:logo|favicon|avatar|sprite|placeholder|no-?image"
                       r"|meta-facebook|default[-_.]|og[-_]default"
                       r"|piwik|matomo|analytics|pixel|beacon|track(?:er|ing)?"
                       r"|1x1|spacer|blank)", re.I)
URLISH_TITLE = re.compile(r"[\w-]+\.(?:gov|com|org|net|edu|info|be|tr|eu|nl|fr|de)"
                          r"(?:\.[a-z]{2})?/?\s*$", re.I)


MIN_IMAGE_BYTES = 3_000      # izleme pikseli / bozuk dosya esigi
MAX_IMAGE_BYTES = 2_500_000  # yerel aynada tek gorsel siniri


def usable_image(url: str) -> str:
    parts = urllib.parse.urlparse(url)
    if not url or IMG_BLOCK.search(parts.path) or IMG_BLOCK.search(parts.query):
        return ""
    return url


def item_key(url: str) -> str:
    """Haber sayfasi icin kalici kayit anahtari."""
    return hashlib.sha1(url.encode("utf-8", "replace")).hexdigest()[:10]


def pick_media(node, fields: dict, link: str) -> str:
    """Akis ogesinden gorsel adresi cikarir (enclosure, media:*, gomulu img)."""
    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()
    for child in node.iter():
        name = local(child.tag)
        if name not in ("enclosure", "thumbnail", "content", "image"):
            continue
        url = child.attrib.get("url") or child.attrib.get("href")
        kind = (child.attrib.get("type", "") + child.attrib.get("medium", "")).lower()
        if url and ("image" in kind or not kind or name == "thumbnail"):
            if re.search(r"\.(?:jpe?g|png|webp|gif|avif)(?:[?#]|$)", url, re.I) or "image" in kind:
                return usable_image(urllib.parse.urljoin(link, url))
    for key in ("encoded", "content", "description", "summary"):
        raw = (fields.get(key) or "").encode("utf-8", "replace")
        m = IMG_IN_HTML.search(raw)
        if m:
            found = usable_image(urllib.parse.urljoin(
                link, html.unescape(m.group(1).decode("utf-8", "replace"))))
            if found:
                return found
    return ""


def fetch_og_image(url: str) -> str:
    """Haber sayfasindan og:image / twitter:image adresini okur."""
    try:
        _, body = fetch(url, 300_000, DISCOVER_TIMEOUT)
    except Exception:
        return ""
    m = OG_IMAGE.search(body)
    if not m:
        return ""
    c = CONTENT_ATTR.search(m.group(0))
    if not c:
        return ""
    src = html.unescape(c.group(1).decode("utf-8", "replace")).strip()
    if not src or src.startswith("data:"):
        return ""
    return usable_image(urllib.parse.urljoin(url, src))


def parse_feed(body: bytes) -> list[dict]:
    """RSS 2.0 / RDF / Atom akisindan ogeleri cikarir (stdlib)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(re.sub(rb"^\s*<\?xml[^>]*\?>", b"", body.strip()))
    except ET.ParseError:
        try:
            root = ET.fromstring(body.decode("utf-8", "replace").encode("utf-8"))
        except Exception:
            return []
    out: list[dict] = []
    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    nodes = [n for n in root.iter() if local(n.tag) in ("item", "entry")]
    for node in nodes[:MAX_PER_FEED * 2]:
        fields: dict[str, str] = {}
        link = ""
        for child in node:
            name = local(child.tag)
            if name == "link":
                href = child.attrib.get("href")
                rel = child.attrib.get("rel", "alternate")
                if href and rel == "alternate" and not link:
                    link = href
                elif not href and _text(child).strip():
                    link = link or _text(child).strip()
            else:
                fields.setdefault(name, _text(child))
        title = clean(fields.get("title", ""), 240)
        if not title:
            continue
        summary = clean(fields.get("description") or fields.get("summary")
                        or fields.get("content") or fields.get("encoded", ""))
        dt = None
        for key in ("published", "pubdate", "updated", "date", "modified", "created"):
            dt = parse_date(fields.get(key, ""))
            if dt:
                break
        out.append({
            "g": pick_media(node, fields, link or ""),
            "t": title,
            "u": (link or "").strip(),
            "s": summary,
            "d": (dt or NOW).astimezone(timezone.utc).isoformat(timespec="minutes"),
            "nd": dt is None,
        })
        if len(out) >= MAX_PER_FEED:
            break
    return out


# ------------------------------------------------------------------------ puan
PRIORITY_WEIGHT = {"Kritik": 30, "Yüksek": 20, "Orta": 10, "Düşük": 4}


def word_pattern(term: str) -> re.Pattern:
    """Terimi sozcuk siniriyla arar (ornek: 'sayi' -> 'Sayin' eslesmez)."""
    return re.compile(r"(?<!\w)" + re.escape(term.lower()) + r"\w{0,4}(?!\w)")


def build_matcher(terms: list[str]):
    uniq = sorted({t.strip().lower() for t in terms if len(t.strip()) > 4},
                  key=len, reverse=True)
    pats = [(t, word_pattern(t)) for t in uniq]

    def match(text: str) -> list[str]:
        low = text.lower()
        hits = []
        for term, pat in pats:
            if pat.search(low):
                hits.append(term)
                if len(hits) == 5:
                    break
        return hits
    return match


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", type=int, default=90,
                    help="bu turda en fazla kac kaynak icin akis aramasi yapilsin")
    ap.add_argument("--news", type=int, default=140,
                    help="RSS yayini olmayan kac kaynak icin haber aramasi yapilsin (0 = kapali)")
    ap.add_argument("--images", type=int, default=90,
                    help="gorseli olmayan kac kayit icin sayfanin og:image'i cekilsin")
    ap.add_argument("--full", type=int, default=0,
                    help="kac kayit icin tam metin indirilsin (yerel uygulama; 0 = kapali)")
    ap.add_argument("--mirror", type=int, default=0,
                    help="kac gorsel diske indirilsin (yerel uygulama; 0 = kapali)")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    meta = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    sources = meta["sources"]
    cache_path = DATA / "feeds.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    def stale(entry: dict) -> bool:
        checked = parse_date(entry.get("checked", ""))
        if not checked:
            return True
        age = (NOW - checked).days
        return age > (RECHECK_FOUND_DAYS if entry.get("feed") else RECHECK_NONE_DAYS)

    # 1) akis kesfi -------------------------------------------------------
    todo = []
    for src in sources:
        for url in (src.get("links") or [])[:2]:
            if "google.com/search" in url or "x.com/" in url:
                continue
            entry = cache.get(url)
            if entry is None or stale(entry):
                todo.append(url)
    todo = todo[: max(args.discover, 0)]
    if todo:
        print(f"akis aramasi: {len(todo)} adres")
        with cf.ThreadPoolExecutor(args.workers) as ex:
            for url, feed in zip(todo, ex.map(discover, todo)):
                cache[url] = {"feed": feed,
                              "checked": NOW.isoformat(timespec="seconds")}

    # 2) kaynak -> akis eslesmesi -----------------------------------------
    seed_by_host = {urllib.parse.urlparse(f).netloc.replace("www.", ""): f for f in SEED_FEEDS}
    jobs: list[tuple[dict, str, str]] = []
    feed_urls: set[str] = set()
    news_used = 0
    for src in sources:
        seen: set[str] = set()
        hosts = {urllib.parse.urlparse(u).netloc.replace("www.", "")
                 for u in (src.get("links") or []) if u.startswith("http")}
        hosts.discard("www.google.com")
        hosts.discard("google.com")
        hosts.discard("x.com")
        for url in (src.get("links") or [])[:2]:
            feed = (cache.get(url) or {}).get("feed")
            if feed and feed not in seen:
                seen.add(feed)
                jobs.append((src, feed, "akış"))
        for host in hosts:
            feed = seed_by_host.get(host)
            if feed and feed not in seen:
                seen.add(feed)
                jobs.append((src, feed, "akış"))
        feed_urls |= seen
        if (not seen and hosts and news_used < args.news
                and src.get("oncelik") in NEWS_PRIORITIES
                and src.get("siklik") in NEWS_FREQUENCIES):
            news_used += 1
            jobs.append((src, news_url(src, sorted(hosts)[0]), "arama"))

    print(f"taranacak akis: {sum(1 for j in jobs if j[2] == 'akış')} | "
          f"haber aramasi: {news_used}")

    def pull(job):
        src, feed, kind = job
        try:
            _, body = fetch(feed)
            return src, feed, kind, parse_feed(body), None
        except Exception as exc:  # akis hatasi taramayi durdurmaz
            return src, feed, kind, [], f"{type(exc).__name__}"

    match = build_matcher(meta.get("alertTerms", []))
    cutoff = NOW - timedelta(days=WINDOW_DAYS)
    items: dict[str, dict] = {}
    errors = 0
    active_feeds = 0
    active_news = 0

    with cf.ThreadPoolExecutor(args.workers) as ex:
        for src, feed, kind, entries, err in ex.map(pull, jobs):
            if err:
                errors += 1
                continue
            if entries:
                if kind == "akış":
                    active_feeds += 1
                else:
                    active_news += 1
            for it in entries:
                if kind == "arama":
                    it["t"] = strip_publisher(it["t"])
                if not useful_title(it["t"], src["ad"]):
                    continue
                published = parse_date(it["d"]) or NOW
                if published < cutoff:
                    continue
                if published > NOW + timedelta(hours=12):
                    published = NOW
                url = it["u"] or feed
                key = re.sub(r"[?#].*$", "", url) or it["t"]
                summary = tidy_summary(it["s"], it["t"])
                blob = f"{it['t']} {summary}"
                low = blob.lower()
                terms = match(blob)
                for extra in source_terms(src):
                    if word_pattern(extra).search(low) and extra.lower() not in terms:
                        terms.append(extra.lower())
                terms = terms[:5]
                # Genel haber kaynaklari ve arama sonuclarinda konu ilgisi zorunlu:
                # kurum/izleme akislarinin tamami ilgilidir, genel basinin degil.
                general = ("Haber" in (src.get("tur") or "")
                           or src.get("kategori") in ("Haber", "Basın özgürlüğü"))
                if not terms and (kind == "arama" or general):
                    continue
                score = (PRIORITY_WEIGHT.get(src.get("oncelik", ""), 8)
                         + (0 if kind == "akış" else -8)
                         + 6 * len(terms)
                         + (12 if src.get("kanit", "").startswith("Birincil") else 0)
                         - min((NOW - published).days, 21))
                row = {
                    "id": src["id"], "kaynak": src["ad"], "bolge": src.get("bolge", ""),
                    "kategori": src.get("kategori", ""), "oncelik": src.get("oncelik", ""),
                    "kanit": src.get("kanit", ""), "tur": src.get("tur", ""),
                    "baslik": it["t"], "url": url, "ozet": summary,
                    "tarih": published.astimezone(timezone.utc).isoformat(timespec="minutes"),
                    "tahmini": it["nd"], "terimler": terms, "puan": score, "tip": kind,
                    "k": item_key(url), "gorsel": it.get("g", ""),
                }
                prev = items.get(key)
                if prev is None or row["puan"] > prev["puan"]:
                    items[key] = row

    rows = sorted(items.values(), key=lambda r: (r["tarih"], r["puan"]), reverse=True)[:MAX_ITEMS]

    # 3) gorsel tamamlama: akista gorsel yoksa sayfanin og:image'i ---------
    img_path = DATA / "images.json"
    imgs = json.loads(img_path.read_text(encoding="utf-8")) if img_path.exists() else {}
    missing = sorted([r for r in rows if not r["gorsel"]], key=lambda r: -r["puan"])
    todo_img = []
    for row in missing:
        hit = imgs.get(row["url"])
        if hit is None:
            todo_img.append(row)
        else:
            row["gorsel"] = usable_image(hit.get("img") or "")
    todo_img = todo_img[: max(args.images, 0)]
    if todo_img:
        with cf.ThreadPoolExecutor(args.workers) as ex:
            found = list(ex.map(fetch_og_image, [r["url"] for r in todo_img]))
        for row, img in zip(todo_img, found):
            imgs[row["url"]] = {"img": img, "checked": NOW.isoformat(timespec="seconds")}
            row["gorsel"] = img
    # onbellegi buyutmemek icin en eski kayitlari at
    if len(imgs) > 4000:
        kept = sorted(imgs.items(), key=lambda kv: kv[1].get("checked", ""), reverse=True)[:3000]
        imgs = dict(kept)
    img_path.write_text(json.dumps(imgs, ensure_ascii=False, indent=0, sort_keys=True),
                        encoding="utf-8")

    # 4) yerel uygulama: tam metin ve gorsel aynasi ------------------------
    if args.full:
        PAGES.mkdir(parents=True, exist_ok=True)
        todo_full = [r for r in rows if not (PAGES / f"{r['k']}.json").exists()][: args.full]

        def save_page(row: dict) -> bool:
            try:
                ctype, body = fetch(row["url"], 1_200_000)
            except Exception:
                return False
            paras = extract_text(body, ctype)
            if not paras:
                return False
            (PAGES / f"{row['k']}.json").write_text(json.dumps({
                "k": row["k"], "baslik": row["baslik"], "kaynak": row["kaynak"],
                "url": row["url"], "tarih": row["tarih"],
                "kelime": sum(len(x.split()) for x in paras),
                "paragraflar": paras,
                "cekim": NOW.isoformat(timespec="seconds"),
            }, ensure_ascii=False), encoding="utf-8")
            return True

        if todo_full:
            with cf.ThreadPoolExecutor(args.workers) as ex:
                got = sum(1 for ok in ex.map(save_page, todo_full) if ok)
            print(f"tam metin: {got}/{len(todo_full)} yeni")
        # mevcut tam metinleri isaretle, ozeti bossa ilk paragraftan tamamla
        for row in rows:
            page = PAGES / f"{row['k']}.json"
            if not page.exists():
                continue
            row["tam"] = True
            if not row["ozet"]:
                try:
                    paras = json.loads(page.read_text(encoding="utf-8"))["paragraflar"]
                    first = next((x for x in paras if not x.startswith("## ")), "")
                    row["ozet"] = clean(first, 320)
                except Exception:
                    pass

    if args.mirror:
        IMGDIR.mkdir(parents=True, exist_ok=True)

        def mirror(row: dict) -> bool:
            path = urllib.parse.urlparse(row["gorsel"]).path
            ext = re.search(r"\.(jpe?g|png|webp|gif|avif)$", path, re.I)
            name = f"{row['k']}.{(ext.group(1) if ext else 'jpg').lower()}"
            target = IMGDIR / name
            if target.exists():
                row["yerel"] = f"data/img/{name}"
                return True
            try:
                ctype, body = fetch(row["gorsel"], 5_000_000)
            except Exception:
                return False
            if (not body or len(body) < MIN_IMAGE_BYTES
                    or len(body) > MAX_IMAGE_BYTES
                    or ("image" not in ctype and not ext)):
                return False
            target.write_bytes(body)
            row["yerel"] = f"data/img/{name}"
            return True

        todo_img = [r for r in rows if r["gorsel"]][: args.mirror]
        if todo_img:
            with cf.ThreadPoolExecutor(args.workers) as ex:
                got = sum(1 for ok in ex.map(mirror, todo_img) if ok)
            print(f"gorsel aynasi: {got}/{len(todo_img)}")

    # 5) cikti -------------------------------------------------------------
    by_region: dict[str, int] = {}
    for r in rows:
        by_region[r["bolge"]] = by_region.get(r["bolge"], 0) + 1
    today = NOW.date().isoformat()
    feeds_known = len(feed_urls)

    latest = {
        "olusturma": NOW.isoformat(timespec="seconds"),
        "istatistik": {
            "kaynak": len(sources),
            "akisBulunan": feeds_known,
            "akisTaranan": sum(1 for j in jobs if j[2] == "akış"),
            "aramaKaynak": news_used,
            "aramaVeriVeren": active_news,
            "akisVeriVeren": active_feeds,
            "akisHata": errors,
            "haber": len(rows),
            "gorselli": sum(1 for r in rows if r["gorsel"]),
            "tamMetin": sum(1 for r in rows if r.get("tam")),
            "yerelGorsel": sum(1 for r in rows if r.get("yerel")),
            "bugun": sum(1 for r in rows if r["tarih"][:10] == today),
            "bolge": by_region,
            "pencereGun": WINDOW_DAYS,
        },
        "haberler": rows,
    }
    (DATA / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True),
                          encoding="utf-8")

    # gunluk arsiv (ayni gun icinde birikimli)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    day_rows = [r for r in rows if r["tarih"][:10] == today]
    day_file = ARCHIVE / f"{today}.json"
    if day_file.exists():
        try:
            old = json.loads(day_file.read_text(encoding="utf-8")).get("haberler", [])
        except Exception:
            old = []
        merged = {r["url"]: r for r in old}
        merged.update({r["url"]: r for r in day_rows})
        day_rows = sorted(merged.values(), key=lambda r: r["puan"], reverse=True)
    day_file.write_text(json.dumps({"gun": today, "haberler": day_rows},
                                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    index = sorted(p.stem for p in ARCHIVE.glob("*.json"))
    (DATA / "archive-index.json").write_text(json.dumps(index), encoding="utf-8")

    print(f"akis veri veren: {active_feeds}/{len(jobs)} (hata {errors}) | "
          f"haber {len(rows)} | gorselli {latest['istatistik']['gorselli']} | "
          f"bugun {latest['istatistik']['bugun']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
