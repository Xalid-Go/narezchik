"""
BubaClipper Telegram Bot (aiogram 3)
Complete automation suite for BUBA MEDIA creators:
- 🎬 Вставка баннера (тайминги, синий фон, ускорение 1.2x)
- 💬 Авто-субтитры (Whisper)
- ✨ Авто-видео (комбайн)
- 🔎 Проверка хэштега (#бубавпн)
- 🔗 Проверка ссылки в профиле
- 💎 VIP-поддержка (тикеты)
- ✅ Проверка видео для подачи (аудит)
- ⚡ Приоритетная подача на выплату
- 🎞 Объединить два видео (сплит)
- 🪞 Отзеркаливание (hflip)
"""
import os
import sys
import json
import asyncio
import logging
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from rules import DEFAULT_BANNER_WIDTH, DEFAULT_BANNER_HEIGHT
from checker import check_video_hashtag, check_profile_bio
from audit import audit_clip_submission
from tickets import create_ticket, list_tickets, submit_payout_request, list_payout_requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "bot_config.json")
os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)


def get_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token and os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                token = cfg.get("token", "").strip()
        except Exception:
            pass
    return token


class BotStates(StatesGroup):
    waiting_hashtag_url = State()
    waiting_bio_url = State()
    waiting_audit_data = State()
    waiting_vip_message = State()
    waiting_payout_data = State()


def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✨ Авто-видео (Комбайн)", callback_data="btn_autovideo")
    builder.button(text="🎬 Вставка баннера", callback_data="btn_banner")
    builder.button(text="💬 Авто-субтитры", callback_data="btn_subtitles")
    builder.button(text="🎞 Объединить видео", callback_data="btn_split")
    builder.button(text="🪞 Отзеркаливание", callback_data="btn_mirror")
    builder.button(text="🔎 Проверить хэштег", callback_data="btn_hashtag")
    builder.button(text="🔗 Проверить ссылку в био", callback_data="btn_bio")
    builder.button(text="✅ Проверка для подачи", callback_data="btn_audit")
    builder.button(text="⚡ Приоритетная выплата", callback_data="btn_payout")
    builder.button(text="💎 VIP-поддержка", callback_data="btn_vip")
    builder.adjust(2, 2, 2, 2, 2)
    return builder.as_markup()


dp = Dispatcher(storage=MemoryStorage())


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome_text = (
        "👋 **Добро пожаловать в BubaClipper Pro Bot!**\n\n"
        "Ваш персональный инструмент для создания и верификации нарезки под правила **BUBA MEDIA**:\n\n"
        "• 🎬 **Баннер:** расчет таймингов (Правило 3.4), удаление синего фона, ускорение до 1.2×\n"
        "• 💬 **Авто-субтитры:** распознавание речи и стильный текст в стиле TikTok\n"
        "• ✨ **Авто-видео:** полный конвейер в 1 клик\n"
        "• 🔎 **Проверка хэштега:** мгновенный поиск `#бубавпн` в TikTok/Shorts\n"
        "• 🔗 **Проверка профиля:** поиск ссылки на `@bubabot` в шапке профиля\n"
        "• ✅ **Аудит видео:** проверка формата, таймингов и площади $\\ge 25\\%$\n"
        "• ⚡ **Приоритетная подача:** отправка заявки в PRO-очередь модерации\n"
        "• 💎 **VIP-поддержка:** персональные тикеты с номером заявки\n\n"
        "Выберите действие в меню ниже:"
    )
    await message.answer(welcome_text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


@dp.callback_query(F.data == "btn_autovideo")
async def cb_autovideo(call: types.CallbackQuery):
    text = (
        "✨ **Авто-видео (One-Click Pipeline)**\n\n"
        "Выполняет весь комплекс задач за 1 запуск:\n"
        "1. Нарезка фрагмента речи спикера.\n"
        "2. Подстановка геймплея Subway Surfers снизу (с динамическим смещением).\n"
        "3. Вставка анимированного баннера (1220x530, от краев до краев).\n"
        "4. Заморозка видео и звука во время показа рекламы.\n"
        "5. Генерация субтитров Whisper.\n"
        "6. Отзеркаливание для обхода теневого бана.\n\n"
        "💡 Для запуска перейдите в веб-панель: `http://localhost:8000` или отправьте видео в чат."
    )
    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == "btn_banner")
