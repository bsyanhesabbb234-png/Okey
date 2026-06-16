from PIL import Image, ImageDraw, ImageFont
import io
import os
from typing import Optional

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "../../assets")

COLOR_MAP = {
    "kirmizi": (220, 50, 50),
    "sari": (230, 180, 30),
    "mavi": (50, 100, 220),
    "siyah": (40, 40, 40),
}

BG_DARK = (30, 35, 45)
BG_CARD = (245, 240, 225)
BG_CARD_BORDER = (180, 165, 120)
BG_TABLE = (25, 90, 40)
TEXT_DARK = (20, 20, 20)
TEXT_LIGHT = (255, 255, 255)
JOKER_COLOR = (148, 0, 211)

TAS_W, TAS_H = 48, 68
PADDING = 8
RADIUS = 6

def rounded_rect(draw, xy, radius, fill, outline=None, outline_width=2):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill, outline=outline, width=outline_width)

def draw_tas(draw, x, y, sayi, renk, is_okey=False, is_special_okey=False, index=None):
    shadow_offset = 2
    draw.rounded_rectangle(
        [x + shadow_offset, y + shadow_offset, x + TAS_W + shadow_offset, y + TAS_H + shadow_offset],
        radius=RADIUS, fill=(0, 0, 0, 80)
    )
    bg = BG_CARD
    border = BG_CARD_BORDER
    draw.rounded_rectangle([x, y, x + TAS_W, y + TAS_H], radius=RADIUS, fill=bg, outline=border, width=2)
    
    if is_okey:
        color = JOKER_COLOR
        text = "OK"
        draw.rounded_rectangle([x+3, y+3, x+TAS_W-3, y+TAS_H-3], radius=4, fill=(240, 220, 255), outline=JOKER_COLOR, width=2)
    elif is_special_okey:
        color = JOKER_COLOR
        text = str(sayi)
        draw.rounded_rectangle([x+3, y+3, x+TAS_W-3, y+TAS_H-3], radius=4, fill=(240, 220, 255), outline=JOKER_COLOR, width=2)
    else:
        color = COLOR_MAP.get(renk, TEXT_DARK)
        text = str(sayi)

    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except Exception:
        font_large = ImageFont.load_default()
        font_small = font_large

    bbox = draw.textbbox((0, 0), text, font=font_large)
    tw = bbox[2] - bbox[0]
    tx = x + (TAS_W - tw) // 2
    ty = y + (TAS_H - 30) // 2
    draw.text((tx, ty), text, fill=color, font=font_large)

    if index is not None:
        idx_text = str(index)
        draw.text((x + 2, y + TAS_H - 14), idx_text, fill=(120, 120, 120), font=font_small)

