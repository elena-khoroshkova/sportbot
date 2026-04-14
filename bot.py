"""
Workout Check-in Bot
- Кнопка в группе → всплывающее уведомление только для пользователя
- Фото с подписью остаётся в чате (видят все)
- Все системные сообщения бота удаляются
"""

import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import random

PHRASES = [
    "Ты большой молодец, так держать! 🌟",
    "Очень рада за тебя, продолжай в том же духе! 😊",
    "Каждая тренировка делает тебя чуточку лучше 💛",
    "Ты справился — это главное! 🙌",
    "Гордимся тобой! Так и держи 🫶",
    "Отлично поработал сегодня! ✨",
    "Твои усилия не проходят даром 💪",
    "Здорово! Ты вдохновляешь остальных 🌈",
    "Вот это да! Умничка 🎉",
    "Сегодня ты сделал важный шаг к своей цели 🎯",
    "Всё получается, продолжай! 🌱",
    "Ты заботишься о себе — это прекрасно 💚",
    "Движение — это жизнь, и ты это понимаешь! 🌿",
    "Так приятно видеть твою активность! 😍",
    "Тело говорит тебе спасибо 🙏",
    "Отличная работа, не останавливайся! 🚀",
    "Ты молодец что нашёл время на себя 💙",
    "День засчитан! Ты великолепен 🏅",
    "Маленький шаг каждый день — большой результат! 📈",
    "Ты делаешь это — и это восхитительно! ⭐",
    "Приятно видеть тебя в деле! 👏",
    "Твоя настойчивость вдохновляет! 🌸",
    "Здорово что ты не сдаёшься! 💫",
    "Умница, так и держи! 🤍",
    "Ты заслуживаешь всех похвал сегодня! 🥰",
    "Ещё один день — ещё одна победа! 🏆",
    "Отлично! Ты на правильном пути 🛤️",
    "Мы болеем за тебя каждый день! 💕",
    "Вот это самодисциплина! Восхищаемся 🌻",
    "Ты делаешь мир лучше — начиная с себя 🌍",
    "Сегодня ты выбрал себя — это важно! 💛",
    "Так держать! Ты на верном пути 🌟",
    "Каждая тренировка — подарок себе 🎁",
    "Хорошая работа! Мы тобой гордимся 🫂",
    "Ты умеешь находить время на главное! ⏰💚",
    "Бодрость духа и тела — твоя суперсила! ✨",
    "Отличный пример для всех нас! 🌠",
    "Замечательно! Продолжай радовать нас! 😄",
    "Ты доказываешь, что всё возможно! 💪🌈",
    "Здорово! Твоё тело скажет спасибо завтра 🌅",
    "Молодец что не пропустил! 🎊",
    "Это твоя маленькая победа сегодня 🥇",
    "Ты заряжаешь нас своим примером! ⚡",
    "Прекрасный результат! Так и держи 🌺",
    "Спасибо что не сдаёшься! 🤗",
    "Каждый день ты становишься лучше 📊",
    "Ты вложил время в себя — это бесценно 💎",
    "Браво! Отличная активность 👌",
    "Ты делаешь это и мы это замечаем! 👀💛",
    "Замечательно! День прожит с пользой 🌞",
]

last_phrase = None

import gspread
from google.oauth2.service_account import Credentials

# ─── НАСТРОЙКИ ───────────────────────────────────────────────
BOT_TOKEN = "8760645112:AAH1VKqfmOf9pEWhhMsaG5DWUMErTwNYIyQ"
SPREADSHEET_ID = "1JQkN_ZbSaO3-J4WtWGkNGaZkOsBcHwNcqKoFMIhJKQI"
import json, tempfile, os

_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
if _creds_json:
    _tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    _tmp.write(_creds_json)
    _tmp.flush()
    CREDENTIALS_FILE = _tmp.name
else:
    CREDENTIALS_FILE = "/Users/xoroshok/Downloads/credentials.json"  # локально

