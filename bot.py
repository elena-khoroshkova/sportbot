import os
import re
import json
import logging
import random
import html
from datetime import datetime

import pytz
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Environment variables ─────────────────────────────────────────────────────
BOT_TOKEN            = os.environ["BOT_TOKEN"]
GOOGLE_SHEET_ID      = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CLIENT_ID     = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
GROUP_CHAT_ID        = os.environ.get("GROUP_CHAT_ID", "")      # e.g. -1001234567890
GROUP_INVITE_LINK    = os.environ.get("GROUP_INVITE_LINK", "")  # e.g. https://t.me/+xxxx
NOTIFY_TIME          = os.environ.get("DAILY_NOTIFY_TIME", "09:00")  # HH:MM local
TIMEZONE             = os.environ.get("TIMEZONE", "UTC")            # e.g. Europe/Kyiv

# ── Conversation states ───────────────────────────────────────────────────────
SPORT, LEVEL, EMAIL = range(3)

# ── Google Sheets helpers ─────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

PENDING_CHECKIN_TTL_SECONDS = 10 * 60  # 10 minutes

PRAISE_PHRASES = [
    "Круто! Так держать 💪",
    "Отличная работа — горжусь тобой 🔥",
    "Засчитано! Ты молодец ✅",
    "Супер! Продолжаем в том же духе 🚀",
    "Вау, мощно! ✅",
]

def _looks_ru(text: str) -> bool:
    return any("А" <= ch <= "я" or ch in "Ёё" for ch in (text or ""))


def _get_lang(update: Update, caption_or_text: str | None = None) -> str:
    """
    Best-effort language selection for replies.
    Returns "ru" or "en".
    """
    # 1) Telegram user language code
    lc = (getattr(update.effective_user, "language_code", None) or "").lower()
    if lc.startswith("ru") or lc.startswith("uk") or lc.startswith("be"):
        return "ru"

    # 2) Content heuristic
    if caption_or_text and _looks_ru(caption_or_text):
        return "ru"

    # 3) Stored preference (if any)
    try:
        prefs = (update.get_bot().get("user_lang") if False else None)  # placeholder
    except Exception:
        prefs = None
    return "en"


