#!/usr/bin/env python3
"""Animated ASCII black hole for the Project Inertia README (v3).

Mixes: a tilted, turbulent accretion disk · lensed far side of the disk over the
shadow · pulsing jets · orbit trails · ejected particle streaks · nebula dust ·
twinkling cross stars · the Inertia rocket escaping on a looping trail.

Usage:
  python3 make_blackhole.py                 # writes blackhole.gif
  python3 make_blackhole.py --out Images    # writes into Images/
  python3 make_blackhole.py --frame 10      # writes preview.png of one frame
  python3 make_blackhole.py --svg           # also write a (large) animated SVG

Requires Pillow (pip install pillow). Tweak the settings block to change the look.
"""
import argparse
import math
import os
import random
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

# ============================ settings ======================================
W, H = 104, 44            # grid size in characters
FRAMES = 60               # frames per loop
FRAME_MS = 70             # ms per frame (60 × 70 ms ≈ 4.2 s loop)
SEED = 42                 # change for a different random layout

FONT_SIZE = 12
TITLE = "PROJECT INERTIA"  # "" hides the title
PAD = 22
TITLE_H = 58

DISK_ROT = -24            # tilt of the disk on screen (degrees, negative = rising to the right)
DISK_Q = 0.33             # disk thickness on screen (1 = face-on, small = edge-on)
SHADOW = 7.5              # radius of the black shadow
R_IN, R_OUT = 11.0, 54.0   # inner / outer edge of the disk
JETS = True
ORBITS = 9               # orbit trails
EJECTA = 10               # particles flung outwards
SPARKS = 22               # particles falling in
STARS = 75
BIG_STARS = 5
ROCKET = True

# runtime knobs (used by make_blackhole_story.py; leave as is for the normal loop)
WARP = 0.25               # how much turbulence bends the gas
CHAOS = 0.0               # 0 = calm, 1 = unstable (flicker, dropouts, corrupted glyphs)
JET_GAIN = 1.0
ZOOM = 1.0                # >1 pulls the whole structure inwards

BG = (9, 6, 36)
BORDER = (94, 40, 214)
TITLE_COL = (255, 255, 255)
PALETTE = [  # faint → bright (logo colours)
    (34, 28, 120), (48, 44, 170), (62, 62, 220), (92, 96, 245),
    (130, 136, 255), (176, 178, 255), (214, 214, 255), (255, 255, 255),
]
NEBULA = [(36, 18, 88), (56, 26, 128), (82, 36, 178)]   # purple from the logo border
FLAME_COLS = [(255, 214, 140), (255, 160, 90), (240, 110, 80)]
# ===========================================================================

rng = random.Random(SEED)
cx, cy = (W - 1) / 2, (H - 1) / 2
COSR, SINR = math.cos(math.radians(DISK_ROT)), math.sin(math.radians(DISK_ROT))


def load_font(names, size, fallback):
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.truetype(fallback, size)