def render_el(tas_listesi, okey_tas=None, title: str = "Elinizdeki Taşlar") -> io.BytesIO:
    from src.game.okey_engine import Tas
    cols = min(len(tas_listesi), 14)
    rows = (len(tas_listesi) + cols - 1) // cols if tas_listesi else 1
    
    img_w = cols * (TAS_W + PADDING) + PADDING + 20
    img_h = rows * (TAS_H + PADDING) + PADDING + 50

    img = Image.new("RGBA", (img_w, img_h), BG_TABLE)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([5, 5, img_w - 5, img_h - 5], radius=12, outline=(255, 255, 255, 60), width=1)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except Exception:
        font_title = ImageFont.load_default()

    draw.text((10, 10), title, fill=TEXT_LIGHT, font=font_title)

    for i, tas in enumerate(tas_listesi):
        col = i % cols
        row = i // cols
        x = PADDING + col * (TAS_W + PADDING) + 10
        y = 35 + PADDING + row * (TAS_H + PADDING)

        is_okey = tas.okey
        is_special = False
        if okey_tas and not tas.okey:
            is_special = (tas.renk == okey_tas.renk and tas.sayi == okey_tas.sayi)

        draw_tas(draw, x, y, tas.sayi, tas.renk, is_okey=is_okey, is_special_okey=is_special, index=i+1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def render_masa_durumu(masa_id: str, oyuncular: dict, siradaki: int, 
                        cop_yigi_ustu=None, goster_tas=None, okey_tas=None) -> io.BytesIO:
    img_w = 600
    img_h = 400
    img = Image.new("RGBA", (img_w, img_h), BG_TABLE)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([5, 5, img_w-5, img_h-5], radius=15, outline=(255,255,255,40), width=2)
    draw.rounded_rectangle([10, 10, img_w-10, img_h-10], radius=12, fill=(20,80,35), outline=(255,255,255,20), width=1)

    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except Exception:
        font_lg = font_md = font_sm = ImageFont.load_default()

    draw.text((img_w//2 - 80, 20), "🎲 Kahvehane Okey Masası", fill=(255, 215, 0), font=font_lg)
    draw.text((img_w//2 - 40, 42), f"Masa: #{masa_id[:6]}", fill=(200, 200, 200), font=font_sm)

    y_pos = 75
    positions = [
        (30, y_pos), (img_w//2 - 60, y_pos),
        (30, y_pos + 130), (img_w//2 - 60, y_pos + 130)
    ]
    for idx, (uid, ad) in enumerate(list(oyuncular.items())[:4]):
        if idx >= len(positions):
            break
        px, py = positions[idx]
        is_siradaki = uid == siradaki
        bg_col = (255, 215, 0, 40) if is_siradaki else (255, 255, 255, 15)
        draw.rounded_rectangle([px, py, px+160, py+90], radius=8, fill=bg_col, outline=(255,215,0) if is_siradaki else (255,255,255,60), width=2)
        icon = "👤" if uid > 0 else "🤖"
        name_short = (icon + " " + ad)[:18]
        draw.text((px+8, py+8), name_short, fill=TEXT_LIGHT, font=font_md)
        if is_siradaki:
            draw.text((px+8, py+32), "⏳ Sırası", fill=(255,215,0), font=font_sm)

    cx, cy = img_w - 160, 140
    draw.rounded_rectangle([cx, cy, cx+130, cy+120], radius=10, fill=(15,60,25), outline=(255,255,255,40), width=1)
    draw.text((cx+10, cy+8), "Masa Merkezi", fill=(200,200,200), font=font_sm)

    if goster_tas:
        draw.text((cx+10, cy+30), "Göster Taşı:", fill=(200,200,200), font=font_sm)
        sayi = "🃏" if goster_tas.okey else str(goster_tas.sayi)
        renk_emoji = {"kirmizi": "🔴", "sari": "🟡", "mavi": "🔵", "siyah": "⚫"}.get(goster_tas.renk, "⬜")
        draw.text((cx+10, cy+48), f"{renk_emoji} {sayi}", fill=TEXT_LIGHT, font=font_md)

    if okey_tas:
        draw.text((cx+10, cy+72), "Okey Taşı:", fill=(200,200,200), font=font_sm)
        sayi = str(okey_tas.sayi)
        renk_emoji = {"kirmizi": "🔴", "sari": "🟡", "mavi": "🔵", "siyah": "⚫"}.get(okey_tas.renk, "⬜")
        draw.text((cx+10, cy+90), f"{renk_emoji} {sayi} ⭐", fill=(255,215,0), font=font_md)

    if cop_yigi_ustu:
        draw.text((cx+10, cy+108), "Üst çöp:", fill=(200,200,200), font=font_sm)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def render_profil(oyuncu: dict) -> io.BytesIO:
    img_w = 500
    img_h = 280
    img = Image.new("RGBA", (img_w, img_h), (15, 20, 35))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, img_w, img_h], radius=16, fill=(20, 28, 48))
    draw.rounded_rectangle([0, 0, img_w, 70], radius=16, fill=(30, 90, 60))
    draw.rectangle([0, 54, img_w, 70], fill=(30, 90, 60))

    try:
        font_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except Exception:
        font_xl = font_lg = font_md = font_sm = ImageFont.load_default()

    ad = oyuncu.get("ad", "Bilinmiyor")
    seviye = oyuncu.get("seviye", 1)
    draw.text((20, 15), f"🎯  {ad}", fill=(255, 255, 255), font=font_xl)
    draw.text((img_w - 100, 20), f"Sv. {seviye}", fill=(255, 215, 0), font=font_lg)

    cip = oyuncu.get("cip", 0)
    galibiyet = oyuncu.get("galibiyet", 0)
    yenilgi = oyuncu.get("yenilgi", 0)
    toplam = oyuncu.get("toplam_mac", 0)
    oran = f"{(galibiyet/toplam*100):.1f}%" if toplam > 0 else "0%"

    stats = [
        ("🪙  Çip", f"{cip:,}", (255, 215, 0)),
        ("🏆  Galibiyet", str(galibiyet), (50, 205, 50)),
        ("💀  Yenilgi", str(yenilgi), (220, 50, 50)),
        ("🎮  Toplam Maç", str(toplam), (135, 206, 235)),
        ("📊  Kazanma Oranı", oran, (255, 165, 0)),
    ]

    for i, (label, val, color) in enumerate(stats):
        col = i % 2
        row = i // 2
        x = 20 + col * 240
        y = 90 + row * 60
        draw.rounded_rectangle([x, y, x+220, y+50], radius=8, fill=(30, 38, 60), outline=(60, 80, 100), width=1)
        draw.text((x + 10, y + 7), label, fill=(160, 175, 200), font=font_sm)
        draw.text((x + 10, y + 24), val, fill=color, font=font_lg)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