async def cb_banner(call: types.CallbackQuery):
    text = (
        "🎬 **Вставка баннера BUBA MEDIA**\n\n"
        "• **Размер:** 1220x530 px (27.6% площади экрана, от краев до краев).\n"
        "• **Синий фон:** поддерживается удаление фона (ChromaKey/Colorkey).\n"
        "• **Ускорение:** до 1.2× с синхронизацией аудио (`atempo`).\n"
        "• **Тайминги:**\n"
        "  - Ролик до 120с: ровно в середине.\n"
        "  - Ролик 120–180с: 0:30, 1:30, 2:30.\n"
        "  - Ролик > 180с: каждые 60 секунд."
    )
    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == "btn_subtitles")
async def cb_subtitles(call: types.CallbackQuery):
    text = (
        "💬 **Автоматические субтитры**\n\n"
        "• Распознавание речи через искусственный интеллект (Whisper).\n"
        "• Стиль: жирный шрифт Arial Black, белый текст, желтые акценты, черная контрастная обводка.\n"
        "• Разбивка на короткие фразы (2–3 слова) для максимального удержания аудитории TikTok."
    )
    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == "btn_split")
async def cb_split(call: types.CallbackQuery):
    text = (
        "🎞 **Объединение двух видео (Сплит)**\n\n"
        "• Верхняя половина: основная история / интервью (1080x960).\n"
        "• Нижняя половина: Subway Surfers без звука (1080x960).\n"
        "• Баннер накладывается строго по центру между двумя видео."
    )
    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == "btn_mirror")
async def cb_mirror(call: types.CallbackQuery):
    text = (
        "🪞 **Отзеркаливание (Mirroring)**\n\n"
        "Горизонтальный разворот видео (`hflip`) позволяет эффективно обходить автоматические детекторы заимствованного контента в TikTok и YouTube Shorts."
    )
    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()