ADMIN_IDS = [307404504]
# ─────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CheckinStates(StatesGroup):
    waiting_for_photo_with_caption = State()


def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        sheet = spreadsheet.worksheet("Чекины")
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title="Чекины", rows=10000, cols=10)
        sheet.append_row(["Дата", "Время", "Имя", "Username", "Telegram ID", "Описание", "Фото (file_id)"])
        sheet.format("A1:G1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.9}
        })
    return sheet


def save_checkin(user: types.User, description: str, photo_file_id: str):
    sheet = get_sheet()
    now = datetime.now()
    row = [
        now.strftime("%d.%m.%Y"),
        now.strftime("%H:%M"),
        user.full_name,
        f"@{user.username}" if user.username else "—",
        str(user.id),
        description,
        photo_file_id,
    ]
    sheet.append_row(row)


def get_stats_text() -> str:
    sheet = get_sheet()
    records = sheet.get_all_records()

    if not records:
        return "Пока нет ни одного чекина."

    total = len(records)
    by_user: dict[str, int] = {}
    for r in records:
        name = r.get("Имя", "Неизвестно")
        by_user[name] = by_user.get(name, 0) + 1

    top = sorted(by_user.items(), key=lambda x: x[1], reverse=True)
    lines = [f"📊 *Статистика тренировок*\n", f"Всего чекинов: *{total}*\n", "*Топ сотрудников:*"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, count) in enumerate(top[:20]):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {name} — {count} тр.")
    return "\n".join(lines)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


async def try_delete(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# ─── КНОПКА ДЛЯ ЗАКРЕПЛЕНИЯ ──────────────────────────────────
@dp.message(Command("pin"))
async def cmd_pin(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отметить тренировку", callback_data="start_checkin")]
    ])
    await message.answer("💪 Нажми кнопку чтобы отметить тренировку:", reply_markup=keyboard)


