"""Generate the PB Asset Decryptor app icon.

The icon is a stylized chrome pinball perched between two red flippers
on a dark backdrop, with a small "PB" wordmark.  Pinball Brothers'
machines all share this dark/red palette so the result is recognizable
without copying any actual PB logo art.

Run:
    python generate_icon.py

Outputs ``pb_decryptor/icon.ico`` and ``pb_decryptor/icon.png``.
"""

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

BG_TOP    = (28, 32, 48, 255)       # dark navy at the top of the backdrop
BG_BOT    = (10, 12, 18, 255)       # near-black at the bottom

# Pinball — chrome with a hot highlight
BALL_DARK = (60, 70, 90, 255)
BALL_MID  = (170, 180, 195, 255)
BALL_HI   = (245, 250, 255, 255)

# Flippers — Pinball-Brothers red
FLIP_LIGHT = (220, 50, 55, 255)
FLIP_DARK  = (130, 20, 25, 255)

WORDMARK   = (245, 230, 220, 255)
WORDMARK_SHADOW = (10, 10, 10, 200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vert_gradient(size, top, bottom):
    """Return a vertical gradient image."""
    img = Image.new("RGBA", (size, size), top)
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        px_color = tuple(
            int(top[i] * (1 - t) + bottom[i] * t) for i in range(4)
        )
        for x in range(size):
            px[x, y] = px_color
    return img


def _radial_overlay(size, center, radius, color, max_alpha=180):
    """Soft radial highlight blob."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    layers = 24
    for i in range(layers, 0, -1):
        t = i / layers
        r = radius * t
        a = int(max_alpha * (1 - t) ** 1.5)
        d.ellipse(
            [center[0] - r, center[1] - r, center[0] + r, center[1] + r],
            fill=color[:3] + (a,),
        )
    return img.filter(ImageFilter.GaussianBlur(radius=size * 0.01))


def _draw_flipper(draw, left_anchor, right_anchor, base_y, width, height,
                  pivot_left=True, light=FLIP_LIGHT, dark=FLIP_DARK):
    """Draw a single tapered flipper as a polygon, then a darker outline."""
    # Pivot circle is at the wider end.
    if pivot_left:
        pivot = left_anchor
        tip = right_anchor
    else:
        pivot = right_anchor
        tip = left_anchor

    pivot_r = height * 0.55
    tip_r = height * 0.18

    # Approximate the flipper as a quadrilateral with rounded ends.
    import math
    dx = tip[0] - pivot[0]
    dy = tip[1] - pivot[1]
    length = math.hypot(dx, dy) or 1
    nx = -dy / length
    ny = dx / length

    p1 = (pivot[0] + nx * pivot_r, pivot[1] + ny * pivot_r)
    p2 = (tip[0]   + nx * tip_r,   tip[1]   + ny * tip_r)
    p3 = (tip[0]   - nx * tip_r,   tip[1]   - ny * tip_r)
    p4 = (pivot[0] - nx * pivot_r, pivot[1] - ny * pivot_r)

    draw.polygon([p1, p2, p3, p4], fill=light)
    draw.ellipse([pivot[0] - pivot_r, pivot[1] - pivot_r,
                  pivot[0] + pivot_r, pivot[1] + pivot_r], fill=light)
    draw.ellipse([tip[0] - tip_r, tip[1] - tip_r,
                  tip[0] + tip_r, tip[1] + tip_r], fill=light)
    # Inner shadow for depth
    inner_dx = nx * pivot_r * 0.55
    inner_dy = ny * pivot_r * 0.55
    draw.ellipse([pivot[0] - pivot_r * 0.65, pivot[1] - pivot_r * 0.65,
                  pivot[0] + pivot_r * 0.65, pivot[1] + pivot_r * 0.65],
                 fill=dark)


# ---------------------------------------------------------------------------
# Master icon
# ---------------------------------------------------------------------------

def draw_icon(size):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # ── Rounded-square dark backdrop ──────────────────────────────
    backdrop_radius = int(s * 0.18)
    backdrop = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bd_mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(bd_mask).rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=backdrop_radius, fill=255)
    grad = _vert_gradient(s, BG_TOP, BG_BOT)
    backdrop.paste(grad, (0, 0), bd_mask)
    img = Image.alpha_composite(img, backdrop)

    # Subtle red glow rising from the bottom (suggests the playfield lights)
    glow = _radial_overlay(
        s, center=(s // 2, int(s * 0.92)), radius=s * 0.55,
        color=(220, 40, 50, 255), max_alpha=110,
    )
    glow_masked = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glow_masked.paste(glow, (0, 0), bd_mask)
    img = Image.alpha_composite(img, glow_masked)

    d = ImageDraw.Draw(img)

    # ── Flippers near the bottom ─────────────────────────────────
    flipper_y = int(s * 0.78)
    flipper_height = int(s * 0.10)
    inner_pad = int(s * 0.20)
    outer_pad = int(s * 0.10)
    gap_centre_offset = int(s * 0.06)

    # Left flipper: pivot near left edge, tip pointing toward centre.
    _draw_flipper(
        d,
        left_anchor=(outer_pad, flipper_y),
        right_anchor=(s // 2 - gap_centre_offset, int(flipper_y + s * 0.04)),
        base_y=flipper_y, width=int(s * 0.30), height=flipper_height,
        pivot_left=True,
    )
    # Right flipper: mirrored.
    _draw_flipper(
        d,
        left_anchor=(s // 2 + gap_centre_offset, int(flipper_y + s * 0.04)),
        right_anchor=(s - outer_pad, flipper_y),
        base_y=flipper_y, width=int(s * 0.30), height=flipper_height,
        pivot_left=False,
    )

    # ── Pinball — sphere with chrome shading ─────────────────────
    ball_cx = s // 2
    ball_cy = int(s * 0.46)
    ball_r = int(s * 0.22)

    # Soft contact-shadow under the ball
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse(
        [ball_cx - ball_r * 1.05, ball_cy + ball_r * 0.85,
         ball_cx + ball_r * 1.05, ball_cy + ball_r * 1.15],
        fill=(0, 0, 0, 180),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=s * 0.01))
    img = Image.alpha_composite(img, shadow)
    d = ImageDraw.Draw(img)

    # Concentric rings for the chrome look
    steps = 32
    for i in range(steps, 0, -1):
        t = i / steps
        r = ball_r * t
        if t > 0.85:
            color = BALL_DARK
        elif t > 0.5:
            mix = (t - 0.5) / 0.35
            color = tuple(
                int(BALL_MID[k] * (1 - mix) + BALL_DARK[k] * mix)
                for k in range(4)
            )
        else:
            mix = t / 0.5
            color = tuple(
                int(BALL_HI[k] * (1 - mix) + BALL_MID[k] * mix)
                for k in range(4)
            )
        d.ellipse(
            [ball_cx - r, ball_cy - r, ball_cx + r, ball_cy + r],
            fill=color,
        )

    # Specular highlight blob
    hi = _radial_overlay(
        s,
        center=(ball_cx - int(ball_r * 0.32), ball_cy - int(ball_r * 0.34)),
        radius=ball_r * 0.55,
        color=BALL_HI, max_alpha=210,
    )
    img = Image.alpha_composite(img, hi)
    d = ImageDraw.Draw(img)

    # Tiny rim highlight
    d.arc(
        [ball_cx - ball_r, ball_cy - ball_r,
         ball_cx + ball_r, ball_cy + ball_r],
        start=200, end=340,
        fill=(220, 230, 245, 220), width=max(1, s // 96),
    )

    # ── "PB" wordmark across the top ─────────────────────────────
    font = None
    font_size = max(8, int(s * 0.18))
    for candidate in [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        if os.path.isfile(candidate):
            try:
                font = ImageFont.truetype(candidate, font_size)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    text = "PB"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (s - tw) // 2 - bbox[0]
    ty = int(s * 0.06) - bbox[1]

    # Subtle shadow + bright wordmark
    shadow_off = max(1, int(s * 0.012))
    d.text((tx + shadow_off, ty + shadow_off), text, font=font,
           fill=WORDMARK_SHADOW)
    d.text((tx, ty), text, font=font, fill=WORDMARK)

    return img


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "pb_decryptor")
    os.makedirs(out_dir, exist_ok=True)

    sizes = [256, 128, 64, 48, 32, 16]
    images = [draw_icon(sz) for sz in sizes]

    ico_path = os.path.join(out_dir, "icon.ico")
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(sz, sz) for sz in sizes],
        append_images=images[1:],
    )
    print(f"Saved: {ico_path}")

    png_path = os.path.join(out_dir, "icon.png")
    images[0].save(png_path)
    print(f"Saved: {png_path}")


if __name__ == "__main__":
    main()
