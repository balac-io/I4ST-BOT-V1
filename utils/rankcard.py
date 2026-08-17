"""
Kryvoox Rank Card Generator
Génère une belle image de niveau / rank.
"""

from __future__ import annotations

import io
import math
from typing import Optional, Tuple

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Couleurs
BG_TOP = (22, 24, 32)
BG_BOTTOM = (12, 14, 20)
ACCENT = (88, 101, 242)          # blurple Discord
ACCENT_LIGHT = (114, 137, 218)
BAR_BG = (40, 43, 54)
WHITE = (255, 255, 255)
GRAY = (180, 185, 200)
GOLD = (255, 215, 80)

CARD_W, CARD_H = 934, 282
AVATAR_SIZE = 160


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Charge une police système (fallback sur default)."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _gradient_background(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * y / h)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * y / h)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * y / h)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius: int, fill):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)


def _circle_avatar(avatar: Image.Image, size: int) -> Image.Image:
    avatar = avatar.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(avatar, (0, 0), mask)
    return output


def _draw_progress_bar(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, progress: float):
    """Barre de progression arrondie."""
    progress = max(0.0, min(1.0, progress))
    _rounded_rectangle(draw, (x, y, x + w, y + h), radius=h // 2, fill=BAR_BG)
    if progress > 0:
        fill_w = max(h, int(w * progress))
        # Dégradé simple sur la barre
        for i in range(fill_w):
            ratio = i / max(1, fill_w)
            r = int(ACCENT[0] + (ACCENT_LIGHT[0] - ACCENT[0]) * ratio)
            g = int(ACCENT[1] + (ACCENT_LIGHT[1] - ACCENT[1]) * ratio)
            b = int(ACCENT[2] + (ACCENT_LIGHT[2] - ACCENT[2]) * ratio)
            draw.line([(x + i, y), (x + i, y + h)], fill=(r, g, b))
        # Re-applique les coins arrondis en masquant (approximation)
        _rounded_rectangle(draw, (x, y, x + fill_w, y + h), radius=h // 2, fill=None)
        # On redessine proprement avec rounded
        bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(bar)
        bar_draw.rounded_rectangle([0, 0, fill_w, h], radius=h // 2, fill=ACCENT)
        return bar
    return None


async def fetch_avatar(url: str) -> Image.Image:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()
    return Image.open(io.BytesIO(data)).convert("RGBA")


async def generate_rank_card(
    *,
    username: str,
    avatar_url: str,
    level: int,
    xp: int,
    current_xp: int,
    needed_xp: int,
    rank: int,
    total_msgs: int = 0,
) -> io.BytesIO:
    """
    Génère la rank card et retourne un BytesIO prêt à envoyer.
    """
    # Fond
    card = _gradient_background(CARD_W, CARD_H).convert("RGBA")
    draw = ImageDraw.Draw(card)

    # Accent bar à gauche
    draw.rectangle([0, 0, 8, CARD_H], fill=ACCENT)

    # Avatar
    try:
        avatar_img = await fetch_avatar(avatar_url)
        avatar_circle = _circle_avatar(avatar_img, AVATAR_SIZE)
    except Exception:
        avatar_circle = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), ACCENT)
        ImageDraw.Draw(avatar_circle).ellipse((0, 0, AVATAR_SIZE, AVATAR_SIZE), fill=ACCENT)

    # Ombre légère sous l'avatar
    shadow = Image.new("RGBA", (AVATAR_SIZE + 10, AVATAR_SIZE + 10), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((0, 0, AVATAR_SIZE + 8, AVATAR_SIZE + 8), fill=(0, 0, 0, 80))
    card.paste(shadow, (42, 56), shadow)
    card.paste(avatar_circle, (48, 60), avatar_circle)

    # Anneau autour de l'avatar
    draw.ellipse(
        [46, 58, 46 + AVATAR_SIZE + 4, 58 + AVATAR_SIZE + 4],
        outline=ACCENT,
        width=3,
    )

    # Polices
    font_name = _load_font(36, bold=True)
    font_level = _load_font(28, bold=True)
    font_small = _load_font(20)
    font_tiny = _load_font(16)

    # Username
    name = username[:22] + "…" if len(username) > 22 else username
    draw.text((240, 55), name, font=font_name, fill=WHITE)

    # Rank badge
    rank_text = f"#{rank}" if rank > 0 else "#—"
    draw.text((240, 100), f"RANK  {rank_text}", font=font_small, fill=GOLD)

    # Level
    draw.text((420, 100), f"LEVEL  {level}", font=font_small, fill=ACCENT_LIGHT)

    # XP text
    xp_text = f"{current_xp:,} / {needed_xp:,} XP"
    draw.text((240, 150), xp_text, font=font_tiny, fill=GRAY)

    # Progress bar
    bar_x, bar_y, bar_w, bar_h = 240, 180, 620, 22
    progress = current_xp / needed_xp if needed_xp > 0 else 1.0

    # Background bar
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=11, fill=BAR_BG)

    # Filled bar
    fill_w = max(22, int(bar_w * progress)) if progress > 0 else 0
    if fill_w > 0:
        draw.rounded_rectangle(
            [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
            radius=11,
            fill=ACCENT,
        )

    # Pourcentage
    pct = int(progress * 100)
    draw.text((bar_x + bar_w + 12, bar_y - 2), f"{pct}%", font=font_small, fill=WHITE)

    # Footer info
    draw.text((240, 230), f"Total XP  •  {xp:,}", font=font_tiny, fill=GRAY)
    if total_msgs:
        draw.text((480, 230), f"Messages  •  {total_msgs:,}", font=font_tiny, fill=GRAY)

    # Watermark discret
    draw.text((CARD_W - 130, CARD_H - 28), "Kryvoox", font=font_tiny, fill=(80, 85, 100))

    # Export
    buffer = io.BytesIO()
    card.convert("RGB").save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    return buffer
