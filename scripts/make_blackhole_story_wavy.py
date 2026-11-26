#!/usr/bin/env python3
"""Wavy story version of the Inertia black hole (needs make_blackhole.py in the same folder).

Same comet story, but the instability is not a regular wobble: waves with unrelated
speeds warp space, regions of the disk run out of sync, and a ghost copy of the disk
splits off and braids through the original.

Timeline (default ≈ 11 s, loops seamlessly):
  calm   – the black hole spins calmly
  comet  – a comet streaks in and hits the core → flash + shockwave
  chaos  – space warps in tangled waves, the disk splits into two braided strands,
           regions drift out of sync, and everything spins faster and faster
  burst  – the disk is sucked in, white flash, and it calmly reforms (loop)

Usage:
  python3 make_blackhole_story.py                  # writes blackhole_story_wavy.gif
  python3 make_blackhole_story.py --out Images
  python3 make_blackhole_story.py --preview 4.5    # still preview at 4.5 s
"""
import argparse
import math
import os

from PIL import Image

import make_blackhole as bh

def _set_font(size):
    bh.FONT_SIZE = size
    bh.FONT = bh.load_font(("DejaVuSansMono.ttf", "Menlo.ttc", "consola.ttf"), size,
                           "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    bh.CW = bh.FONT.getlength("M")
    bh.CH = round(size * 1.18)
    bh.ASPECT = bh.CH / bh.CW

# ============================ timeline (seconds) =============================
FRAME_MS = 90
CALM_END = 3.2            # comet hits at this moment
COMET_TIME = 1.1          # how long the comet is visible before impact
CHAOS_END = 10.2          # instability peaks here
COLLAPSE = 0.6            # disk gets sucked in
FLASH_HOLD = 0.15
REFORM = 0.9              # fade back from the flash to the calm state
BASE_LOOP = 4.2           # seconds per "spin" when calm
MAX_SPEED = 6.0           # spin speed multiplier at peak chaos
COMET_FROM = (-0.55, -1.0)  # where the comet comes from (fraction of half-width/height)
GIF_COLOURS = 48
SCALE = 1.0
FONT_SIZE = 10            # smaller text = smaller file (normal loop uses 12)
# ===========================================================================

_set_font(FONT_SIZE)
bh.PAD, bh.TITLE_H = 18, 48
DURATION = CHAOS_END + COLLAPSE + FLASH_HOLD + REFORM
FLASH_T = CHAOS_END + COLLAPSE
BASE = dict(cx=bh.cx, cy=bh.cy, rot=bh.DISK_ROT, q=bh.DISK_Q, shadow=bh.SHADOW, warp=bh.WARP)


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def chaos_level(T):
    if T < CALM_END:
        return 0.0
    if T < CHAOS_END:
        return ((T - CALM_END) / (CHAOS_END - CALM_END)) ** 1.6
    if T < FLASH_T:
        return 1.0
    return 0.0


def speed(T):
    return 1 + (MAX_SPEED - 1) * chaos_level(T) ** 1.3


# integrate the spin "clock" so the speed-ups are smooth
DT = FRAME_MS / 1000
N = int(round(DURATION / DT))
clock, p = [], 0.0
for k in range(N):
    clock.append(p)
    p += DT * speed(k * DT) / BASE_LOOP
# after the flash, re-sync the clock so the last frame flows into frame 0
for k in range(N):
    T = k * DT
    if T >= FLASH_T:
        clock[k] = (T - DURATION) / BASE_LOOP


# ---- incommensurate "noise" built from waves whose speeds share no rhythm -----------
WAVES = [(0.73, 0.0), (1.19, 1.3), (1.61, 2.9), (2.27, 4.1), (3.07, 5.3)]


def drift(tc, seed, amp=1.0):
    """Smooth but non-repeating value in about [-1, 1]."""
    return amp * sum(math.sin(r * tc * (1 + 0.13 * seed) + p + seed * 2.17) / (1 + n * 0.6)
                     for n, (r, p) in enumerate(WAVES)) / 2.4


STATE = dict(c=0.0, tc=0.0, rotA=0.0, qA=0.33, rotB=0.0, qB=0.33, wB=0.0)
_orig_field = bh.field


def _with_disk(rot, q, fn):
    bh.DISK_ROT, bh.DISK_Q = rot, q
    bh.COSR, bh.SINR = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return fn()


def warp(x, y, tc, c, seed):
    """Domain warp: several travelling waves at unrelated speeds and directions."""
    wx = (2.6 * math.sin(0.11 * y + 0.05 * x + 1.7 * tc + seed)
          + 1.7 * math.sin(0.23 * y - 0.09 * x - 2.9 * tc + 2 * seed)
          + 1.0 * math.sin(0.41 * x + 0.17 * y + 4.3 * tc))
    wy = (1.1 * math.sin(0.07 * x - 0.12 * y + 2.3 * tc + 3 * seed)
          + 0.7 * math.sin(0.19 * x + 0.21 * y - 3.7 * tc + seed))
    # the warp itself breathes unevenly over the screen
    g = 0.6 + 0.4 * math.sin(0.05 * x + 0.13 * y + 0.9 * tc + seed)
    return wx * c * g, wy * c * g


def local_lag(x, y, tc, c):
    """Different regions run ahead of / behind each other (asynchronous motion)."""
    return c * 0.35 * (math.sin(0.09 * x + 0.6 * tc) * math.cos(0.15 * y - 0.4 * tc)
                       + 0.5 * math.sin(0.21 * x - 0.17 * y + 1.3 * tc))


def wavy_field(x, y, t):
    c, tc = STATE["c"], STATE["tc"]
    if c <= 0.001:
        return _orig_field(x, y, t)
    wx, wy = warp(x, y, tc, c, 0.0)
    lag = local_lag(x, y, tc, c)
    a = _with_disk(STATE["rotA"], STATE["qA"], lambda: _orig_field(x + wx, y + wy, (t + lag) % 1.0))
    if STATE["wB"] < 0.02:
        return a
    wx2, wy2 = warp(x, y, tc * 1.31, c, 1.9)
    b = _with_disk(STATE["rotB"], STATE["qB"], lambda: _orig_field(x + wx2, y + wy2, (t - 1.4 * lag + 0.37) % 1.0))
    bv = b[0] * STATE["wB"]
    # braid: the strands take turns being in front, and the pattern itself drifts
    braid = math.sin(0.18 * x - 0.31 * y * bh.ASPECT + 2.1 * tc + 1.5 * math.sin(0.07 * x + 1.1 * tc))
    if a[2] == "shadow" and bv < 0.35:
        return a
    if bv * (1.15 if braid > 0 else 0.7) > a[0] * (0.7 if braid > 0 else 1.15):
        return (bv, b[1], b[2] if b[2] != "shadow" else "disk")
    return a


bh.field = wavy_field


def set_state(T, k):
    c = chaos_level(T)
    s = speed(T)
    tc = clock[k] * BASE_LOOP          # chaos clock in "seconds", already accelerating
    STATE["c"], STATE["tc"] = c, tc
    # strand A drifts on its own uneven path instead of a regular swivel
    STATE["rotA"] = BASE["rot"] + c * 14 * drift(tc, 0.0)
    STATE["qA"] = max(0.12, BASE["q"] + c * 0.12 * drift(tc, 1.0))
    # strand B peels off, wanders away and crosses back through A
    STATE["rotB"] = BASE["rot"] + c * (28 * drift(tc, 2.0) + 18 * math.sin(0.6 * tc))
    STATE["qB"] = max(0.1, BASE["q"] + c * 0.25 * drift(tc, 3.0))
    STATE["wB"] = smooth((c - 0.12) / 0.4)
    bh.DISK_ROT, bh.DISK_Q = STATE["rotA"], STATE["qA"]
    bh.COSR, bh.SINR = math.cos(math.radians(bh.DISK_ROT)), math.sin(math.radians(bh.DISK_ROT))
    bh.WARP = BASE["warp"] + 0.9 * c * (0.7 + 0.3 * drift(tc, 4.0))
    bh.CHAOS = c * 0.75
    bh.SHADOW = BASE["shadow"] * (1 + 0.1 * c * drift(tc * 1.7, 5.0))
    bh.JET_GAIN = (1 + 0.8 * c * drift(tc * 2.3, 6.0)) if c > 0.1 else 1.0
    bh.cx, bh.cy = BASE["cx"], BASE["cy"]
    if CHAOS_END <= T < FLASH_T:
        x = (T - CHAOS_END) / COLLAPSE
        bh.ZOOM = 1 + 5 * x ** 2
        bh.SHADOW = BASE["shadow"] * (1 + 0.6 * x)
    else:
        bh.ZOOM = 1.0
    return c, s


def draw_comet(grid, T, k):
    t0 = CALM_END - COMET_TIME
    if not (t0 <= T < CALM_END):
        return
    f = (T - t0) / COMET_TIME
    f = f ** 1.6                                     # accelerates as it falls in
    sx = BASE["cx"] + COMET_FROM[0] * bh.W * 0.6
    sy = BASE["cy"] + COMET_FROM[1] * bh.H * 0.6
    hx = sx + (BASE["cx"] - sx) * f
    hy = sy + (BASE["cy"] - sy) * f
    dx, dy = BASE["cx"] - sx, (BASE["cy"] - sy) * bh.ASPECT
    ang = math.atan2(dy, dx)
    ux, uy = math.cos(ang), math.sin(ang) / bh.ASPECT
    nx, ny = -math.sin(ang), math.cos(ang) / bh.ASPECT
    tail = 42
    for j in range(tail):
        s = 1 - j / tail
        for w in (-1, 0, 1):
            if w and bh.hash01(j, w, k) > s * 0.8:
                continue
            ch = bh.flow_char(ang, 0.3 + 0.6 * s * (0.6 if w else 1), bh.hash01(j, w, k, 4))
            bh.put(grid, hx - ux * j + nx * w * 0.8, hy - uy * j + ny * w * 0.8, ch,
                   bh.PALETTE[min(7, 2 + int(6 * s))], 8)
    for dx_, dy_, ch in ((0, 0, "@"), (1, 0, ")"), (-1, 0, "("), (0, -1, "~"), (0, 1, "~")):
        bh.put(grid, hx + dx_, hy + dy_, ch, (255, 255, 255), 9)


def draw_shockwave(grid, T, k):
    if not (CALM_END <= T < CALM_END + 1.3):
        return
    f = (T - CALM_END) / 1.3
    for ring, delay in ((0, 0.0), (1, 0.18)):
        g = f - delay
        if g <= 0:
            continue
        r = 4 + g * 70
        strength = (1 - g) ** 1.5
        steps = int(2 * math.pi * r * 2.2)
        for j in range(steps):
            a = 2 * math.pi * j / steps
            if bh.hash01(j, k, ring) > strength + 0.3:
                continue
            x = BASE["cx"] + r * math.cos(a)
            y = BASE["cy"] + r * math.sin(a) * 0.55 / bh.ASPECT * 1.6
            ch = "O@o*"[int(bh.hash01(j, k, 9) * 4)] if strength > 0.5 else "o:."[int(bh.hash01(j, k) * 3)]
            bh.put(grid, x, y, ch, bh.PALETTE[min(7, 3 + int(5 * strength))], 8)


def glitch_rows(grid, c, k):
    """Rows bend in tangled waves (heat-haze look) with occasional tears."""
    if c < 0.2:
        return
    tc = STATE["tc"]
    a = (c - 0.2) / 0.8
    for y in range(bh.H):
        shift = a * (3.2 * math.sin(0.33 * y + 2.3 * tc) + 2.0 * math.sin(0.81 * y - 3.9 * tc + 1)
                     + 1.2 * math.sin(1.7 * y + 6.1 * tc))
        if bh.hash01(y, k, 31) < a * 0.08:                       # a tear
            shift += (bh.hash01(y, k, 32) - 0.5) * 18 * a
        sh = int(round(shift))
        if sh:
            row = grid[y]
            grid[y] = row[-sh:] + row[:-sh]


def flash_alpha(T):
    if CALM_END <= T < CALM_END + 0.25:                       # comet impact
        return 0.55 * (1 - (T - CALM_END) / 0.25)
    if FLASH_T - 0.25 <= T < FLASH_T:
        return (T - (FLASH_T - 0.25)) / 0.25
    if FLASH_T <= T < FLASH_T + FLASH_HOLD:
        return 1.0
    if FLASH_T + FLASH_HOLD <= T < DURATION:
        return 1 - smooth((T - FLASH_T - FLASH_HOLD) / REFORM)
    return 0.0


def render(k):
    T = k * DT
    c, _ = set_state(T, k)
    t = clock[k] % 1.0
    grid = bh.frame(k, t)
    draw_comet(grid, T, k)
    draw_shockwave(grid, T, k)
    glitch_rows(grid, c, k)
    img = bh.render_png(grid)
    a = flash_alpha(T)
    if a > 0:
        white = Image.new("RGB", img.size, (226, 224, 255))
        mask = bh.render_png([[(" ", None, 0)] * bh.W for _ in range(bh.H)])  # keeps the frame/title
        img = Image.blend(img, white, a * 0.92)
        # keep the purple border crisp
        bw = 6
        img.paste(mask.crop((0, 0, img.width, bw)), (0, 0))
        img.paste(mask.crop((0, img.height - bw, img.width, img.height)), (0, img.height - bw))
        img.paste(mask.crop((0, 0, bw, img.height)), (0, 0))
        img.paste(mask.crop((img.width - bw, 0, img.width, img.height)), (img.width - bw, 0))
    return img


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    ap.add_argument("--preview", type=float, help="write preview.png at this time (s)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    bh.ROCKET = False
    if a.preview is not None:
        render(int(a.preview / DT)).save(os.path.join(a.out, "preview.png"))
    else:
        imgs = [render(k) for k in range(N)]
        if SCALE != 1:
            imgs = [im.resize((int(im.width * SCALE), int(im.height * SCALE)), Image.LANCZOS) for im in imgs]
        # palette from a calm, a chaotic and a flash frame so every phase looks right
        samples = [imgs[int(N * f)] for f in (0.15, 0.7, 0.88, FLASH_T / DURATION + 0.03)]
        sheet = Image.new("RGB", (samples[0].width, samples[0].height * len(samples)))
        for n, im in enumerate(samples):
            sheet.paste(im, (0, n * im.height))
        pal = sheet.quantize(colors=GIF_COLOURS, method=Image.Quantize.MEDIANCUT)
        q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in imgs]
        path = os.path.join(a.out, "blackhole_story_wavy.gif")
        q[0].save(path, save_all=True, append_images=q[1:], duration=FRAME_MS, loop=0, optimize=True, disposal=1)
        print(f"wrote {path}: {N} frames, {DURATION:.1f} s")
