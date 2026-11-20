"""Erzeugt spielzeit/web/icon.ico ohne Zusatzpakete (nur Standardbibliothek).

Gleiches Motiv wie das Tray-Symbol: abgerundetes Quadrat (Blau→Violett), weißer Ring, Play-Dreieck.
Aufruf:  python tools/make_icon.py
"""

import math
import struct
import zlib
from pathlib import Path

TOP = (57, 135, 229)
BOTTOM = (98, 80, 214)
SIZES = (16, 24, 32, 48, 64, 128, 256)
SS = 4  # Überabtastung je Achse


def inside_rounded(x, y, s):
    m, r = s * 0.04, s * 0.22
    x0, y0, x1, y1 = m, m, s - m, s - m
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def inside_ring(x, y, s):
    c = s / 2
    d = math.hypot(x - c, y - c)
    outer = s * 0.30
    return outer - s * 0.07 <= d <= outer


def inside_triangle(x, y, s):
    ax, ay, bx, by, cx, cy = s * 0.43, s * 0.36, s * 0.43, s * 0.64, s * 0.65, s * 0.50

    def sign(px, py, qx, qy, rx, ry):
        return (px - rx) * (qy - ry) - (qx - rx) * (py - ry)

    d1, d2, d3 = sign(x, y, ax, ay, bx, by), sign(x, y, bx, by, cx, cy), sign(x, y, cx, cy, ax, ay)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def render(size):
    rows = []
    for py in range(size):
        row = bytearray([0])  # PNG-Filter "None"
        t = py / max(1, size - 1)
        base = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        for px in range(size):
            bg = white = 0
            for sy in range(SS):
                for sx in range(SS):
                    x, y = px + (sx + 0.5) / SS, py + (sy + 0.5) / SS
                    if inside_rounded(x, y, size):
                        bg += 1
                        if inside_ring(x, y, size) or inside_triangle(x, y, size):
                            white += 1
            n = SS * SS
            if bg == 0:
                row += bytes(4)
                continue
            w = white / bg
            rgb = [round(base[i] * (1 - w) + 255 * w) for i in range(3)]
            row += bytes(rgb + [round(255 * bg / n)])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def make_ico(path):
    pngs = [render(s) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, data = b"", b""
    for s, png in zip(SIZES, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    Path(path).write_bytes(header + entries + data)
    return pngs[-1]


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    out = root / "spielzeit" / "web" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)
    big = make_ico(out)
    print("geschrieben:", out, out.stat().st_size, "Bytes")