# ─── НАЖАТИЕ КНОПКИ ──────────────────────────────────────────
@dp.callback_query(lambda c: c.data == "start_checkin")
async def callback_checkin(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()  # убираем часики

    # Отправляем инструкцию в чат — удалим сразу после получения фото
    sent = await callback.message.answer(
        f"📸 {callback.from_user.first_name}, отправьте фото/скриншот с подписью — какую активность выбрали сегодня!"
    )
    await state.set_state(CheckinStates.waiting_for_photo_with_caption)
    await state.update_data(
        chat_id=sent.chat.id,
        bot_message_ids=[sent.message_id],
        checkin_cmd_id=None,
        user_id=callback.from_user.id
    )

    # Таймаут 2 минуты — если нет фото, удаляем сообщение и сбрасываем
    async def timeout_cleanup():
        await asyncio.sleep(120)
        current = await state.get_state()
        if current == CheckinStates.waiting_for_photo_with_caption.state:
            data = await state.get_data()
            if data.get("user_id") == callback.from_user.id:
                for msg_id in data.get("bot_message_ids", []):
                    await try_delete(data["chat_id"], msg_id)
                await state.clear()

    asyncio.create_task(timeout_cleanup())


# ─── /checkin КОМАНДОЙ ───────────────────────────────────────
@dp.message(Command("checkin"))
async def cmd_checkin(message: types.Message, state: FSMContext):
    await state.set_state(CheckinStates.waiting_for_photo_with_caption)
    await state.update_data(
        chat_id=message.chat.id,
        bot_message_ids=[],
        checkin_cmd_id=message.message_id,
        user_id=message.from_user.id
    )
    # Удаляем команду /checkin сразу
    await try_delete(message.chat.id, message.message_id)
    # Показываем попап только этому пользователю — невозможно через message, поэтому тихо ждём фото


# ─── ПОЛУЧИЛИ ФОТО ───────────────────────────────────────────
@dp.message(CheckinStates.waiting_for_photo_with_caption, F.photo)
async def process_photo_with_caption(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # Игнорируем фото от других пользователей
    if data.get("user_id") and message.from_user.id != data["user_id"]:
        return

    if not message.caption or not message.caption.strip():
        # Показываем ошибку только отправителю через reply который удалим
        sent = await message.reply(
            "⚠️ Нет подписи! Отправь ещё раз — фото и подпись вместе."
        )
        # Удаляем оба через 5 секунд
        async def cleanup():
            await asyncio.sleep(5)
            await try_delete(message.chat.id, sent.message_id)
            await try_delete(message.chat.id, message.message_id)
        asyncio.create_task(cleanup())
        return

    photo = message.photo[-1]
    description = message.caption.strip()

    # Удаляем все системные сообщения бота
    for msg_id in data.get("bot_message_ids", []):
        await try_delete(data["chat_id"], msg_id)

    await state.clear()

    # Показываем "Молодчина!" только через всплывающее — но это callback_query
    # Поэтому просто записываем тихо, фото остаётся в чате
    asyncio.create_task(_save_and_notify(message, description, photo.file_id))


async def _save_and_notify(message: types.Message, description: str, photo_file_id: str):
    try:
        save_checkin(message.from_user, description, photo_file_id)
    except Exception as e:
        logger.error(f"Ошибка записи в Sheets: {e}")

    # Отвечаем рандомной фразой (не повторяя предыдущую)
    global last_phrase
    available = [p for p in PHRASES if p != last_phrase]
    phrase = random.choice(available)
    last_phrase = phrase
    try:
        await message.reply(phrase, message_effect_id="5104841245755180586")
    except Exception:
        await message.reply(phrase)


# ─── ИГНОРИРУЕМ ОСТАЛЬНЫЕ СООБЩЕНИЯ В СОСТОЯНИИ ─────────────
@dp.message(CheckinStates.waiting_for_photo_with_caption)
async def process_wrong_input(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # Игнорируем сообщения от других пользователей
    if data.get("user_id") and message.from_user.id != data["user_id"]:
        return

    # Показываем подсказку и удаляем через 5 секунд
    sent = await message.reply("📸 Нужно отправить фото с подписью — одним сообщением.")
    async def cleanup():
        await asyncio.sleep(5)
        await try_delete(message.chat.id, sent.message_id)
        await try_delete(message.chat.id, message.message_id)
    asyncio.create_task(cleanup())


# ─── СТАТИСТИКА ──────────────────────────────────────────────
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Только для администраторов.")
        return
    try:
        text = get_stats_text()
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await message.answer("❌ Не удалось загрузить статистику.")


@dp.message(Command("mystats"))
async def cmd_mystats(message: types.Message):
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        user_id = str(message.from_user.id)
        my_records = [r for r in records if str(r.get("Telegram ID")) == user_id]

        if not my_records:
            await message.answer("У тебя пока нет записанных тренировок. Начни с /checkin 💪")
            return

        count = len(my_records)
        last = my_records[-1]
        await message.answer(
            f"📈 *Твоя статистика*\n\nВсего тренировок: *{count}*\nПоследняя: {last.get('Дата', '?')}\n_{last.get('Описание', '?')}_",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка mystats: {e}")
        await message.answer("❌ Не удалось загрузить данные.")


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    sent = await message.answer(f"Привет, {message.from_user.first_name}! 💪\nНажми кнопку чтобы отметить тренировку.")
    async def cleanup():
        await asyncio.sleep(10)
        await try_delete(message.chat.id, sent.message_id)
        await try_delete(message.chat.id, message.message_id)
    asyncio.create_task(cleanup())


async def main():
    logger.info("Бот запущен!")
    await bot.set_my_commands([
        types.BotCommand(command="checkin", description="✅ Отметить тренировку"),
        types.BotCommand(command="mystats", description="📈 Моя статистика"),
    ])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