FONT = load_font(("DejaVuSansMono.ttf", "Menlo.ttc", "consola.ttf"), FONT_SIZE,
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
CW = FONT.getlength("M")
CH = round(FONT_SIZE * 1.18)
ASPECT = CH / CW          # one row is this many columns tall


def hash01(*v):
    h = hash(v) & 0xFFFFFFFF
    return ((h * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF


# ---- periodic turbulence (integer time frequencies → seamless loop) ---------
def make_turb(n, kth, kr, m):
    comps = [(rng.uniform(0.4, 1.0), rng.randint(1, kth), rng.uniform(-kr, kr),
              rng.choice([-1, 1]) * rng.randint(1, m), rng.uniform(0, 2 * math.pi)) for _ in range(n)]
    return comps, sum(c[0] for c in comps)


T_A, T_B, T_C = make_turb(7, 5, 5, 2), make_turb(7, 12, 10, 3), make_turb(5, 20, 16, 4)


def turb(spec, th, lr, t):
    comps, norm = spec
    return sum(a * math.sin(k * th + kr * lr + 2 * math.pi * m * t + p) for a, k, kr, m, p in comps) / norm


# ---- character choice --------------------------------------------------------
def flow_char(angle, v, salt):
    """Character following a streak direction (screen angle, y down); denser when bright."""
    a = (math.degrees(angle) + 180) % 180
    if a < 22.5 or a >= 157.5:
        sets = ("-~", "=~-", "=#")
    elif a < 67.5:
        sets = ("\\`", "\\\\)", "\\N")
    elif a < 112.5:
        sets = ("|!:", "|I!", "|H")
    else:
        sets = ("/,", "/(/", "/Z")
    if v < 0.08:
        pool = ".,'`:"
    elif v < 0.24:
        pool = sets[0]
    elif v < 0.48:
        pool = sets[1]
    elif v < 0.74:
        pool = sets[2] + "*o%"
    else:
        pool = "@#%$&8B"
    return pool[int(salt * len(pool)) % len(pool)]


def colour(v, lo=0):
    return PALETTE[max(lo, min(len(PALETTE) - 1, int(v ** 0.5 * len(PALETTE))))]


def to_disk(x, y):
    """Screen cell → rotated screen frame (u along disk, v across) in column units."""
    px, py = x - cx, (y - cy) * ASPECT
    return px * COSR + py * SINR, -px * SINR + py * COSR


def from_disk(u, v):
    px, py = u * COSR - v * SINR, u * SINR + v * COSR
    return cx + px, cy + py / ASPECT


def screen_angle(du, dv):
    return math.atan2(du * SINR + dv * COSR, du * COSR - dv * SINR)


# ---- the black hole field ----------------------------------------------------
LAYERS = [(3, 0.9, 10.0, 6.0), (2, 0.7, 20.0, 9.0), (1, 0.5, 36.0, 16.0)]


def disk_value(r, ph, t):
    if r < R_IN * 0.85 or r > R_OUT:
        return 0.0
    lr = math.log(r)
    ta, tb, tc = turb(T_A, ph, lr, t), turb(T_B, ph, lr, t), turb(T_C, ph, lr, t)
    phw = ph + WARP * ta
    val, ws = 0.0, 0.0
    for m, twist, rc, wd in LAYERS:
        w = math.exp(-((r - rc) / wd) ** 2)
        s = phw + twist * lr
        arm = (0.5 + 0.5 * math.cos(2 * s - 2 * math.pi * m * t)) ** 1.4
        val += w * arm
        ws += w
    val /= ws + 1e-9
    clumps = 0.55 + 0.45 * (0.6 * tb + 0.4 * tc)                       # lumpy gas
    bands = 0.75 + 0.25 * math.cos(1.6 * r + 2.5 * ta - 2 * math.pi * 2 * t)
    prof = math.exp(-(r - R_IN) / 22.0) * min(1.0, (r - R_IN * 0.85) / 1.5)
    edge = max(0.0, 1 - (r / R_OUT) ** 3)
    doppler = 1 + 0.45 * -math.cos(ph)                                  # approaching side brighter
    flick = 1 + CHAOS * 0.7 * tc
    return max(0.0, min(1.0, (0.35 + 0.9 * val) * clumps * bands * prof * edge * doppler * 2.2 * flick))


def field(x, y, t):
    """Return (value, screen angle, kind) for one cell; kind in {'shadow','disk','lens','jet',None}."""
    u, v = to_disk(x, y)
    u, v = u * ZOOM, v * ZOOM
    rho = math.hypot(u, v)
    rd = math.hypot(u, v / DISK_Q)
    ph = math.atan2(v / DISK_Q, u)
    best = (0.0, 0.0, None)

    # disk (front half may cover the shadow)
    dv = disk_value(rd, ph, t)
    if dv > 0.04:
        ang = screen_angle(-math.sin(ph), DISK_Q * math.cos(ph))
        best = (dv, ang, "disk")

    if rho < SHADOW:
        if best[2] == "disk" and v > 0:                                # front of disk passes in front
            return best
        return (0.0, 0.0, "shadow")

    # lensed far side of the disk arching over (and faintly under) the shadow
    ring_ang = math.atan2(v, u)
    top = -math.sin(ring_ang)                                           # 1 at the top
    lens_r = SHADOW * (1.55 + 0.25 * max(0, top))
    lens = math.exp(-((rho - lens_r) / (1.1 + 1.2 * max(0, top))) ** 2) * (0.25 + 0.75 * max(0, top) ** 0.7)
    lens *= 0.75 + 0.25 * turb(T_B, ring_ang * 2, math.log(rho), t)
    photon = math.exp(-((rho - SHADOW * 1.08) / 0.45) ** 2)
    lv = min(1.0, lens * 1.25 + photon * 1.1)
    if lv > best[0]:
        best = (lv, screen_angle(-math.sin(ring_ang), math.cos(ring_ang)), "lens")

    # jets along the disk axis, with knots moving outwards
    if JETS and abs(v) > SHADOW:
        width = 0.9 + 0.06 * abs(v)
        knots = 0.55 + 0.45 * math.cos(0.45 * abs(v) - 2 * math.pi * 3 * t)
        flick = 0.8 + 0.2 * math.sin(2 * math.pi * 2 * t + (0 if v > 0 else 1.7))
        jv = math.exp(-(u / width) ** 2) * knots * flick * math.exp(-(abs(v) - SHADOW) / 45) * 1.25 * JET_GAIN
        if jv > best[0]:
            best = (jv, screen_angle(0, 1), "jet")
    return best


# ---- moving things -------------------------------------------------------------
orbits = [dict(a=rng.uniform(R_IN + 3, R_OUT * 0.95), q=rng.uniform(0.12, 0.55),
               rot=rng.uniform(-0.5, 0.5), n=rng.choice([1, 1, 2]), off=rng.random(),
               arc=rng.uniform(0.6, 1.6)) for _ in range(ORBITS)]
for o in orbits:
    o["n"] = 2 if o["a"] < 20 else o["n"]                                # inner orbits faster
ejecta = [dict(dir=rng.uniform(0, 2 * math.pi), k=rng.choice([1, 2]), off=rng.random(),
               spin=rng.uniform(-0.5, 0.5)) for _ in range(EJECTA)]
sparks = [dict(k=rng.choice([1, 1, 2]), off=rng.random(), th0=rng.uniform(0, 2 * math.pi),
               rout=rng.uniform(18, R_OUT)) for _ in range(SPARKS)]
stars = [(rng.randrange(W), rng.randrange(H), rng.random(), rng.choice([1, 2, 3])) for _ in range(STARS)]
big_stars = [(rng.randrange(5, W - 5), rng.randrange(3, H - 3), rng.random()) for _ in range(BIG_STARS)]
neb_spec = [(rng.uniform(0.05, 0.16), rng.uniform(0.08, 0.3), rng.uniform(0, 6.3), rng.choice([-1, 1]))
            for _ in range(6)]


def nebula(x, y, t):
    s = sum(math.sin(fx * x + fy * y * ASPECT + p + 2 * math.pi * m * t * 0.0 + 0.6 * math.sin(2 * math.pi * t + p))
            for fx, fy, p, m in neb_spec) / len(neb_spec)
    return max(0.0, s - 0.25) * 2.2


def put(grid, x, y, ch, col, z):
    xi, yi = int(round(x)), int(round(y))
    if 0 <= xi < W and 0 <= yi < H and z >= grid[yi][xi][2]:
        grid[yi][xi] = (ch, col, z)


def in_shadow(x, y):
    u, v = to_disk(x, y)
    return math.hypot(u, v) < SHADOW


ROCKET_END = 0.7


def rocket_xy(s):
    r = SHADOW * 0.7 + 46 * s ** 1.8
    th = 0.45 * math.pi + 1.25 * math.pi * s ** 0.85
    return cx + r * math.cos(th), cy + r * math.sin(th) * 0.82 / ASPECT, r


def frame(i, t=None):
    t = i / FRAMES if t is None else t
    grid = [[(" ", None, 0)] * W for _ in range(H)]

    # nebula dust + stars
    for y in range(H):
        for x in range(W):
            n = nebula(x, y, t)
            if n > 0.05 and hash01(x, y, 11) < n * 1.3:
                ch = ".:'`,"[int(hash01(x, y, i // 8) * 5)]
                put(grid, x, y, ch, NEBULA[min(2, int(n * 3))], 0)
    for sx, sy, ph, k in stars:
        b = 0.5 + 0.5 * math.sin(2 * math.pi * (k * t + ph))
        ch = "+" if b > 0.9 else "*" if b > 0.7 else "." if b > 0.3 else "`" if b > 0.15 else ""
        if ch:
            put(grid, sx, sy, ch, PALETTE[6 if b > 0.7 else 3], 1)
    for sx, sy, ph in big_stars:
        b = 0.5 + 0.5 * math.sin(2 * math.pi * (t + ph))
        if b > 0.3:
            put(grid, sx, sy, "#" if b > 0.8 else "*", PALETTE[7] if b > 0.7 else PALETTE[5], 2)
            arm = 1 + int(b * 3.2)
            for k in range(1, arm + 1):
                c = PALETTE[max(1, 6 - 2 * k)]
                put(grid, sx - 2 * k, sy, "-", c, 2)
                put(grid, sx + 2 * k, sy, "-", c, 2)
                if k <= max(1, arm - 1):
                    put(grid, sx, sy - k, "|", c, 2)
                    put(grid, sx, sy + k, "|", c, 2)
            if b > 0.85:
                for dx, dy, c in ((-1, -1, "\\"), (1, 1, "\\"), (1, -1, "/"), (-1, 1, "/")):
                    put(grid, sx + dx, sy + dy, c, PALETTE[3], 2)

    # black hole field
    for y in range(H):
        for x in range(W):
            v, ang, kind = field(x, y, t)
            if kind == "shadow":
                put(grid, x, y, " ", None, 9)          # nothing behind the shadow shows through
                continue
            if v < 0.05:
                continue
            if CHAOS and hash01(x, y, i, 21) < CHAOS * 0.16:
                continue                                   # gas tearing apart
            vv = max(0.0, min(0.999, v + (hash01(x, y, i) - 0.5) * (0.14 + 0.4 * CHAOS)))
            ch = flow_char(ang, vv, hash01(x, y, i, 3))
            if CHAOS and hash01(x, y, i, 22) < CHAOS * 0.12:
                ch = "@#%&$?!*><{}[]"[int(hash01(x, y, i, 23) * 14)]   # corrupted glyphs
            put(grid, x, y, ch, colour(vv, 2 if kind == "jet" else 0), 4 if kind == "disk" else 3)

    # orbit trails (tilted ellipses in different planes)
    for o in orbits:
        head = 2 * math.pi * (o["n"] * t + o["off"])
        steps = 26
        for j in range(steps):
            a = head - j * o["arc"] / steps
            eu, ev = o["a"] * math.cos(a), o["a"] * o["q"] * math.sin(a)
            ru = eu * math.cos(o["rot"]) - ev * math.sin(o["rot"])
            rv = eu * math.sin(o["rot"]) + ev * math.cos(o["rot"])
            x, y = from_disk(ru, rv)
            if in_shadow(x, y) and rv < 0:
                continue
            s = 1 - j / steps
            da_u = -o["a"] * math.sin(a)
            da_v = o["a"] * o["q"] * math.cos(a)
            tu = da_u * math.cos(o["rot"]) - da_v * math.sin(o["rot"])
            tv = da_u * math.sin(o["rot"]) + da_v * math.cos(o["rot"])
            ch = "*" if j == 0 else flow_char(screen_angle(tu, tv), 0.15 + 0.5 * s, hash01(j, i))
            put(grid, x, y, ch, PALETTE[min(5, 1 + int(4 * s))], 3)

    # ejected particles: straight streaks flying outward
    for e in ejecta:
        f = (e["k"] * t + e["off"]) % 1.0
        for j, (ch_v, c) in enumerate(((1.0, 7), (0.7, 6), (0.5, 4), (0.3, 3), (0.2, 2), (0.1, 1))):
            ff = f - j * 0.015
            if ff < 0:
                break
            r = SHADOW * 1.6 + ff * 60
            d = e["dir"] + e["spin"] * ff
            x, y = cx + r * math.cos(d), cy + r * math.sin(d) / ASPECT
            ch = "o" if j == 0 else flow_char(d, ch_v * 0.6, hash01(j, i, 5))
            put(grid, x, y, ch, PALETTE[c], 5)

    # sparks spiralling in
    for s in sparks:
        f = (s["k"] * t + s["off"]) % 1.0
        for j, (ch, c) in enumerate((("*", 7), ("o", 6), (":", 4), (".", 2))):
            ff = f - j * 0.012
            if ff < 0:
                break
            r = R_IN + (s["rout"] - R_IN) * (1 - ff) ** 1.3
            ph = s["th0"] + 2 * math.pi * 2 * ff
            x, y = from_disk(r * math.cos(ph), r * DISK_Q * math.sin(ph))
            if not (in_shadow(x, y) and math.sin(ph) < 0):
                put(grid, x, y, ch, PALETTE[c], 5)

    # rocket + looping trail
    if ROCKET and t < ROCKET_END + 0.25:
        head = min(t / ROCKET_END, 1.0)
        fade = 1.0 if t < ROCKET_END else 1 - (t - ROCKET_END) / 0.25
        steps = 90
        for j in range(steps):
            s = head - j * 0.011
            if s < 0:
                break
            x, y, r = rocket_xy(s)
            if r < SHADOW + 0.5:
                continue
            strength = (1 - j / steps) * fade
            xp, yp, _ = rocket_xy(max(0, s - 0.01))
            tang = math.atan2((y - yp) * ASPECT, x - xp)
            nx, ny = -math.sin(tang), math.cos(tang) / ASPECT
            for w in (-1.5, -0.7, 0, 0.7, 1.5):
                ew = abs(w) / 1.5
                if hash01(j, int(w * 10), i) > strength * (1.15 - 0.6 * ew):
                    continue
                vv = max(0.0, min(0.999, strength * (1 - 0.45 * ew) + (hash01(j, int(w * 10), i, 7) - 0.5) * 0.2))
                put(grid, x + nx * w * ASPECT * 0.5, y + ny * w * ASPECT * 0.5,
                    flow_char(tang, 0.45 + vv * 0.55, hash01(j, int(w * 10), i, 9)),
                    PALETTE[min(7, int(5 + vv * 3))], 6)
        if t < ROCKET_END:
            x, y, r = rocket_xy(head)
            x2, y2, _ = rocket_xy(max(0, head - 0.01))
            ang = math.atan2((y - y2) * ASPECT, x - x2)
            ux, uy = math.cos(ang), math.sin(ang) / ASPECT
            octant = int(round(ang / (math.pi / 4))) % 8
            if r > SHADOW + 0.5:
                put(grid, x, y, [">", "\\", "v", "/", "<", "\\", "^", "/"][octant], PALETTE[7], 8)
                put(grid, x - ux, y - uy, "A" if octant in (5, 6, 7) else "H", PALETTE[7], 8)
                put(grid, x - 2 * ux, y - 2 * uy, "#", PALETTE[7], 8)
                put(grid, x - 2 * ux - uy * ASPECT * 0.9, y - 2 * uy + ux / ASPECT * 0.9, "/", PALETTE[6], 8)
                put(grid, x - 2 * ux + uy * ASPECT * 0.9, y - 2 * uy - ux / ASPECT * 0.9, "\\", PALETTE[6], 8)
                for k, fc in enumerate(FLAME_COLS):
                    put(grid, x - (3 + k) * ux, y - (3 + k) * uy, "*" if hash01(i, k) > 0.5 else "~", fc, 7)
    return grid


# ---- writers -----------------------------------------------------------------
def canvas_size():
    return int(W * CW + 2 * PAD), int(H * CH + PAD + (TITLE_H if TITLE else PAD))


def render_png(grid):
    w, h = canvas_size()
    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, w - 3, h - 3], radius=22, fill=BG, outline=BORDER, width=5)
    for y, row in enumerate(grid):
        for x, (ch, col, _) in enumerate(row):
            if ch != " " and col:
                d.text((PAD + x * CW, PAD + y * CH), ch, font=FONT, fill=col)
    if TITLE:
        tf = load_font(("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"), int(TITLE_H * 0.52),
                       "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        sp = 6
        tw = sum(d.textlength(c, font=tf) for c in TITLE) + sp * (len(TITLE) - 1)
        xx = (w - tw) / 2
        for c in TITLE:
            d.text((xx, h - TITLE_H + 6), c, font=tf, fill=TITLE_COL)
            xx += d.textlength(c, font=tf) + sp
    return img


def write_gif(path, frames):
    imgs = [render_png(g) for g in frames]
    pal = imgs[len(imgs) // 2].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in imgs]
    q[0].save(path, save_all=True, append_images=q[1:], duration=FRAME_MS, loop=0, optimize=True, disposal=1)


def write_svg(path, frames):
    w, h = canvas_size()
    period = FRAMES * FRAME_MS / 1000
    hexc = lambda c: "#%02x%02x%02x" % c
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
           f'role="img" aria-label="Animated ASCII black hole">', "<style>",
           f"text{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace;"
           f"font-size:{FONT_SIZE}px;white-space:pre}}",
           f".f{{visibility:hidden;animation:s {period:.2f}s steps(1,end) infinite}}",
           f"@keyframes s{{0%{{visibility:visible}}{100 / FRAMES:.4f}%,100%{{visibility:hidden}}}}",
           ".t{font-family:'Segoe UI',Helvetica,Arial,sans-serif;font-weight:800;font-size:30px;"
           "letter-spacing:6px;fill:#fff}", "</style>",
           f'<rect x="3" y="3" width="{w-6}" height="{h-6}" rx="22" fill="{hexc(BG)}" '
           f'stroke="{hexc(BORDER)}" stroke-width="5"/>']
    for i, grid in enumerate(frames):
        out.append(f'<g class="f" style="animation-delay:{i * FRAME_MS / 1000 - period:.3f}s">')
        by_col = {}
        for y, row in enumerate(grid):
            x = 0
            while x < W:
                ch, col, _ = row[x]
                if ch == " " or not col:
                    x += 1
                    continue
                start, run = x, []
                while x < W and row[x][1] == col and row[x][0] != " ":
                    run.append(row[x][0])
                    x += 1
                by_col.setdefault(col, []).append(
                    f'<tspan x="{PAD + start * CW:.1f}" y="{PAD + (y + 1) * CH - 3}" '
                    f'textLength="{len(run) * CW:.1f}">{escape("".join(run))}</tspan>')
        for col, spans in by_col.items():
            out.append(f'<text fill="{hexc(col)}" xml:space="preserve">{"".join(spans)}</text>')
        out.append("</g>")
    if TITLE:
        out.append(f'<text class="t" x="{w/2:.0f}" y="{h - 20}" text-anchor="middle">{escape(TITLE)}</text>')
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    ap.add_argument("--frame", type=int, help="only render this frame to preview.png")
    ap.add_argument("--svg", action="store_true", help="also write a CSS-animated SVG (large)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.frame is not None:
        render_png(frame(a.frame)).save(os.path.join(a.out, "preview.png"))
    else:
        frames = [frame(i) for i in range(FRAMES)]
        write_gif(os.path.join(a.out, "blackhole.gif"), frames)
        if a.svg:
            write_svg(os.path.join(a.out, "blackhole.svg"), frames)
        print("done")
