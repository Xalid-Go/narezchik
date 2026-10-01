"""
BUBA MEDIA Publication & Bio Checker
Verifies:
1. Presence of #бубавпн hashtag in TikTok / YouTube Shorts descriptions.
2. Presence of Telegram bot link (t.me/bubabot or mention) in profile bio.
"""
import re
import json
import asyncio
from typing import Dict, Any, List, Optional
import httpx

ALLOWED_BIO_KEYWORDS = [
    "t.me/bubabot",
    "bubabot",
    "@bubabot",
    "бубабот",
    "@бубабот",
    "buba vpn",
    "буба впн",
    "bubavpn",
    "mediabuba.ru"
]

REQUIRED_HASHTAG = "#бубавпн"


async def check_video_hashtag(url: str, target_hashtag: str = REQUIRED_HASHTAG) -> Dict[str, Any]:
    """
    Checks if a TikTok or YouTube Shorts video has the mandatory hashtag in its description/title.
    Uses yt-dlp metadata extraction with fallback to web scraping.
    """
    url = url.strip()
    platform = "Unknown"
    if "tiktok.com" in url:
        platform = "TikTok"
    elif "youtube.com" in url or "youtu.be" in url:
        platform = "YouTube"

    normalized_target = target_hashtag.lower().replace("#", "")

    # Run yt-dlp to get title, description and tags
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-playlist",
        "--skip-download",
        "--no-warnings",
        url
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20.0)
        if proc.returncode == 0 and stdout:
            info = json.loads(stdout.decode("utf-8", errors="replace"))
            title = info.get("title", "") or ""
            description = info.get("description", "") or ""
            tags = [t.lower() for t in info.get("tags", []) or []]
            full_text = f"{title}\n{description}".lower()

            # Extract all hashtags
            found_tags = set(re.findall(r"#([a-zA-Zа-яА-Я0-9_]+)", full_text) + tags)
            has_hashtag = normalized_target in [t.lower().replace("#", "") for t in found_tags]

            return {
                "success": True,
                "url": url,
                "platform": platform,
                "title": title[:100],
                "has_hashtag": has_hashtag,
                "target_hashtag": target_hashtag,
                "all_hashtags": [f"#{t}" for t in found_tags],
                "message": (
                    f"✅ Хэштег {target_hashtag} найден в публикации!"
                    if has_hashtag
                    else f"❌ Обязательный хэштег {target_hashtag} НЕ найден в описании!"
                )
            }
    except Exception as e:
        pass

    # Fallback to direct HTTP oEmbed / web fetch
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            text = resp.text.lower()
            found_tags = set(re.findall(r"#([a-zA-Zа-яА-Я0-9_]+)", text))
            has_hashtag = normalized_target in [t.lower().replace("#", "") for t in found_tags]

            return {
                "success": True,
                "url": url,
                "platform": platform,
                "has_hashtag": has_hashtag,
                "target_hashtag": target_hashtag,
                "all_hashtags": [f"#{t}" for t in found_tags][:15],
                "message": (
                    f"✅ Хэштег {target_hashtag} обнаружен на странице!"
                    if has_hashtag
                    else f"❌ Хэштег {target_hashtag} не обнаружен!"
                )
            }
    except Exception as err:
        return {
            "success": False,
            "url": url,
            "platform": platform,
            "has_hashtag": False,
            "target_hashtag": target_hashtag,
            "error": str(err),
            "message": f"⚠️ Не удалось загрузить метаданные ссылки: {err}"
        }


async def check_profile_bio(url: str, allowed_keywords: List[str] = None) -> Dict[str, Any]:
    """
    Checks if a TikTok or YouTube user profile has the required link/mention in bio.
    Works with both clickable website links and non-clickable bio text.
    """
    url = url.strip()
    if allowed_keywords is None:
        allowed_keywords = ALLOWED_BIO_KEYWORDS

    platform = "TikTok" if "tiktok.com" in url else ("YouTube" if "youtube.com" in url else "Profile")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            html = resp.text

            # Look for matches in entire page source / bio container
            found_keyword = None
            lower_html = html.lower()

            for kw in allowed_keywords:
                if kw.lower() in lower_html:
                    found_keyword = kw
                    break

            # Try to extract bio text snippet for display
            bio_snippet = ""
            bio_match = re.search(r'data-e2e="user-bio"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
            if bio_match:
                bio_snippet = re.sub(r"<[^>]+>", "", bio_match.group(1)).strip()
            elif '"description":"' in html:
                m = re.search(r'"description":"([^"]+)"', html)
                if m:
                    bio_snippet = m.group(1)[:200]

            return {
                "success": True,
                "url": url,
                "platform": platform,
                "link_found": found_keyword is not None,
                "matched_keyword": found_keyword,
                "bio_snippet": bio_snippet,
                "message": (
                    f"✅ Ссылка/упоминание найдено в профиле: '{found_keyword}'!"
                    if found_keyword
                    else "❌ Ссылка на @bubabot или BUBA VPN в шапке профиля не найдена!"
                )
            }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "platform": platform,
            "link_found": False,
            "error": str(e),
            "message": f"⚠️ Ошибка проверки профиля: {e}"
        }
