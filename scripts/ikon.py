#!/usr/bin/env python3
"""Uygulama ikonlarini uretir (PNG yazici: yalnizca zlib + struct).

Motif: koyu petrol zeminde, bolge renklerinde bes haber satiri.
Cikti: icon-512.png, icon-180.png (apple-touch-icon), icon.svg
"""
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUND = (0x13, 0x4A, 0x57)
BARS = [((0xC8, 0x40, 0x2C), 0.78), ((0x3D, 0x8B, 0x4F), 0.58),
        ((0x3F, 0xA8, 0xC6), 0.86), ((0x6D, 0x4B, 0xB0), 0.50),
        ((0xC0, 0x8A, 0x1E), 0.70)]


def draw(size: int) -> bytes:
    pad = round(size * 0.17)
    gap = round(size * 0.055)
    height = round(size * 0.085)
    rows = [[GROUND] * size for _ in range(size)]
    top = pad
    for color, width in BARS:
        span = round((size - 2 * pad) * width)
        for y in range(top, min(top + height, size)):
            row = rows[y]
            for x in range(pad, min(pad + span, size)):
                row[x] = color
        top += height + gap
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)
    return raw


def png(size: int, path: Path) -> None:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    data = zlib.compress(draw(size), 9)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", data) + chunk(b"IEND", b""))
    print(f"{path.name}  {path.stat().st_size / 1024:.1f} KB")


def svg(path: Path) -> None:
    size, pad, gap, height = 512, 87, 28, 44
    parts, top = [], pad
    for (r, g, b), width in BARS:
        span = round((size - 2 * pad) * width)
        parts.append(f'<rect x="{pad}" y="{top}" width="{span}" height="{height}" '
                     f'fill="#{r:02X}{g:02X}{b:02X}"/>')
        top += height + gap
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">'
        f'<rect width="{size}" height="{size}" fill="#134A57"/>'
        + "".join(parts) + "</svg>\n", encoding="utf-8")
    print(f"{path.name}")


if __name__ == "__main__":
    png(512, ROOT / "icon-512.png")
    png(180, ROOT / "icon-180.png")
    svg(ROOT / "icon.svg")
