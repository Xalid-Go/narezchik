"""
BUBA MEDIA Compliance Auditor
Performs full pre-flight audit of video clips before submission for payout.
"""
import os
import asyncio
from typing import Dict, Any, List, Optional
from rules import (
    calculate_banner_area_percentage,
    calculate_visible_banner_percentage,
    get_banner_timestamps,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    DEFAULT_BANNER_WIDTH,
    DEFAULT_BANNER_HEIGHT,
)
from checker import check_video_hashtag, check_profile_bio
from video_engine import probe_file


async def audit_clip_submission(
    video_path: str,
    banner_w: int = DEFAULT_BANNER_WIDTH,
    banner_h: int = DEFAULT_BANNER_HEIGHT,
    post_url: Optional[str] = None,
    profile_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Audits video file and social links against BUBA MEDIA rules.
    """
    checklist = []
    all_passed = True

    if not os.path.exists(video_path):
        return {
            "verdict": "REJECTED",
            "passed": False,
            "checklist": [{"title": "Файл видео", "status": "FAIL", "details": "Файл не найден"}],
            "score": 0,
            "filename": os.path.basename(video_path),
            "duration": 0.0,
            "summary": "Файл видео не найден на диске!"
        }

    info = probe_file(video_path)
    duration = float(info.get("duration", 0.0))
    width = int(info.get("width", 0))
    height = int(info.get("height", 0))
    has_audio = bool(info.get("has_audio", False))

    # 1. Video Duration (Rule 1.4: 10s to 300s)
    if 10.0 <= duration <= 300.0:
        checklist.append({
            "rule": "1.4",
            "title": "Длительность ролика",
            "status": "PASS",
            "details": f"{round(duration, 1)} сек. (норма 10–300 сек)"
        })
    else:
        all_passed = False
        checklist.append({
            "rule": "1.4",
            "title": "Длительность ролика",
            "status": "FAIL",
            "details": f"{round(duration, 1)} сек. Нарушение: должно быть от 10 до 300 секунд."
        })

    # 2. Aspect Ratio (Vertical 9:16)
    if height > width:
        checklist.append({
            "rule": "1.3",
            "title": "Формат 9:16 (Вертикальный)",
            "status": "PASS",
            "details": f"Разрешение {width}x{height} (вертикальный формат)"
        })
    else:
        all_passed = False
        checklist.append({
            "rule": "1.3",
            "title": "Формат 9:16 (Вертикальный)",
            "status": "FAIL",
            "details": f"Разрешение {width}x{height}. Требуется вертикальный формат 9:16."
        })

    # 3. Audio stream (Rule 2.3: voice & sound required)
    if has_audio:
        checklist.append({
            "rule": "2.3",
            "title": "Звуковая дорожка",
            "status": "PASS",
            "details": "Звук обнаружен и активен"
        })
    else:
        all_passed = False
        checklist.append({
            "rule": "2.3",
            "title": "Звуковая дорожка",
            "status": "FAIL",
            "details": "Звук отсутствует! По правилу 2.3 ролик без звука отклоняется."
        })

    # 4. Strict Visible Banner Dimensions (Rule 3.2: >= 25% screen area)
    vis_pct = calculate_visible_banner_percentage(banner_w, banner_h)
    box_pct = calculate_banner_area_percentage(banner_w, banner_h)
    if vis_pct >= 25.0:
        checklist.append({
            "rule": "3.2",
            "title": "Видимая площадь баннера (без прозрачных полей)",
            "status": "PASS",
            "details": f"{vis_pct}% чистого баннера на экране (норма >= 25%). Общий габарит: {box_pct}%"
        })
    else:
        all_passed = False
        checklist.append({
            "rule": "3.2",
            "title": "Видимая площадь баннера",
            "status": "FAIL",
            "details": f"Только {vis_pct}% видимой площади (из-за прозрачных полей исходника баннер занимает < 25%). Рекомендуется размер 1260x550 (25.8%)."
        })

    # 5. Banner Edge-to-Edge coverage
    if banner_w >= 1080:
        checklist.append({
            "rule": "3.1",
            "title": "Ширина баннера от краев до краев",
            "status": "PASS",
            "details": f"{banner_w} px (заполняет 100% ширины экрана)"
        })
    else:
        checklist.append({
            "rule": "3.1",
            "title": "Ширина баннера",
            "status": "WARN",
            "details": f"{banner_w} px (рекомендуется от краев до краев >= 1080 px)"
        })

    # 6. Expected banner timings
    expected_ts = get_banner_timestamps(duration)
    ts_str = ", ".join([f"{t}с" for t in expected_ts])
    checklist.append({
        "rule": "3.4",
        "title": "Тайминги баннера",
        "status": "PASS",
        "details": f"Рассчитано {len(expected_ts)} появление(я): {ts_str}"
    })

    # 7. Post Hashtag Check (if URL provided)
    if post_url:
        ht_res = await check_video_hashtag(post_url)
        if ht_res.get("has_hashtag"):
            checklist.append({
                "rule": "2.9",
                "title": "Хэштег #бубавпн в посте",
                "status": "PASS",
                "details": f"Хэштег найден на {ht_res.get('platform', 'платформе')}"
            })
        else:
            all_passed = False
            checklist.append({
                "rule": "2.9",
                "title": "Хэштег #бубавпн в посте",
                "status": "FAIL",
                "details": f"Хэштег #бубавпн не найден в описании: {post_url}"
            })

    # 8. Profile Bio Link Check (if URL provided)
    if profile_url:
        bio_res = await check_profile_bio(profile_url)
        if bio_res.get("link_found"):
            checklist.append({
                "rule": "4.6",
                "title": "Ссылка в профиле на бота",
                "status": "PASS",
                "details": f"Найдено: '{bio_res.get('matched_keyword')}'"
            })
        else:
            all_passed = False
            checklist.append({
                "rule": "4.6",
                "title": "Ссылка в профиле на бота",
                "status": "FAIL",
                "details": f"Ссылка на @bubabot не обнаружена в профиле: {profile_url}"
            })

    passed_count = sum(1 for c in checklist if c["status"] == "PASS")
    score_pct = int(round((passed_count / len(checklist)) * 100))

    return {
        "verdict": "APPROVED" if all_passed else "NEEDS_FIX",
        "passed": all_passed,
        "score": score_pct,
        "filename": os.path.basename(video_path),
        "duration": round(duration, 2),
        "checklist": checklist,
        "summary": (
            "✅ Видео полностью готово к подаче на выплату BUBA MEDIA!"
            if all_passed
            else "⚠️ Обнаружены несоответствия регламенту. Исправьте отмеченные пункты."
        )
    }