# ------------------ ХЭШТЕГ ------------------
@dp.callback_query(F.data == "btn_hashtag")
async def cb_hashtag(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🔎 Отправьте ссылку на видео в TikTok или YouTube Shorts для проверки хэштега `#бубавпн`:")
    await state.set_state(BotStates.waiting_hashtag_url)
    await call.answer()


@dp.message(BotStates.waiting_hashtag_url)
async def process_hashtag_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    msg = await message.answer("⏳ Проверяем публикацию...")
    res = await check_video_hashtag(url)
    await state.clear()
    ans = f"{res.get('message', '')}\n\n"
    if res.get("all_hashtags"):
        ans += f"Найденные тэги: {', '.join(res['all_hashtags'][:8])}"
    await msg.edit_text(ans)


# ------------------ БИО ПРОФИЛЯ ------------------
@dp.callback_query(F.data == "btn_bio")
async def cb_bio(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🔗 Отправьте ссылку на профиль TikTok (`tiktok.com/@username`) или канал YouTube для проверки ссылки на бота:")
    await state.set_state(BotStates.waiting_bio_url)
    await call.answer()


@dp.message(BotStates.waiting_bio_url)
async def process_bio_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    msg = await message.answer("⏳ Анализируем шапку профиля...")
    res = await check_profile_bio(url)
    await state.clear()
    ans = f"{res.get('message', '')}\n\n"
    if res.get("bio_snippet"):
        ans += f"📝 Описание био: _{res['bio_snippet']}_"
    await msg.edit_text(ans, parse_mode="Markdown")


# ------------------ АУДИТ ------------------
@dp.callback_query(F.data == "btn_audit")
async def cb_audit(call: types.CallbackQuery):
    # Check the latest rendered clip in output/
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    files = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith(".mp4")] if os.path.exists(out_dir) else []
    if files:
        latest = max(files, key=os.path.getmtime)
        res = await audit_clip_submission(latest)
        report = (
            f"✅ **Отчет пред-аудита ролика перед подачей:**\n\n"
            f"📁 Файл: `{os.path.basename(latest)}`\n"
            f"⏱ Длительность: {res['duration']} сек.\n"
            f"🏆 Оценка: **{res['score']}%** ({res['verdict']})\n\n"
            f"**Чек-лист:**\n"
        )
        for item in res["checklist"]:
            ico = "✅" if item["status"] == "PASS" else ("⚠️" if item["status"] == "WARN" else "❌")
            report += f"{ico} **{item['title']}:** {item['details']}\n"

        report += f"\n💡 *{res['summary']}*"
        await call.message.answer(report, parse_mode="Markdown")
    else:
        await call.message.answer("ℹ️ В папке `output/` пока нет готовых роликов. Сначала создайте клип в веб-панели или авто-видео.")
    await call.answer()


# ------------------ VIP ПОДДЕРЖКА ------------------
@dp.callback_query(F.data == "btn_vip")
async def cb_vip(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💎 **VIP-поддержка**\n\nОпишите ваш вопрос или проблему одним сообщением, и мы откроем приоритетный тикет:")
    await state.set_state(BotStates.waiting_vip_message)
    await call.answer()


@dp.message(BotStates.waiting_vip_message)
async def process_vip_message(message: types.Message, state: FSMContext):
    user_tag = message.from_user.username or str(message.from_user.id)
    ticket = create_ticket(f"@{user_tag}", "Вопрос по выплатам/нарезке", message.text)
    await state.clear()
    await message.answer(
        f"💎 **Заявка #{ticket['id']} зарегистрирована!**\n\n"
        f"Статус: `{ticket['status']}`\n"
        f"Команда VIP-поддержки уже уведомлена. Ответ поступит в личные сообщения или этот диалог."
    )


# ------------------ ПРИОРИТЕТНАЯ ВЫПЛАТА ------------------
@dp.callback_query(F.data == "btn_payout")
async def cb_payout(call: types.CallbackQuery, state: FSMContext):
    text = (
        "⚡ **Приоритетная подача заявки на выплату**\n\n"
        "Отправьте данные в формате:\n"
        "`[Ссылка на видео] [Просмотры] [Реквизиты карты или USDT]`\n\n"
        "Пример:\n"
        "`https://tiktok.com/@clip/video/123 250000 TRC20_WALLET_ADDRESS`"
    )
    await call.message.answer(text, parse_mode="Markdown")
    await state.set_state(BotStates.waiting_payout_data)
    await call.answer()


@dp.message(BotStates.waiting_payout_data)
async def process_payout_data(message: types.Message, state: FSMContext):
    parts = message.text.strip().split()
    user_tag = message.from_user.username or str(message.from_user.id)
    if len(parts) >= 3:
        video_url = parts[0]
        views = int(parts[1]) if parts[1].isdigit() else 100000
        wallet = " ".join(parts[2:])
    else:
        video_url = message.text.strip()
        views = 150000
        wallet = "По запросу"

    req = submit_payout_request(
        video_url=video_url,
        profile_url="",
        views=views,
        wallet_or_card=wallet,
        telegram_tag=f"@{user_tag}",
        is_priority=True
    )
    await state.clear()
    await message.answer(
        f"⚡ **Заявка на выплату #{req['id']} принята в PRO-очередь!**\n\n"
        f"Статус: `{req['status']}`\n"
        f"Ожидаемое время проверки: **{req['estimated_review_time']}**\n"
        f"Просмотры: {req['views']:,}\n"
        f"Реквизиты: `{req['wallet_or_card']}`\n\n"
        f"✅ Ваши материалы переданы старшему модератору BUBA MEDIA."
    )


async def main():
    token = get_token()
    if not token:
        print("\n" + "=" * 60)
        print("⚠️ TELEGRAM_BOT_TOKEN не задан!")
        print("Для запуска бота сохраните токен в data/bot_config.json:")
        print('{"token": "ВАШ_ТОКЕН_БОТА"}')
        print("Или экспортируйте: export TELEGRAM_BOT_TOKEN='ВАШ_ТОКЕН'")
        print("=" * 60 + "\n")
        return

    bot = Bot(token=token)
    print("🤖 BubaClipper Telegram Bot успешно запущен и ожидает сообщений!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
