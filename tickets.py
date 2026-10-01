"""
VIP Support & Priority Payout Submission System
Provides ticket management with unique IDs and priority queue submissions.
"""
import os
import json
import random
import time
from typing import Dict, Any, List, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

TICKETS_FILE = os.path.join(DATA_DIR, "tickets.json")
PAYOUTS_FILE = os.path.join(DATA_DIR, "payouts.json")


def _load_json(file_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_json(file_path: str, data: List[Dict[str, Any]]):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_ticket(user_id: str, subject: str, message: str, is_vip: bool = True) -> Dict[str, Any]:
    tickets = _load_json(TICKETS_FILE)
    ticket_num = random.randint(1000, 9999)
    ticket_id = f"VIP-{ticket_num}" if is_vip else f"TICK-{ticket_num}"

    new_ticket = {
        "id": ticket_id,
        "user_id": user_id,
        "subject": subject,
        "is_vip": is_vip,
        "status": "В обработке командой" if is_vip else "Открыт",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "messages": [
            {
                "sender": user_id,
                "text": message,
                "time": time.strftime("%H:%M:%S")
            },
            {
                "sender": "Команда BUBA VIP",
                "text": "Здравствуйте! Ваша VIP-заявка принята в приоритетную очередь. Специалист ответит в течение 10-15 минут.",
                "time": time.strftime("%H:%M:%S")
            }
        ]
    }
    tickets.insert(0, new_ticket)
    _save_json(TICKETS_FILE, tickets)
    return new_ticket


def add_ticket_message(ticket_id: str, sender: str, text: str) -> Optional[Dict[str, Any]]:
    tickets = _load_json(TICKETS_FILE)
    for t in tickets:
        if t["id"] == ticket_id:
            t["messages"].append({
                "sender": sender,
                "text": text,
                "time": time.strftime("%H:%M:%S")
            })
            _save_json(TICKETS_FILE, tickets)
            return t
    return None


def list_tickets(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    tickets = _load_json(TICKETS_FILE)
    if user_id:
        return [t for t in tickets if t.get("user_id") == user_id]
    return tickets


def submit_payout_request(
    video_url: str,
    profile_url: str,
    views: int,
    wallet_or_card: str,
    telegram_tag: str,
    is_priority: bool = True
) -> Dict[str, Any]:
    payouts = _load_json(PAYOUTS_FILE)
    payout_num = random.randint(2000, 8999)
    payout_id = f"PAY-{payout_num}"

    req = {
        "id": payout_id,
        "video_url": video_url,
        "profile_url": profile_url,
        "views": views,
        "wallet_or_card": wallet_or_card,
        "telegram_tag": telegram_tag,
        "is_priority": is_priority,
        "status": "⚡ В ПРИОРИТЕТНОЙ ОЧЕРЕДИ" if is_priority else "В очереди",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "estimated_review_time": "До 2 часов" if is_priority else "До 24 часов"
    }
    payouts.insert(0, req)
    _save_json(PAYOUTS_FILE, payouts)
    return req


def list_payout_requests(telegram_tag: Optional[str] = None) -> List[Dict[str, Any]]:
    payouts = _load_json(PAYOUTS_FILE)
    if telegram_tag:
        clean = telegram_tag.lower().replace("@", "")
        return [p for p in payouts if clean in p.get("telegram_tag", "").lower()]
    return payouts