def _t(lang: str, key: str, **kwargs) -> str:
    ru = {
        "welcome": "👋 *Добро пожаловать в Sports Challenge!*\n\nРегистрация займёт всего 3 шага.\n\nШаг 1 — выбери вид спорта:",
        "sport_chosen": "Отлично — *{sport}* 🎯\n\nШаг 2 — выбери уровень:",
        "level_chosen": "Уровень *{level}* — принято 💪\n\nШаг 3 — отправь *корпоративный email*.",
        "bad_email": "⚠️ Похоже, это не email.\nПопробуй ещё раз (например, name@company.com):",
        "registered": (
            "🎉 *Ты зарегистрирован(а)!*\n\n"
            "🏅 Спорт: *{sport}*\n"
            "📊 Уровень: *{level}*\n"
            "📧 Email: `{email}`\n\n"
            "{status}\n\n"
            "👇 Вступай в группу челленджа:\n{link}\n\n"
            "Каждый день будет напоминание в группе. Чтобы отметиться, используй `/checkin` (или кнопку) "
            "и ответь фото/скрином *с подписью* одним сообщением. Поехали! 🚀"
        ),
        "cancel": "Регистрация отменена. Когда будешь готов(а), отправь /start.",
        "need_caption_retry": "⚠️ Добавь подпись к фото/скрину (одним сообщением) и отправь ещё раз.",
        "need_caption": "⚠️ Чтобы засчитать тренировку, отправь фото/скрин *с подписью* одним сообщением.",
        "sheet_fail": "⚠️ Не получилось записать отметку в Google Sheets. Проверь `GOOGLE_*` и доступ к таблице, затем попробуй ещё раз.",
        "praise": "{praise}\n\nСегодня отметились: {unique}",
        "stats": "📊 *Статистика за {date}*\n\n✅ Отметились сегодня: *{unique}*\n🧾 Всего записей: *{total}*",
        "reminder": (
            "🌅 *Доброе утро!*\n\n"
            "📅 {date}\n\n"
            "💪 Нажми кнопку ниже (или напиши `/checkin`), затем *ответь на сообщение бота* фото/скрином с подписью — "
            "и я отмечу тебя.\n\n"
            "Каждый день — маленький шаг к цели. Поехали! 🚀"
        ),
        "checkin_prompt": "{mention}, ответь на это сообщение <b>фото/скрином</b> и добавь <b>подпись</b> — чем ты занимался(ась) сегодня.",
        "checkin_ack": "Ок! Ответь фото/скрином с подписью.",
    }
    en = {
        "welcome": "👋 *Welcome to the Sports Challenge!*\n\nI'll register you in 3 quick steps.\n\nStep 1 — choose your sport:",
        "sport_chosen": "Great choice — *{sport}* 🎯\n\nStep 2 — choose your level:",
        "level_chosen": "Level *{level}* — got it 💪\n\nStep 3 — send your *corporate email*.",
        "bad_email": "⚠️ That doesn't look like a valid email.\nPlease try again (e.g. name@company.com):",
        "registered": (
            "🎉 *You're registered!*\n\n"
            "🏅 Sport: *{sport}*\n"
            "📊 Level: *{level}*\n"
            "📧 Email: `{email}`\n\n"
            "{status}\n\n"
            "👇 Join the challenge group:\n{link}\n\n"
            "Each day there will be a reminder in the group. To check in, use `/checkin` (or the button) "
            "and reply with an image *with a caption* in one message. Let's go! 🚀"
        ),
        "cancel": "Registration cancelled. Send /start whenever you're ready.",
        "need_caption_retry": "⚠️ Please add a caption to the image (one message) and send again.",
        "need_caption": "⚠️ To log a workout, send a photo/screenshot *with a caption* in one message.",
        "sheet_fail": "⚠️ Couldn't write to Google Sheets. Check `GOOGLE_*` env vars and sheet access, then try again.",
        "praise": "{praise}\n\nChecked in today: {unique}",
        "stats": "📊 *Stats for {date}*\n\n✅ People checked in: *{unique}*\n🧾 Total logs: *{total}*",
        "reminder": (
            "🌅 *Good morning!*\n\n"
            "📅 {date}\n\n"
            "💪 Tap the button below (or type `/checkin`), then *reply to the bot's message* with a photo/screenshot + caption.\n\n"
            "Every rep counts. Let's go! 🚀"
        ),
        "checkin_prompt": "{mention}, reply to this message with a <b>photo/screenshot</b> and add a <b>caption</b> describing what you did.",
        "checkin_ack": "Ok! Reply with an image + caption.",
    }
    table = ru if lang == "ru" else en
    return table[key].format(**kwargs)


def _sheet_client():
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    creds.refresh(Request())   # exchange refresh_token → access_token
    return gspread.authorize(creds)


def _participants_ws(spreadsheet):
    try:
        return spreadsheet.worksheet("Participants")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet("Participants", rows=1000, cols=60)
        ws.append_row(["Telegram ID", "Full Name", "Username",
                       "Sport", "Level", "Corporate Email", "Registered At"])
        return ws


def _daily_ws(spreadsheet, date_str: str):
    """Return (or create) a per-day worksheet named like '2026-04-06'."""
    try:
        return spreadsheet.worksheet(date_str)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(date_str, rows=500, cols=5)
        ws.append_row(["Telegram ID", "Full Name", "Activity", "Done ✅", "Time"])
        return ws


def save_participant(user_data: dict, tg_user) -> None:
    spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
    ws = _participants_ws(spreadsheet)

    row = [
        tg_user.id,
        tg_user.full_name,
        tg_user.username or "",
        user_data["sport"],
        user_data["level"],
        user_data["email"],
        datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M"),
    ]

    # Update if already registered, otherwise append
    records = ws.get_all_records()
    for idx, rec in enumerate(records, start=2):        # row 1 = header
        if str(rec.get("Telegram ID")) == str(tg_user.id):
            ws.update(f"A{idx}:G{idx}", [row])
            return
    ws.append_row(row)


def _ensure_daily_header(ws) -> None:
    """Best-effort: ensure daily worksheet has expected header columns."""
    try:
        header = ws.row_values(1)
        expected = ["Telegram ID", "Full Name", "Activity", "Done ✅", "Time"]
        if header == expected:
            return
        if not header:
            ws.update("A1:E1", [expected])
            return
        # If old header is present, patch it in place (keeping any extra cols)
        padded = (header + [""] * 5)[:5]
        if padded != expected:
            ws.update("A1:E1", [expected])
    except Exception:
        # Don't block check-ins if header update fails
        return


