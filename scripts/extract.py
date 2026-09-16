#!/usr/bin/env python3
"""Haber sayfasindan okunabilir tam metin cikarma (yalnizca stdlib).

Sezgisel yaklasim: gezinti/altlik/betik bloklarini at, paragraf ve ara baslik
etiketlerini topla, <article>/<main> icindekileri yeglе, kalip metinleri ayikla.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer",
             "aside", "form", "iframe", "button", "select", "template",
             "figure", "figcaption", "picture", "video", "audio", "table"}
BLOCK_TAGS = {"p", "h2", "h3", "h4", "blockquote", "pre"}
MAIN_TAGS = {"article", "main"}
STOP_MARKERS = re.compile(
    r"(?:yorumlar|comments?\s*\(|cookie|çerez|abone ol|subscribe to|newsletter"
    r"|share this|paylaş|bültenimize|ilgili haberler|related (?:articles|posts)"
    r"|read more|tüm hakları saklıdır|all rights reserved|©)", re.I)
WS = re.compile(r"\s+")
# "Home / Events / Baslik" bicimindeki gezinti izleri
BREADCRUMB = re.compile(r"^[^/]{1,40}(?:\s*/\s*[^/]{1,60}){1,5}$")


class Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.main = 0
        self.tag: str | None = None
        self.buf: list[str] = []
        self.blocks: list[tuple[str, str, bool]] = []   # (tag, metin, main_icinde)

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if tag in MAIN_TAGS:
            self.main += 1
        if tag in BLOCK_TAGS and not self.skip:
            self.flush()
            self.tag = tag
        elif tag == "br" and self.tag:
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag in MAIN_TAGS:
            self.main = max(0, self.main - 1)
        if tag in BLOCK_TAGS and tag == self.tag:
            self.flush()

    def handle_data(self, data):
        if not self.skip and self.tag:
            self.buf.append(data)

    def flush(self) -> None:
        if self.tag and self.buf:
            text = WS.sub(" ", "".join(self.buf)).strip()
            if text:
                self.blocks.append((self.tag, text, self.main > 0))
        self.tag, self.buf = None, []


def decode(body: bytes, content_type: str = "") -> str:
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    if not m:
        m = re.search(rb"charset=[\"']?([\w-]+)", body[:4000], re.I)
        enc = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    else:
        enc = m.group(1)
    try:
        return body.decode(enc, "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def extract(body: bytes, content_type: str = "", min_chars: int = 400) -> list[str]:
    """Sayfadan paragraf listesi dondurur; guvenilir metin bulunamazsa bos liste."""
    reader = Reader()
    try:
        reader.feed(decode(body, content_type))
        reader.flush()
    except Exception:
        return []

    blocks = reader.blocks
    if any(b[2] for b in blocks):          # article/main varsa yalnizca onu kullan
        blocks = [b for b in blocks if b[2]]

    out: list[str] = []
    seen: set[str] = set()
    for tag, text, _ in blocks:
        if STOP_MARKERS.search(text) and len(text) < 220:
            continue
        if tag == "p" and len(text) < 30:
            continue
        if len(text) < 200 and BREADCRUMB.match(text):
            continue
        key = text[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f"## {text}" if tag in ("h2", "h3", "h4") else text)
        if len(out) >= 140:
            break

    body_chars = sum(len(p) for p in out if not p.startswith("## "))
    return out if body_chars >= min_chars else []
