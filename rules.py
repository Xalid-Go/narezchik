"""
BUBA MEDIA Rules & Constraints Engine
Implements strict compliance with official payout rules:
- 1.4: 10s <= duration <= 300s
- 3.2: Banner area >= 25% of screen (1080x1920)
- 3.4: Timings:
    - Duration <= 120s: 1 banner strictly at midpoint
    - Duration 120s..180s: 3 banners at 0:30, 1:30, 2:30
    - Duration > 180s: 1 banner every 60s (0:30, 1:30, 2:30, 3:30...)
- 3.6: Max banner speed 1.2x (default 1.0x)
- 2.9: Mandatory hashtag #бубавпн
"""
from typing import List, Tuple

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
TOTAL_CANVAS_AREA = CANVAS_WIDTH * CANVAS_HEIGHT  # 2,073,600 px

# Guaranteed >= 25.0% STRICT VISIBLE (opaque) area:
# In the original 1374x552 webm, visible graphic is 1247x497 (surrounded by transparent margins).
# Scaling to 1260x550 yields:
#   Visible on-screen width: 1080 px (100% full width, edge-to-edge)
#   Visible on-screen height: 495.2 px
#   Visible area: 534,815 px = 25.79% of the entire 1080x1920 screen (guaranteed payout pass!)
DEFAULT_BANNER_WIDTH = 1260
DEFAULT_BANNER_HEIGHT = 550

DEFAULT_BANNER_DURATION = 5.04  # реклама.webm length in seconds

ORIG_WEBM_WIDTH = 1374
ORIG_WEBM_HEIGHT = 552
VISIBLE_GRAPHIC_WIDTH = 1247
VISIBLE_GRAPHIC_HEIGHT = 497


def calculate_banner_area_percentage(width: int, height: int) -> float:
    """Returns total container percentage of the 1080x1920 canvas."""
    return round((width * height) / TOTAL_CANVAS_AREA * 100.0, 2)


def calculate_visible_banner_percentage(width: int, height: int) -> float:
    """
    Computes strict visible (opaque) banner area on screen, accounting for transparent borders.
    This resolves the common issue where other cutters yield only 18.5% - 19.4% visible area.
    """
    scale_x = width / ORIG_WEBM_WIDTH
    scale_y = height / ORIG_WEBM_HEIGHT
    visible_w = min(float(CANVAS_WIDTH), VISIBLE_GRAPHIC_WIDTH * scale_x)
    visible_h = VISIBLE_GRAPHIC_HEIGHT * scale_y
    visible_area = visible_w * visible_h
    return round((visible_area / TOTAL_CANVAS_AREA) * 100.0, 2)


def is_banner_compliant(width: int, height: int) -> bool:
    """Checks if strict visible banner area is at least 25% of the screen."""
    return calculate_visible_banner_percentage(width, height) >= 25.0


def get_banner_timestamps(clip_duration: float, banner_duration: float = DEFAULT_BANNER_DURATION) -> List[float]:
    """
    Computes exact start timestamps (in seconds) for banner appearances according to Rule 3.4.
    """
    if clip_duration < 10.0:
        return [0.0]
    
    if clip_duration <= 120.0:
        mid_start = max(0.0, (clip_duration - banner_duration) / 2.0)
        return [round(mid_start, 2)]
    
    timestamps = []
    t = 30.0
    while t + banner_duration <= clip_duration:
        timestamps.append(round(t, 2))
        t += 60.0
        
    return timestamps


def generate_tiktok_caption(part_number: int = None, total_parts: int = None) -> str:
    """Generates a caption compliant with BUBA rules."""
    prefix = ""
    if part_number is not None:
        if total_parts:
            prefix = f"Часть {part_number}/{total_parts} 🔥 "
        else:
            prefix = f"Часть {part_number} 🔥 "
            
    caption = f"{prefix}Смотри до конца! Ссылка на бота в шапке профиля 👆\n\n#бубавпн #рек #fyp #врек #shorts #нарезка"
    return caption