def _find_daily_row_index(ws, tg_user_id: str) -> int | None:
    """Return 1-based row index (>=2) for tg_user_id in column A, else None."""
    try:
        # Column A contains Telegram ID; row 1 is header
        col = ws.col_values(1)
        for i, v in enumerate(col[1:], start=2):
            if str(v).strip() == tg_user_id:
                return i
        return None
    except Exception:
        return None


def upsert_checkin(tg_user, activity: str) -> str:
    """
    Upsert today's check-in row.

    Returns:
      - "new": created a new row
      - "updated": updated existing row's activity/time
      - "exists": already present and no update needed
    """
    spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
    date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
    ws = _daily_ws(spreadsheet, date_str)
    _ensure_daily_header(ws)

    tg_id = str(tg_user.id)
    now_time = datetime.now(pytz.timezone(TIMEZONE)).strftime("%H:%M")

    row_idx = _find_daily_row_index(ws, tg_id)
    if row_idx is None:
        ws.append_row([tg_user.id, tg_user.full_name, activity, "✅", now_time])
        return "new"

    # Existing row: update activity/time (and keep Done ✅)
    try:
        current_activity = (ws.cell(row_idx, 3).value or "").strip()
    except Exception:
        current_activity = ""

    activity_clean = (activity or "").strip()
    if activity_clean and activity_clean != current_activity:
        ws.update(f"C{row_idx}:E{row_idx}", [[activity_clean, "✅", now_time]])
        return "updated"

    return "exists"


def today_count() -> int:
    """Return total number of logs today (rows in daily sheet)."""
    try:
        spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
        date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
        ws = _daily_ws(spreadsheet, date_str)
        return max(0, len(ws.get_all_records()))
    except Exception:
        return 0

def today_stats() -> tuple[int, int]:
    """Return (unique_users, total_logs) for today."""
    try:
        spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
        date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
        ws = _daily_ws(spreadsheet, date_str)
        recs = ws.get_all_records()
        ids = {str(r.get("Telegram ID")).strip() for r in recs if str(r.get("Telegram ID")).strip()}
        return (len(ids), len(recs))
    except Exception:
        return (0, 0)


