"""Regenerate the app icons.

A PWA needs raster icons: Android wants a 192 and a 512, a maskable variant it
can crop to whatever shape the launcher uses, and iOS wants an apple-touch-icon
because it ignores the manifest entirely. PNGs are binary, so once committed
nobody can see what changed or nudge a colour. Rather than four opaque blobs,
the icon lives here as geometry and is rasterised on demand.

No Pillow, and no build step - the shapes are a circle, a pentagon and five
lines, which is little enough to sample directly. The SVG is written from the
same numbers so the two can never drift apart.

    uv run manage.py make_icons
"""

import math
import struct
import zlib
from pathlib import Path

from django.core.management.base import BaseCommand

# Everything is described in a 192-unit square and scaled on the way out.
UNIT = 192.0
CORNER = 42.0

WHITE = (255, 255, 255)
BLUE = (0x16, 0x67, 0xC9)  # --accent, the app's only accent colour

BALL = (96.0, 96.0, 54.0)  # centre x, centre y, radius
PENTAGON = [(96, 62), (110, 72), (105, 89), (87, 89), (82, 72)]
SPOKES = [
    ((96, 62), (96, 44)),
    ((110, 72), (126, 61)),
    ((105, 89), (122, 95)),
    ((87, 89), (70, 95)),
    ((82, 72), (66, 61)),
]
STROKE = 7.0

# Anything the logo touches, with room for the stroke's round caps.
LOGO_BOX = (
    BALL[0] - BALL[2] - STROKE,
    BALL[1] - BALL[2] - STROKE,
    BALL[0] + BALL[2] + STROKE,
    BALL[1] + BALL[2] + STROKE,
)

SAMPLES = 3  # 3x3 supersampling; the edges are curves, not text


def in_circle(x, y):
    cx, cy, r = BALL
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_pentagon(x, y):
    # Ray casting. The shape is convex, but this is short and obviously right.
    inside = False
    n = len(PENTAGON)
    for i in range(n):
        ax, ay = PENTAGON[i]
        bx, by = PENTAGON[(i + 1) % n]
        if (ay > y) != (by > y):
            cross = ax + (y - ay) / (by - ay) * (bx - ax)
            if x < cross:
                inside = not inside
    return inside


def on_spoke(x, y):
    half = STROKE / 2.0
    for (ax, ay), (bx, by) in SPOKES:
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        t = ((x - ax) * dx + (y - ay) * dy) / length
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)  # round caps
        px, py = ax + t * dx - x, ay + t * dy - y
        if px * px + py * py <= half * half:
            return True
    return False


def in_tile(x, y, corner):
    """Inside the rounded square that forms the icon's background."""
    if x < 0 or y < 0 or x > UNIT or y > UNIT:
        return False
    if corner <= 0:
        return True
    cx = corner if x < corner else (UNIT - corner if x > UNIT - corner else x)
    cy = corner if y < corner else (UNIT - corner if y > UNIT - corner else y)
    if cx == x and cy == y:
        return True
    return (x - cx) ** 2 + (y - cy) ** 2 <= corner * corner


def sample(x, y, corner, scale):
    """Colour of one point, in painting order. None means transparent."""
    if not in_tile(x, y, corner):
        return None
    # The maskable icon shrinks the logo instead of the canvas, so scaling
    # happens by looking the sample up in unscaled logo space.
    lx = (x - UNIT / 2) / scale + UNIT / 2
    ly = (y - UNIT / 2) / scale + UNIT / 2
    colour = WHITE
    if in_circle(lx, ly):
        colour = BLUE
        if in_pentagon(lx, ly) or on_spoke(lx, ly):
            colour = WHITE
    return colour


def render(size, corner=CORNER, scale=1.0, opaque=False):
    """Rasterise to rows of RGBA bytes."""
    step = UNIT / size
    sub = step / SAMPLES
    offsets = [(i + 0.5) * sub for i in range(SAMPLES)]
    total = SAMPLES * SAMPLES
    corner_u = corner
    x0, y0, x1, y1 = LOGO_BOX
    x0, y0 = (x0 - UNIT / 2) * scale + UNIT / 2, (y0 - UNIT / 2) * scale + UNIT / 2
    x1, y1 = (x1 - UNIT / 2) * scale + UNIT / 2, (y1 - UNIT / 2) * scale + UNIT / 2

    rows = []
    for py in range(size):
        top = py * step
        row = bytearray()
        plain_row = top > corner_u and top + step < UNIT - corner_u
        for px in range(size):
            left = px * step
            # Most of the tile is flat white. Only supersample where something
            # actually happens: near the logo, or near a rounded corner.
            if (
                plain_row
                and (left + step < x0 or left > x1 or top + step < y0 or top > y1)
            ):
                row += bytes(WHITE) + b"\xff"
                continue
            r = g = b = a = 0
            for oy in offsets:
                for ox in offsets:
                    hit = sample(left + ox, top + oy, corner_u, scale)
                    if hit is None:
                        continue
                    r += hit[0]
                    g += hit[1]
                    b += hit[2]
                    a += 255
            if a == 0:
                row += b"\xff\xff\xff\x00" if not opaque else b"\xff\xff\xff\xff"
                continue
            covered = a // 255
            row += bytes(
                (r // covered, g // covered, b // covered, a // total)
            )
        rows.append(bytes(row))
    return rows


def write_png(path, rows):
    size = len(rows)

    def chunk(kind, payload):
        head = struct.pack(">I", len(payload)) + kind
        return head + payload + struct.pack(">I", zlib.crc32(kind + payload))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    body = zlib.compress(b"".join(b"\x00" + row for row in rows), 9)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", body)
        + chunk(b"IEND", b"")
    )


def svg_source():
    points = " ".join(f"{x},{y}" for x, y in PENTAGON)
    lines = " ".join(f"M{ax} {ay}L{bx} {by}" for (ax, ay), (bx, by) in SPOKES)
    cx, cy, r = BALL
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192" '
        f'width="192" height="192">\n'
        f'  <rect width="192" height="192" rx="{CORNER:g}" fill="#ffffff"/>\n'
        f'  <circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="#1667c9"/>\n'
        f'  <polygon points="{points}" fill="#ffffff"/>\n'
        f'  <path d="{lines}" stroke="#ffffff" stroke-width="{STROKE:g}"\n'
        f'        stroke-linecap="round" fill="none"/>\n'
        f"</svg>\n"
    )


class Command(BaseCommand):
    help = "Rasterise the PWA icons into training/static/training/img/."

    def handle(self, *args, **options):
        out = Path(__file__).resolve().parents[2] / "static" / "training" / "img"
        out.mkdir(parents=True, exist_ok=True)

        (out / "icon.svg").write_text(svg_source(), encoding="utf-8")
        self.stdout.write("icon.svg")

        # name, size, corner radius, logo scale, opaque background
        wanted = [
            ("icon-192.png", 192, CORNER, 1.0, False),
            ("icon-512.png", 512, CORNER, 1.0, False),
            # Maskable: the launcher may crop this to a circle, so the tile is
            # full-bleed and the logo is pulled inside the 80% safe zone.
            ("icon-maskable-512.png", 512, 0.0, 0.72, True),
            # iOS applies its own rounding and hates transparency.
            ("apple-touch-icon.png", 180, 0.0, 0.86, True),
        ]
        for name, size, corner, scale, opaque in wanted:
            write_png(out / name, render(size, corner, scale, opaque))
            self.stdout.write(f"{name} ({size}px)")

        self.stdout.write(self.style.SUCCESS("Icons written to %s" % out))
