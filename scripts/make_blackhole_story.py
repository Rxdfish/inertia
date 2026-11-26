#!/usr/bin/env python3
"""Story version of the Inertia black hole (needs make_blackhole.py in the same folder).

Timeline (default ≈ 11 s, loops seamlessly):
  calm   – the black hole spins calmly
  comet  – a comet streaks in and hits the core → flash + shockwave
  chaos  – it wobbles, flickers, glitches and spins faster and faster
  burst  – the disk is sucked in, white flash, and it calmly reforms (loop)

Usage:
  python3 make_blackhole_story.py                  # writes blackhole_story.gif
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
CHAOS_END = 9.4           # instability peaks here
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


def set_state(T, k):
    c = chaos_level(T)
    s = speed(T)
    p = clock[k]
    # wobble / precession of the disk, growing with chaos
    bh.DISK_ROT = BASE["rot"] + c * 16 * math.sin(2 * math.pi * 1.7 * p) + c * 6 * math.sin(2 * math.pi * 5.3 * p)
    bh.DISK_Q = BASE["q"] + c * 0.14 * math.sin(2 * math.pi * 2.3 * p + 1)
    bh.COSR, bh.SINR = math.cos(math.radians(bh.DISK_ROT)), math.sin(math.radians(bh.DISK_ROT))
    bh.WARP = BASE["warp"] + 1.1 * c
    bh.CHAOS = c
    bh.SHADOW = BASE["shadow"] * (1 + 0.12 * c * math.sin(2 * math.pi * 3.1 * p))
    # jets sputter
    bh.JET_GAIN = 1.0 if c < 0.2 else (0.2 + 1.6 * bh.hash01(int(p * 10), 3)) * (1 + c)
    # screen shake
    shake = c ** 1.5 * 1.6
    bh.cx = BASE["cx"] + shake * (bh.hash01(k, 1) - 0.5) * 2
    bh.cy = BASE["cy"] + shake * (bh.hash01(k, 2) - 0.5) * 1.2
    # collapse: everything is pulled inwards
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
    """Shift random rows sideways – a broken-signal look when things get unstable."""
    if c < 0.35:
        return
    for y in range(bh.H):
        if bh.hash01(y, k, 31) < (c - 0.35) * 0.35:
            shift = int((bh.hash01(y, k, 32) - 0.5) * 2 * (2 + 8 * c))
            row = grid[y]
            grid[y] = row[-shift:] + row[:-shift] if shift > 0 else row[-shift:] + row[:-shift]


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
        path = os.path.join(a.out, "blackhole_story.gif")
        q[0].save(path, save_all=True, append_images=q[1:], duration=FRAME_MS, loop=0, optimize=True, disposal=1)
        print(f"wrote {path}: {N} frames, {DURATION:.1f} s")