# ── Bot handlers ──────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🏃 Running",  callback_data="sport_Running"),
            InlineKeyboardButton("🚴 Cycling",  callback_data="sport_Cycling"),
        ],
        [
            InlineKeyboardButton("🏊 Swimming", callback_data="sport_Swimming"),
            InlineKeyboardButton("💪 Gym",       callback_data="sport_Gym"),
        ],
        [
            InlineKeyboardButton("🧘 Yoga",     callback_data="sport_Yoga"),
            InlineKeyboardButton("⭐ Other",     callback_data="sport_Other"),
        ],
    ]
    lang = _get_lang(update)
    await update.message.reply_text(
        _t(lang, "welcome"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SPORT


async def sport_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sport = query.data.replace("sport_", "")
    context.user_data["sport"] = sport

    keyboard = [
        [InlineKeyboardButton("🌱 Newbie",   callback_data="level_Newbie")],
        [InlineKeyboardButton("🔥 Regular",  callback_data="level_Regular")],
        [InlineKeyboardButton("⚡ Pro",       callback_data="level_Pro")],
    ]
    lang = _get_lang(update, sport)
    await query.edit_message_text(
        _t(lang, "sport_chosen", sport=sport),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return LEVEL


async def level_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    level = query.data.replace("level_", "")
    context.user_data["level"] = level

    lang = _get_lang(update, level)
    await query.edit_message_text(
        _t(lang, "level_chosen", level=level),
        parse_mode="Markdown",
    )
    return EMAIL


async def email_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    lang = _get_lang(update, email)

    if not re.match(r"^[\w.%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}$", email):
        await update.message.reply_text(
            _t(lang, "bad_email")
        )
        return EMAIL

    context.user_data["email"] = email

    try:
        save_participant(context.user_data, update.effective_user)
        saved_ok = True
    except Exception as e:
        logger.error("Sheet save error: %s", e)
        saved_ok = False

    link = GROUP_INVITE_LINK or "_(ask your admin for the group link)_"
    status_line = "✅ Записала в таблицу!" if saved_ok else "⚠️ Не получилось записать в таблицу — пожалуйста, напиши администратору."
    if lang == "en":
        status_line = "✅ Saved to the spreadsheet!" if saved_ok else "⚠️ Couldn't write to the spreadsheet — please contact the admin."

    await update.message.reply_text(
        _t(
            lang,
            "registered",
            sport=context.user_data["sport"],
            level=context.user_data["level"],
            email=email,
            status=status_line,
            link=link,
        ),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = _get_lang(update)
    await update.message.reply_text(_t(lang, "cancel"))
    return ConversationHandler.END


def _extract_image_kind(msg) -> str | None:
    """Return 'photo' or 'document' if message contains an image, else None."""
    if msg.photo:
        return "photo"
    doc = msg.document
    if not doc:
        return None
    mime = (doc.mime_type or "").lower()
    if mime.startswith("image/"):
        return "document"
    # Some clients may send without mime_type; fall back to extension
    name = (doc.file_name or "").lower()
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "document"
    return None


async def handle_group_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fires when someone posts a workout photo/screenshot in the group chat.

    If the user has a pending check-in prompt, the image must be a reply to it and include a caption.
    """
    msg = update.message
    if not msg:
        return

    image_kind = _extract_image_kind(msg)
    if not image_kind:
        return

    # Ignore if not in the configured group
    if GROUP_CHAT_ID and str(msg.chat_id) != str(GROUP_CHAT_ID):
        return

    user = update.effective_user
    lang = _get_lang(update, msg.caption or "")

    pending_all = context.application.bot_data.get("pending_checkins") or {}
    pending = pending_all.get(str(user.id))
    now_ts = datetime.now(pytz.timezone(TIMEZONE)).timestamp()

    # If a pending prompt exists, require reply-to + caption
    if pending and pending.get("chat_id") == msg.chat_id and pending.get("expires_at", 0) >= now_ts:
        prompt_message_id = pending.get("prompt_message_id")
        if not msg.reply_to_message or msg.reply_to_message.message_id != prompt_message_id:
            return
        caption = (msg.caption or "").strip()
        if not caption:
            await msg.reply_text(_t(lang, "need_caption_retry"))
            return
        activity = caption
        # consume pending check-in once a valid reply arrives
        context.application.bot_data["pending_checkins"].pop(str(user.id), None)
        # delete the prompt message after successful check-in
        try:
            await context.bot.delete_message(chat_id=msg.chat_id, message_id=prompt_message_id)
        except Exception:
            pass
    else:
        # No pending prompt: still require a caption on the image message
        caption = (msg.caption or "").strip()
        if not caption:
            await msg.reply_text(
                _t(lang, "need_caption"),
                parse_mode="Markdown" if lang == "ru" else "Markdown",
            )
            return
        activity = caption

    try:
        # Allow multiple logs per day: always append a new row
        spreadsheet = _sheet_client().open_by_key(GOOGLE_SHEET_ID)
        date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
        ws = _daily_ws(spreadsheet, date_str)
        _ensure_daily_header(ws)
        ws.append_row([
            user.id,
            user.full_name,
            (activity or "").strip(),
            "✅",
            datetime.now(pytz.timezone(TIMEZONE)).strftime("%H:%M"),
        ])
        status = "new"
    except Exception as e:
        logger.error("Failed to mark photo in sheet: %s", e)
        await msg.reply_text(_t(lang, "sheet_fail"))
        return

    if status in {"new", "updated"}:
        unique, total = today_stats()
        praise = random.choice(PRAISE_PHRASES)
        if lang == "en":
            # quick English praise set
            praise = random.choice(["Nice! Keep it up 💪", "Logged ✅ Great job!", "Awesome work 🔥", "Done ✅", "Great consistency 🚀"])
        await msg.reply_text(_t(lang, "praise", praise=praise, unique=unique, total=total))
    else:
        # With multiple logs enabled, this branch should not happen, keep a safe message
        await msg.reply_text(_t(lang, "praise", praise=random.choice(PRAISE_PHRASES), unique=today_stats()[0], total=today_stats()[1]))


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: show how many people posted today."""
    lang = _get_lang(update)
    unique, total = today_stats()
    date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
    await update.message.reply_text(
        _t(lang, "stats", date=date_str, unique=unique, total=total),
        parse_mode="Markdown",
    )


# ── Scheduler job ─────────────────────────────────────────────────────────────

async def daily_reminder(app: Application):
    if not GROUP_CHAT_ID:
        logger.warning("GROUP_CHAT_ID not set — skipping daily reminder.")
        return

    date_str = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
    try:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ /checkin", callback_data="checkin")]]
        )
        await app.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=_t("ru", "reminder", date=date_str),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        logger.info("Daily reminder sent to group %s", GROUP_CHAT_ID)
    except Exception as e:
        logger.error("Failed to send daily reminder: %s", e)

def _user_mention_md(user) -> str:
    name = (user.full_name or user.first_name or "user").replace("[", "(").replace("]", ")")
    return f"[{name}](tg://user?id={user.id})"


def _user_mention_html(user) -> str:
    name = html.escape(user.full_name or user.first_name or "user")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def _start_checkin_prompt(message, user, bot, bot_data) -> None:
    """Send (and track) a per-user prompt message to reply to with image+caption."""
    now = datetime.now(pytz.timezone(TIMEZONE))

    pending = bot_data.get("pending_checkins")
    if not isinstance(pending, dict):
        pending = {}
        bot_data["pending_checkins"] = pending

    # pick language from user
    lang = "ru"
    try:
        lc = (getattr(user, "language_code", None) or "").lower()
        if lc and not lc.startswith(("ru", "uk", "be")):
            lang = "en"
    except Exception:
        pass
    prompt_text = _t(lang, "checkin_prompt", mention=_user_mention_html(user))
    try:
        # PTB v21 uses reply_parameters under the hood; avoid allow_sending_without_reply here.
        prompt = await message.reply_text(prompt_text, parse_mode="HTML")
    except Exception:
        # Fallback: send as a normal message if replying fails for any reason
        prompt = await bot.send_message(
            chat_id=message.chat_id,
            text=_t(lang, "checkin_ack"),
        )

    pending[str(user.id)] = {
        "chat_id": message.chat_id,
        "prompt_message_id": prompt.message_id,
        "expires_at": now.timestamp() + PENDING_CHECKIN_TTL_SECONDS,
    }


async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group command: start check-in prompt (same as button)."""
    msg = update.message
    if not msg:
        return
    if GROUP_CHAT_ID and str(msg.chat_id) != str(GROUP_CHAT_ID):
        return
    await _start_checkin_prompt(
        message=msg,
        user=update.effective_user,
        bot=context.bot,
        bot_data=context.application.bot_data,
    )


async def handle_checkin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline button click: start check-in prompt (same as /checkin)."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    msg = query.message
    if not msg:
        return

    if GROUP_CHAT_ID and str(msg.chat_id) != str(GROUP_CHAT_ID):
        return

    data = (query.data or "").strip()
    # Backward-compatible: older pinned messages used "start_checkin"
    if data not in {"checkin", "start_checkin"}:
        return

    user = query.from_user

    bot_data = context.application.bot_data
    lang = "ru"
    try:
        lc = (getattr(query.from_user, "language_code", None) or "").lower()
        if lc and not lc.startswith(("ru", "uk", "be")):
            lang = "en"
    except Exception:
        pass
    await query.answer(_t(lang, "checkin_ack"), show_alert=False)
    await _start_checkin_prompt(
        message=msg,
        user=user,
        bot=context.bot,
        bot_data=bot_data,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    async def post_init(app: Application):
        # Register commands so Telegram shows them in UI for DMs and groups
        private_cmds = [
            BotCommand("start", "Начать регистрацию"),
            BotCommand("cancel", "Отменить регистрацию"),
        ]
        group_cmds = [
            BotCommand("checkin", "✅ Отметить тренировку"),
            BotCommand("stats", "📊 Сколько отметилось сегодня"),
        ]
        try:
            await app.bot.set_my_commands(private_cmds, scope=BotCommandScopeAllPrivateChats())
            await app.bot.set_my_commands(group_cmds, scope=BotCommandScopeAllGroupChats())
        except Exception as e:
            logger.warning("Failed to set bot commands: %s", e)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Registration conversation
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            SPORT: [CallbackQueryHandler(sport_chosen, pattern="^sport_")],
            LEVEL: [CallbackQueryHandler(level_chosen, pattern="^level_")],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_received)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CallbackQueryHandler(handle_checkin_button, pattern="^(checkin|start_checkin)$"))
    app.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.Document.ALL) & (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP),
            handle_group_image,
        )
    )

    # Daily scheduler
    tz = pytz.timezone(TIMEZONE)
    hour, minute = map(int, NOTIFY_TIME.split(":"))
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(
        daily_reminder,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[app],
    )
    scheduler.start()
    logger.info("Scheduler started — daily reminder at %s %s", NOTIFY_TIME, TIMEZONE)

    logger.info("Bot is running…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
